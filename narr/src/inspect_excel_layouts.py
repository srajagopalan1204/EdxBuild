#!/usr/bin/env python3
"""
inspect_excel_layouts.py
List sheet/tab names and columns for each Excel file, and suggest likely text columns.

Usage examples:
  python inspect_excel_layouts.py     --inputs "/workspaces/son_e_lum/narr/Inputs/Tech/*.xlsx"     --out "/workspaces/son_e_lum/narr/logs/Tech/inspect_report.csv"

Options:
  --inputs   Glob pattern to Excel files (e.g., ".../Inputs/Tech/*.xlsx") [required]
  --out      Where to write the CSV report. If omitted, prints only to console.
  --max-rows Limit rows read from each sheet when profiling columns (default: 200)
"""
import argparse, glob, os, re, sys
from pathlib import Path
from typing import List
import pandas as pd

KEYWORDS = ["what","detail","step","notes","action","description","instruction"]

def suggest_text_columns(df: pd.DataFrame) -> List[str]:
    suggestions = []
    for c in df.columns:
        cn = str(c).strip()
        series = df[c].astype(str).fillna("")
        nonempty = series[series.str.strip()!=""]
        avg_len = nonempty.str.len().mean() if len(nonempty) else 0
        hits_kw = any(k in cn.lower() for k in KEYWORDS)
        if hits_kw or avg_len >= 10:
            suggestions.append(cn)
    return suggestions

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out")
    ap.add_argument("--max-rows", type=int, default=200)
    args = ap.parse_args()

    files = sorted(glob.glob(args.inputs))
    if not files:
        print("[ERROR] No Excel files matched your --inputs pattern.", file=sys.stderr)
        sys.exit(2)

    rows = []
    for f in files:
        try:
            xlf = pd.ExcelFile(f)
            sheets = list(xlf.sheet_names)
        except Exception as e:
            print(f"[WARN] Cannot open {os.path.basename(f)}: {e}")
            continue

        # Recommend default sheet: OPM (any case) -> Sheet1 (any case) -> first
        lower_map = {s.lower(): s for s in sheets}
        if "opm" in lower_map:
            recommended = lower_map["opm"]
        elif "sheet1" in lower_map:
            recommended = lower_map["sheet1"]
        else:
            recommended = sheets[0] if sheets else "(none)"

        print(f"\n=== {os.path.basename(f)} ===")
        print(f"Sheets: {', '.join(sheets)}")
        print(f"Recommended default sheet: {recommended}")

        for s in sheets:
            try:
                df = pd.read_excel(f, sheet_name=s, dtype=str, nrows=args.max_rows)
            except Exception as e:
                print(f"  - {s}: cannot read: {e}")
                continue

            cols = [str(c) for c in df.columns]
            sug = suggest_text_columns(df)
            print(f"  - {s}: columns = {cols}")
            print(f"    suggested_text_columns = {sug}")

            rows.append({
                "File": os.path.basename(f),
                "Sheet": s,
                "Recommended_Default_Sheet": recommended,
                "Columns": "; ".join(cols),
                "Suggested_Text_Columns": "; ".join(sug),
                "Rows_Profiled": len(df),
            })

    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        import pandas as _pd
        _pd.DataFrame(rows).to_csv(outp, index=False, encoding="utf-8-sig")
        print(f"\n[OK] Wrote report: {outp}")

if __name__ == "__main__":
    main()
