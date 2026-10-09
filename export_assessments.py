
# -*- coding: utf-8 -*-
# ArcMap 10.7 / Python 2.7
# Read-only exporter. Does NOT modify the File Geodatabase.
# run this code in arcpy to generate assessments.json

import arcpy
import os
import json
import re
import io

GDB_PATH = r"D:\shashi_deloitte\BHARAT NAGAR\BHARAT NAGAR.gdb"
FEATURE_CLASS = "Assesments"

OUTPUT_DIR = r"D:\GHMC_Floor_QC\data"
OUTPUT_JSON = os.path.join(OUTPUT_DIR, "assessments.json")

FLOOR_CANDIDATES = [
    "No Of Floors Excluding GroundClear",
    "No Of Floors Excluding Ground Clear",
    "No_Of_Floors_Excluding_GroundClear",
    "NoOfFloors",
    "Floors",
]

IMAGE_CANDIDATES = [
    "Plot Picture",
    "Plot_Picture",
    "PlotPicture",
]

PTIN_CANDIDATES = [
    "PTIN",
    "Property ID",
    "Property_ID",
]

BUILDING_ID_CANDIDATES = [
    "Building ID",
    "Building_ID",
    "BUILDINGID",
    "OBJECTID",
]


def find_field(available_fields, candidates, required=False):
    lookup = dict((f.lower(), f) for f in available_fields)

    for candidate in candidates:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]

    if required:
        raise Exception(
            "Required field not found. Tried: " +
            ", ".join(candidates) +
            "\nAvailable fields: " +
            ", ".join(available_fields)
        )

    return None


def clean_value(value):
    if value is None:
        return None

    if isinstance(value, (int, float, long, bool)):
        return value

    try:
        return unicode(value)
    except Exception:
        return str(value)


def extract_url(value):
    if value is None:
        return u""

    text_value = clean_value(value).strip()

    # Markdown URL: [image](https://example.com/image.jpg)
    match = re.search(
        r'\]\((https?://[^)]+)\)',
        text_value,
        re.IGNORECASE
    )

    if match:
        return match.group(1).strip()

    # Direct URL stored in the field
    match = re.search(
        r'https?://[^\s<>"\']+',
        text_value,
        re.IGNORECASE
    )

    if match:
        return match.group(0).rstrip(")]},").strip()

    return u""


def find_feature_class(gdb_path, target_name):
    """Find a feature class in the GDB root or any feature dataset."""

    arcpy.env.workspace = gdb_path

    available = []

    # Search feature classes in the GDB root.
    root_classes = arcpy.ListFeatureClasses() or []

    for fc in root_classes:
        full_path = os.path.join(gdb_path, fc)
        available.append(full_path)

        if fc.lower() == target_name.lower():
            return full_path, available

    # Search all feature datasets.
    datasets = arcpy.ListDatasets("", "Feature") or []

    for dataset in datasets:
        dataset_path = os.path.join(gdb_path, dataset)
        arcpy.env.workspace = dataset_path

        feature_classes = arcpy.ListFeatureClasses() or []

        for fc in feature_classes:
            full_path = os.path.join(dataset_path, fc)
            available.append(full_path)

            if fc.lower() == target_name.lower():
                return full_path, available

    return None, available


# -------------------------------------------------
# Validate geodatabase
# -------------------------------------------------

if not arcpy.Exists(GDB_PATH):
    raise Exception("Geodatabase not found: " + GDB_PATH)

print("Searching for feature class: " + FEATURE_CLASS)
print("Geodatabase: " + GDB_PATH)

fc_path, available_classes = find_feature_class(
    GDB_PATH, FEATURE_CLASS
)

if not fc_path:
    message = (
        "Feature class '" + FEATURE_CLASS +
        "' was not found in the GDB root or feature datasets.\n"
        "Feature classes discovered:\n"
    )

    for path in available_classes:
        message += "  " + path + "\n"

    message += (
        "\nCheck the actual name. If the data is stored as a "
        "standalone table, use ListTables instead."
    )

    raise Exception(message)

print("Feature class found:")
print(fc_path)

# -------------------------------------------------
# Prepare output
# -------------------------------------------------

if not os.path.isdir(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

fields = [field.name for field in arcpy.ListFields(fc_path)]

floor_field = find_field(
    fields, FLOOR_CANDIDATES, required=True
)

image_field = find_field(
    fields, IMAGE_CANDIDATES, required=True
)

ptin_field = find_field(fields, PTIN_CANDIDATES)
building_field = find_field(fields, BUILDING_ID_CANDIDATES)

oid_field = arcpy.Describe(fc_path).OIDFieldName

selected_fields = [oid_field]

for field_name in [
    building_field, ptin_field, floor_field, image_field
]:
    if field_name and field_name not in selected_fields:
        selected_fields.append(field_name)

# -------------------------------------------------
# Read records without editing the source GDB
# -------------------------------------------------

records = []

with arcpy.da.SearchCursor(fc_path, selected_fields) as cursor:
    for row in cursor:
        values = dict(zip(selected_fields, row))

        object_id = values.get(oid_field)

        record = {
            "OBJECTID": clean_value(object_id),
            "BUILDING_ID": (
                clean_value(values.get(building_field))
                if building_field
                else clean_value(object_id)
            ),
            "PTIN": (
                clean_value(values.get(ptin_field))
                if ptin_field
                else None
            ),
            "RECORDED_FLOORS": clean_value(
                values.get(floor_field)
            ),
            "PLOT_PICTURE_URL": extract_url(
                values.get(image_field)
            ),
        }

        records.append(record)

# -------------------------------------------------
# Write JSON for the Streamlit application
# -------------------------------------------------

payload = {
    "source_gdb": GDB_PATH,
    "feature_class": fc_path,
    "floor_field": floor_field,
    "image_field": image_field,
    "record_count": len(records),
    "records": records
}

with io.open(OUTPUT_JSON, "w", encoding="utf-8") as output_file:
    output_file.write(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2
        )
    )

print("========================================")
print("GHMC Assessment export completed")
print("Records exported: " + str(len(records)))
print("Floor field: " + floor_field)
print("Image field: " + image_field)
print("Feature class: " + fc_path)
print("Output: " + OUTPUT_JSON)
print("Source GDB was not modified.")
print("========================================")
