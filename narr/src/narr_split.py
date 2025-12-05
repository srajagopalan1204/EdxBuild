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

  /.../Excel/Ord2Pick_P1_Enter_a_Quote_Order.xlsx
  /.../Excel/Ord2Pick_P2_Convert_a_quote_to_a_pricing_record.xlsx
  ...

Each file will have at least:

  Task Description, What, Considerations

If the source workbook has helper columns, they are also copied:

  Code, UAP url, UAP Label, Oth1, Oth2, "used for creation only"

Version: 20251205_0900 (America/New_York)
Authors: Subi Rajagopalan   with assistance from ChatGPT (OpenAI)
"""

import argparse
import re
from pathlib import Path
import pandas as pd


def safe_name(text: str, max_length: int = 80) -> str:
    """Turn a task description into a safe filename fragment."""
    if text is None:
        return "step"
    s = str(text).strip()
    if not s:
        return "step"
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r'[<>:"/\\|?*]+', "", s)
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
        "--input", "-i", required=True,
        help="Path to the master narration Excel workbook (one row per step).",
    )
    parser.add_argument(
        "--sop", required=True,
        help="SOP ID / short name (e.g. Quo2Ord, Ord2Pick).",
    )
    parser.add_argument(
        "--out-dir", "-o", required=True,
        help="Directory where per-step Excel files will be written.",
    )
    parser.add_argument(
        "--step-col", default="OPM_Step",
        help="Column with the step code (P1, P2, PM, etc.). Default: OPM_Step",
    )
    parser.add_argument(
        "--task-col", default="Task Description",
        help="Column with the human-readable step name. Default: 'Task Description'",
    )
    parser.add_argument(
        "--what-col", default="What",
        help="Column containing the main narration text. Default: 'What'",
    )
    parser.add_argument(
        "--consid-col", default="Considerations",
        help="Column with extra notes/considerations. Default: 'Considerations'",
    )
    parser.add_argument(
        "--uap-url-col", default="UAP url",
        help="Column with UAP URL (if present). Default: 'UAP url'",
    )
    parser.add_argument(
        "--uap-label-col", default="UAP Label",
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

    required_cols = [args.task_col, args.what_col]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise SystemExit(f"[ERROR] Missing required column(s) in workbook: {missing}")

    has_step = args.step_col in df.columns
    has_consider = args.consid_col in df.columns
    has_uap_url = args.uap_url_col in df.columns
    has_uap_label = args.uap_label_col in df.columns

    # Flexible detection for Code, Oth1, Oth2, and "used for creation only"
    code_col = None
    oth1_col = None
    oth2_col = None
    used_creation_col = None

    for col in df.columns:
        key = str(col).strip().lower()
        if key == "code" and code_col is None:
            code_col = col
        elif key == "oth1" and oth1_col is None:
            oth1_col = col
        elif key == "oth2" and oth2_col is None:
            oth2_col = col
        elif key == "used for creation only" and used_creation_col is None:
            used_creation_col = col

    total_rows = len(df)
    written = 0

    for idx, row in df.iterrows():
        task = row.get(args.task_col)
        what = row.get(args.what_col)

        # Skip rows with no real content
        if (task is None or str(task).strip() == "") and (
            what is None or str(what).strip() == ""
        ):
            continue

        if task is None or str(task).strip() == "":
            print(f"[WARN] Row {idx} has narration but no task description; skipping.")
            continue

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

        data = {
            "Task Description": [task],
            "What": [what],
        }

        if has_consider:
            data["Considerations"] = [row.get(args.consid_col)]
        else:
            data["Considerations"] = [""]
        if has_uap_url:
            data["UAP url"] = [row.get(args.uap_url_col)]

        if has_uap_label:
            data["UAP Label"] = [row.get(args.uap_label_col)]



        # Code
        if code_col is not None:
            data["Code"] = [row.get(code_col)]
        elif has_step:
            data["Code"] = [row.get(args.step_col)]

        # Oth1 / Oth2
        if oth1_col is not None:
            data["Oth1"] = [row.get(oth1_col)]
        if oth2_col is not None:
            data["Oth2"] = [row.get(oth2_col)]

        # "used for creation only"
        if used_creation_col is not None:
            data[used_creation_col] = [row.get(used_creation_col)]

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
