#!/usr/bin/env python3
import argparse
import csv
import os
import sys


# Columns we expect to exist in the mk_tw_in_READY CSV
REQUIRED_HEADERS = [
    "Source_PPT",
    "SlideIndex",
    "SelectionTitle",
    "Title",
    "Code",
    "Title_short",
    "Image_sub_url",
    "Deci_Question",
    "Next1_Code",
    "Next2_Code",
    "match_code_OPM",
    "OPM_Step",
    "Source_Title",
    "Narr1",
    "Narr2",
    "Narr3",
    "Disp_next1",
    "Disp_next2",
    "Disp_next3",
    "UAP url",
    "UAP Label",
    "start_here",
    "Mismatch",
    "Entity",
    "Function",
    "SubEntity",
    "SOP_id",
    "SOP_path",
]


def check_csv_headers(csv_path, required_headers):
    """
    Open the CSV, read the header row, and confirm all required headers are present.
    Returns (missing_headers, headers_list)
    """
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or [])]

    missing = [col for col in required_headers if col not in headers]
    return missing, headers


def list_missing_images(csv_path, base_dir):
    """
    Walk the CSV rows and verify that each Image_sub_url points
    to a real file.

    Rules:
    - If Image_sub_url starts with "SOP/" or ".build/" or "/" we treat it
      as an already-formed path and check that exact path.
    - Otherwise, we assume it's just a filename (e.g. "D4.png") and we
      join it under base_dir from --images.
    - We report missing files with the CSV line number (2 = first data row).
    """
    missing = []

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, start=2):
            rel = (row.get("Image_sub_url") or "").strip()
            if not rel:
                # nothing to check for this row
                continue

            # Decide how to build the filesystem path
            if rel.startswith(("SOP/", ".build/", "/")):
                # CSV already stored a path like SOP/images/Palco/Service/ServReqOrd/D4.png
                fs_path = rel
            else:
                # CSV only stored the filename like "D4.png"
                # Build from the provided base_dir
                fs_path = os.path.join(base_dir, rel)

            # Normalize slashes for display and existence check
            fs_path_norm = os.path.normpath(fs_path)

            if not os.path.exists(fs_path_norm):
                # Keep what we *checked*, not the normalized one with backslashes,
                # so output matches what user expects to see.
                missing.append((i, fs_path))

    return missing


def main():
    parser = argparse.ArgumentParser(
        description="Validate mk_tw_in_READY CSV and referenced images for a given SOP."
    )

    # Allow --csv or legacy --in style
    parser.add_argument(
        "--csv",
        "--in",
        dest="csv",
        required=True,
        help="Path to the staged mk_tw_in_READY_*.csv to validate.",
    )

    parser.add_argument(
        "--images",
        default="",
        help="Base directory for images for this SOP "
             "(e.g. /workspaces/.../SOP/images/Palco/Service/ServReqOrd).",
    )

    parser.add_argument(
        "--check-images",
        action="store_true",
        help="If set, verify that every Image_sub_url resolves to an existing file.",
    )

    parser.add_argument(
        "--log",
        help="Optional path to write a validation log file.",
    )

    args = parser.parse_args()

    lines = []

    # 1. CSV header validation
    missing_headers, headers = check_csv_headers(args.csv, REQUIRED_HEADERS)

    lines.append(f"CSV: {args.csv}")
    lines.append(f"Headers: {headers}")

    if missing_headers:
        lines.append("Missing required headers:")
        for h in missing_headers:
            lines.append(f"  {h}")

        text = "\n".join(lines)
        print(text)

        if args.log:
            with open(args.log, "w", encoding="utf-8") as lf:
                lf.write(text + "\n")

        # exit code 2 = header failure
        sys.exit(2)

    # 2. Image existence validation (optional)
    if args.check_images:
        bad = list_missing_images(args.csv, args.images)

        if bad:
            lines.append("Missing images:")
            for line_no, path_str in bad:
                lines.append(f"  line {line_no}: {path_str}")

            text = "\n".join(lines)
            print(text)

            if args.log:
                with open(args.log, "w", encoding="utf-8") as lf:
                    lf.write(text + "\n")

            # exit code 3 = images missing
            sys.exit(3)

    # 3. All good
    lines.append("Validation OK.")

    text = "\n".join(lines)
    print(text)

    if args.log:
        with open(args.log, "w", encoding="utf-8") as lf:
            lf.write(text + "\n")


if __name__ == "__main__":
    main()
