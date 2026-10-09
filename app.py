
# -*- coding: utf-8 -*-
# GHMC Building Floor QC Application
# Streamlit 1.45.1 compatible
# Source File Geodatabase remains unchanged.

import os
import json
from datetime import date, datetime

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = r"D:\GHMC_Floor_QC"
DATA_DIR = os.path.join(BASE_DIR, "data")

INPUT_JSON = os.path.join(DATA_DIR, "assessments.json")
PROGRESS_JSON = os.path.join(DATA_DIR, "qc_progress.json")
OUTPUT_EXCEL = os.path.join(
    DATA_DIR, "GHMC_Floor_QC_Report.xlsx"
)

FLOOR_OPTIONS = [
    "",
    "G",
    "G+1",
    "G+2",
    "G+3",
    "G+4",
    "G+5",
    "Other",
    "Not identifiable"
]

QC_STATUSES = [
    "Pending",
    "Pass",
    "Fail",
    "Needs Review"
]

os.makedirs(DATA_DIR, exist_ok=True)

st.set_page_config(
    page_title="GHMC Building Floor QC",
    page_icon="🏢",
    layout="wide"
)


# ============================================================
# DATA FUNCTIONS
# ============================================================

def load_source():
    """Load assessment records exported by ArcPy."""

    if not os.path.exists(INPUT_JSON):
        st.error(
            "Source file not found:\n\n"
            + INPUT_JSON
            + "\n\nRun export_assessments.py in ArcMap 10.7 first."
        )
        st.stop()

    try:
        with open(INPUT_JSON, "r", encoding="utf-8") as file:
            return json.load(file)
    except (ValueError, IOError) as exc:
        st.error("Unable to read assessments.json: " + str(exc))
        st.stop()


def load_progress():
    """Load saved QC decisions."""

    if not os.path.exists(PROGRESS_JSON):
        return {}

    try:
        with open(PROGRESS_JSON, "r", encoding="utf-8") as file:
            return json.load(file)
    except (ValueError, IOError) as exc:
        st.error(
            "Unable to read QC progress file: "
            + str(exc)
            + ". Back up the file before repairing it."
        )
        st.stop()


def save_progress(progress):
    """Save progress using an atomic file replacement."""

    temp_path = PROGRESS_JSON + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(
            progress,
            file,
            ensure_ascii=False,
            indent=2
        )

    os.replace(temp_path, PROGRESS_JSON)


def format_recorded_floors(value):
    """
    Display stored floor counts.

    Assumes numeric values represent floors excluding ground.
    Verify this interpretation against the source data.
    """

    if value is None or str(value).strip() == "":
        return "Not available"

    text_value = str(value).strip()

    if (
        text_value.upper() == "G"
        or text_value.upper().startswith("G+")
    ):
        return text_value.upper()

    try:
        number = float(text_value)

        if number >= 0 and number.is_integer():
            if int(number) == 0:
                return "G"

            return "G+" + str(int(number))

    except (ValueError, TypeError):
        pass

    return text_value


def export_excel():
    """Create an Excel report from source records and saved QC."""

    source = load_source()
    records = source.get("records", [])
    progress = load_progress()

    rows = []

    for record in records:
        object_id = str(record.get("OBJECTID", ""))
        qc = progress.get(object_id, {})

        rows.append({
            "OBJECTID": record.get("OBJECTID"),
            "Building_ID": record.get("BUILDING_ID"),
            "PTIN": record.get("PTIN"),
            "Recorded_Floors": record.get("RECORDED_FLOORS"),
            "Recorded_Floors_Display": format_recorded_floors(
                record.get("RECORDED_FLOORS")
            ),
            "QC_Floors": qc.get("QC_FLOORS", ""),
            "QC_Status": qc.get("QC_STATUS", "Pending"),
            "QC_Remarks": qc.get("QC_REMARKS", ""),
            "QC_Reviewer": qc.get("QC_REVIEWER", ""),
            "QC_Date": qc.get("QC_DATE", ""),
            "QC_Updated_At": qc.get("UPDATED_AT", ""),
            "Plot_Picture_URL": record.get(
                "PLOT_PICTURE_URL", ""
            )
        })

    dataframe = pd.DataFrame(rows)

    summary = (
        dataframe["QC_Status"]
        .value_counts()
        .reindex(QC_STATUSES, fill_value=0)
        .rename_axis("QC_Status")
        .reset_index(name="Count")
    )

    with pd.ExcelWriter(
        OUTPUT_EXCEL,
        engine="openpyxl"
    ) as writer:
        dataframe.to_excel(
            writer,
            sheet_name="Building_QC",
            index=False
        )

        summary.to_excel(
            writer,
            sheet_name="QC_Summary",
            index=False
        )


