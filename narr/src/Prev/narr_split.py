#!/usr/bin/env python3
"""
narr_split.py

Split a single SOP narration workbook (one row per major step) into
per-step Excel files that the existing narration pipeline can consume.

Typical use:

  python narr/src/narr_split.py \
    --input /workspaces/EdxBuild/narr/Inputs/Ord2Pick/Overall_SLS_Ord2Pick__251123_with_UAP.xlsx \
    --sop Ord2Pick \
    --out-dir /workspaces/EdxBuild/narr/Inputs/Ord2Pick/Excel

This will create one Excel file per row/step, e.g.

  /workspaces/EdxBuild/narr/Inputs/Ord2Pick/Excel/
      Ord2Pick_P1_Enter_a_Quote_Order.xlsx
      Ord2Pick_P2_Convert_a_quote_to_a_pricing_record.xlsx
      ...

Each file will have at least these columns:

  Task Description, What, Considerations

If the source workbook has UAP / other helper columns, they are also copied:

  UAP url, UAP Label, Code, Oth1, Oth2, "used for creation only"

Version: 20251205_0900 (America/New_York)
Authors: Subi Rajagopalan   with assistance from ChatGPT (OpenAI)
"""

import argparse
import re
from pathlib import Path

import pandas as pd


def safe_name(text: str, max_length: int = 80) -> str:
    """
    Turn an arbitrary task description into a safe filename fragment.
    - Collapse whitespace to underscores
    - Remove characters not safe for filenames
    - Truncate to max_length
    """
    if text is None:
        return "step"
    s = str(text).strip()
    if not s:
        return "step"
    # Collapse whitespace
    s = re.sub(r"\s+", "_", s)
    # Remove characters that are troublesome on Windows/macOS/Linux
    s = re.sub(r'[<>:"/\\|?*]+', "", s)
    # Keep only word chars, dash, underscore, dot
    s = re.sub(r"[^\w\-.]", "", s)
    if not s:
        s = "step"
    return s[:max_length]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Split a single SOP narration workbook into per-step Excel files "
            "for the narration pipeline."
        )
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to the master narration Excel workbook (one row per step).",
    )
    parser.add_argument(
        "--sop",
        required=True,
        help="SOP ID / short name (e.g. Quo2Ord, Ord2Pick).",
    )
    parser.add_argument(
        "--out-dir",
        "-o",
        required=True,
        help="Directory where per-step Excel files will be written.",
    )

    # Column mapping options (defaults match your existing patterns)
    parser.add_argument(
        "--step-col",
        default="OPM_Step",
        help="Column with the step code (P1, P2, PM, etc.). Default: OPM_Step",
    )
    parser.add_argument(
        "--task-col",
        default="Task Description",
        help="Column with the human-readable step name. Default: 'Task Description'",
    )
    parser.add_argument(
        "--what-col",
        default="What",
        help="Column containing the main narration text. Default: 'What'",
    )
    parser.add_argument(
        "--consid-col",
        default="Considerations",
        help=(
            "Column containing any extra notes/considerations. "
            "Default: 'Considerations'"
        ),
    )
    parser.add_argument(
        "--uap-url-col",
        default="UAP url",
        help="Column with UAP URL (if present). Default: 'UAP url'",
    )
    parser.add_argument(
        "--uap-label-col",
        default="UAP Label",
        help="Column with UAP label (if present). Default: 'UAP Label'",
    )

    args = parser.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        raise SystemExit(f"[ERROR] Input workbook not found: {in_path}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Reading master workbook: {in_path}")
    df = pd.read_excel(in_path)

    # Basic sanity checks
    required_cols = [args.task_col, args.what_col]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise SystemExit(f"[ERROR] Missing required column(s) in workbook: {missing}")

    has_step = args.step_col in df.columns
    has_consider = args.consid_col in df.columns
    has_uap_url = args.uap_url_col in df.columns
    has_uap_label = args.uap_label_col in df.columns

    # Optional helper columns in the overall workbook
    has_code_col = "Code" in df.columns
    has_oth1 = "Oth1" in df.columns
    has_oth2 = "Oth2" in df.columns

    # Locate any column whose header (trimmed/lower) is "used for creation only"
    used_for_creation_col = None
    for col in df.columns:
        if str(col).strip().lower() == "used for creation only":
            used_for_creation_col = col
            break

    total_rows = len(df)
    written = 0

    for idx, row in df.iterrows():
        task = row.get(args.task_col)
        what = row.get(args.what_col)

        # Skip rows that don't have a real step
        if (task is None or str(task).strip() == "") and (
            what is None or str(what).strip() == ""
        ):
            continue

        if task is None or str(task).strip() == "":
            # We require a task description to name the file
            print(f"[WARN] Row {idx} has narration but no task description; skipping.")
            continue

        # Step code (P1, P2, PM, etc.) is optional but nice to have
        step_code = ""
        if has_step:
            raw_step = row.get(args.step_col)
            if raw_step is not None and str(raw_step).strip():
                step_code = str(raw_step).strip()

        safe_task = safe_name(task)
        if step_code:
            filename = f"{args.sop}_{step_code}_{safe_task}.xlsx"
        else:
            filename = f"{args.sop}_{safe_task}.xlsx"

        # Core fields
        data = {
            "Task Description": [task],
            "What": [what],
        }

        # Considerations: copy if present, otherwise leave blank
        if has_consider:
            data["Considerations"] = [row.get(args.consid_col)]
        else:
            data["Considerations"] = [""]

        # UAP fields: include only if present in source
        if has_uap_url:
            data["UAP url"] = [row.get(args.uap_url_col)]
        if has_uap_label:
            data["UAP Label"] = [row.get(args.uap_label_col)]

        # Code column: prefer explicit 'Code' column; otherwise, reuse step-col
        if has_code_col:
            data["Code"] = [row.get("Code")]
        elif has_step:
            # This ensures downstream scripts can still see a 'Code' field
            data["Code"] = [row.get(args.step_col)]
        # If neither exists, we simply omit the Code column

        # Oth1 / Oth2: carry through if present in the overall file
        if has_oth1:
            data["Oth1"] = [row.get("Oth1")]
        if has_oth2:
            data["Oth2"] = [row.get("Oth2")]

        # "used for creation only" helper column: carry through if present
        if used_for_creation_col is not None:
            data[used_for_creation_col] = [row.get(used_for_creation_col)]

        out_df = pd.DataFrame(data)
        out_path = out_dir / filename
        out_df.to_excel(out_path, index=False)
        written += 1
        print(f"[OK] Wrote {out_path}")

    print(
        f"[DONE] Processed {total_rows} row(s), wrote {written} per-step workbook(s) "
        f"to {out_dir}"
    )


if __name__ == "__main__":
    main()