def save_review(
    record,
    verified_floors,
    status,
    remarks,
    reviewer,
    qc_date
):
    """Save the current review and regenerate Excel."""

    if not reviewer or not reviewer.strip():
        st.error("Please enter the reviewer name.")
        return False

    if status == "Pending":
        st.error(
            "Select Pass, Fail, or Needs Review before saving."
        )
        return False

    if status in ("Pass", "Fail") and not verified_floors:
        st.error(
            "Select the visually verified floor count."
        )
        return False

    progress = load_progress()
    object_id = str(record.get("OBJECTID", ""))

    progress[object_id] = {
        "QC_FLOORS": verified_floors,
        "QC_STATUS": status,
        "QC_REMARKS": remarks.strip(),
        "QC_REVIEWER": reviewer.strip(),
        "QC_DATE": qc_date.isoformat(),
        "UPDATED_AT": datetime.now().isoformat(
            timespec="seconds"
        )
    }

    try:
        save_progress(progress)
        export_excel()
        return True

    except Exception as exc:
        st.error(
            "Unable to save the QC report: " + str(exc)
        )
        return False


def load_image(url):
    """Fetch an image URL and display it if accessible."""

    if not url:
        st.warning("No Plot Picture URL is available.")
        return

    st.markdown(
        "[Open original photograph in browser]({})".format(url)
    )

    try:
        response = requests.get(
            url,
            timeout=25,
            headers={"User-Agent": "GHMC-Floor-QC/1.0"}
        )
        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if not content_type.startswith("image/"):
            st.warning(
                "The URL did not return an image. "
                "Open the original link to check authentication "
                "or the server response."
            )
            return

        # Streamlit 1.45.1: use_container_width is supported.
        st.image(
            response.content,
            caption="Building Plot Picture",
            use_container_width=True
        )

    except requests.RequestException as exc:
        st.warning(
            "Unable to load the photograph automatically. "
            "Use the original image link above. Check network "
            "access or authentication if necessary."
        )
        st.caption(str(exc))


# ============================================================
# APPLICATION HEADER
# ============================================================

st.title("GHMC Building Floor QC")

st.caption(
    "Visual quality control of building floors using "
    "Plot Picture images from the Assessments feature class."
)

source = load_source()
records = source.get("records", [])

if not records:
    st.warning("No assessment records were found.")
    st.stop()

# Sort records by numeric OBJECTID when possible.
def object_id_sort_key(record):
    value = record.get("OBJECTID")

    try:
        return (0, int(value))
    except (ValueError, TypeError):
        return (1, str(value or ""))


records = sorted(records, key=object_id_sort_key)
progress = load_progress()


# ============================================================
# DASHBOARD METRICS
# ============================================================

total = len(records)

def status_for(record):
    return progress.get(
        str(record.get("OBJECTID", "")), {}
    ).get("QC_STATUS", "Pending")


pass_count = sum(
    1 for record in records
    if status_for(record) == "Pass"
)

fail_count = sum(
    1 for record in records
    if status_for(record) == "Fail"
)

review_count = sum(
    1 for record in records
    if status_for(record) == "Needs Review"
)

completed = pass_count + fail_count + review_count
pending_count = total - completed

metric1, metric2, metric3, metric4, metric5 = st.columns(5)

metric1.metric("Total Buildings", total)
metric2.metric("Completed", completed)
metric3.metric("Passed", pass_count)
metric4.metric("Failed", fail_count)
metric5.metric("Pending", pending_count)

st.progress(completed / total if total else 0.0)


# ============================================================
# REVIEW QUEUE
# ============================================================

st.sidebar.title("QC Controls")

queue_filter = st.sidebar.selectbox(
    "Review queue",
    [
        "All records",
        "Pending only",
        "Failed only",
        "Needs Review only",
        "Passed only"
    ]
)

if queue_filter == "Pending only":
    queue = [
        record for record in records
        if status_for(record) == "Pending"
    ]

elif queue_filter == "Failed only":
    queue = [
        record for record in records
        if status_for(record) == "Fail"
    ]

elif queue_filter == "Needs Review only":
    queue = [
        record for record in records
        if status_for(record) == "Needs Review"
    ]

elif queue_filter == "Passed only":
    queue = [
        record for record in records
        if status_for(record) == "Pass"
    ]

else:
    queue = records


# ============================================================
# DOWNLOAD EXCEL REPORT
# ============================================================

st.sidebar.divider()
st.sidebar.subheader("Export Report")

if os.path.exists(OUTPUT_EXCEL):
    try:
        with open(OUTPUT_EXCEL, "rb") as file:
            excel_bytes = file.read()

        st.sidebar.download_button(
            label="Download Excel QC Report",
            data=excel_bytes,
            file_name="GHMC_Floor_QC_Report.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        )

    except IOError:
        st.sidebar.warning(
            "Close the Excel workbook if it is open, then refresh."
        )
else:
    st.sidebar.info(
        "The Excel report will be created after the first saved QC."
    )


# ============================================================
# CURRENT RECORD
# ============================================================

if not queue:
    st.info("No buildings match the selected review filter.")
    st.stop()

if "current_index" not in st.session_state:
    st.session_state.current_index = 0

st.session_state.current_index = max(
    0,
    min(
        st.session_state.current_index,
        len(queue) - 1
    )
)

index = st.session_state.current_index
record = queue[index]

object_id = str(record.get("OBJECTID", ""))
qc = progress.get(object_id, {})


# ============================================================
# PREVIOUS / NEXT NAVIGATION
# ============================================================

st.divider()

previous_col, counter_col, next_col = st.columns([1, 3, 1])

with previous_col:
    if st.button(
        "← Previous",
        disabled=(index == 0),
        use_container_width=True
    ):
        st.session_state.current_index -= 1
        st.rerun()

with counter_col:
    st.markdown(
        "### Building {} of {}".format(
            index + 1, len(queue)
        )
    )

with next_col:
    if st.button(
        "Next →",
        disabled=(index >= len(queue) - 1),
        use_container_width=True
    ):
        st.session_state.current_index += 1
        st.rerun()


# ============================================================
# BUILDING IMAGE AND ASSESSMENT DETAILS
# ============================================================

image_column, details_column = st.columns([1.2, 1])

with image_column:
    st.subheader("Building Photograph")
    load_image(record.get("PLOT_PICTURE_URL", ""))

with details_column:
    st.subheader("Assessment Details")

    st.write("**OBJECTID:**", record.get("OBJECTID"))
    st.write("**Building ID:**", record.get("BUILDING_ID"))
    st.write("**PTIN:**", record.get("PTIN"))

    st.write(
        "**Recorded floors:**",
        format_recorded_floors(
            record.get("RECORDED_FLOORS")
        )
    )

    st.write(
        "**Current QC status:**",
        qc.get("QC_STATUS", "Pending")
    )

    st.divider()
    st.subheader("Floor Verification")


    # --------------------------------------------------------
    # QC FORM
    # --------------------------------------------------------

    existing_floor = qc.get("QC_FLOORS", "")
    floor_index = (
        FLOOR_OPTIONS.index(existing_floor)
        if existing_floor in FLOOR_OPTIONS
        else 0
    )

    verified_floors = st.selectbox(
        "Visually verified floors",
        options=FLOOR_OPTIONS,
        index=floor_index,
        key="floor_" + object_id
    )

    existing_status = qc.get("QC_STATUS", "Pending")
    status_index = (
        QC_STATUSES.index(existing_status)
        if existing_status in QC_STATUSES
        else 0
    )

    qc_status = st.selectbox(
        "QC Decision",
        options=QC_STATUSES,
        index=status_index,
        key="status_" + object_id
    )

    qc_remarks = st.text_area(
        "QC Remarks",
        value=qc.get("QC_REMARKS", ""),
        placeholder=(
            "Example: Recorded G+1, photograph indicates G+2."
        ),
        key="remarks_" + object_id
    )

    qc_reviewer = st.text_input(
        "Reviewer Name",
        value=qc.get("QC_REVIEWER", ""),
        key="reviewer_" + object_id
    )

    try:
        default_date = date.fromisoformat(
            qc.get("QC_DATE", date.today().isoformat())
        )
    except (ValueError, TypeError):
        default_date = date.today()

    qc_date = st.date_input(
        "QC Date",
        value=default_date,
        key="date_" + object_id
    )

    if st.button(
        "Save QC Result",
        type="primary",
        use_container_width=True,
        key="save_" + object_id
    ):
        success = save_review(
            record,
            verified_floors,
            qc_status,
            qc_remarks,
            qc_reviewer,
            qc_date
        )

        if success:
            st.success(
                "QC result saved successfully. "
                "Excel report has been updated."
            )
            st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Source feature class: {}".format(
        source.get("feature_class", "Assesments")
    )
)

st.caption(
    "Source GDB: {} | The original File Geodatabase "
    "is read-only in this application.".format(
        source.get("source_gdb", "")
    )
)
