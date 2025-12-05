#!/usr/bin/env python3
# (same contents as previously executed cell)
import argparse
import json
import sys
import re
import glob
from pathlib import Path
from datetime import datetime

import pandas as pd


CANDIDATE_TEXT_PATTERNS = [
    r"description",
    r"what",
    r"notes?",
    r"step",
    r"instruction",
    r"narr",
    r"detail",
    r"comment",
    r"task",
    r"activity",
]


def guess_text_columns(columns):
    cols = [str(c) for c in columns]
    ranked = []
    for c in cols:
        score = 0
        lc = c.lower()
        for pat in CANDIDATE_TEXT_PATTERNS:
            if re.search(pat, lc):
                score += 1
        score += min(len(lc) / 20.0, 1.0)
        ranked.append((score, c))
    ranked.sort(reverse=True)
    chosen = [c for s, c in ranked if s > 0]
    return chosen[:3] if chosen else []


def read_any(path, sheet=None, encoding=None):
    p = Path(path)
    if p.suffix.lower() in [".xlsx", ".xlsm", ".xls"]:
        try:
            if sheet is None:
                df = pd.read_excel(p, engine="openpyxl")
            else:
                df = pd.read_excel(p, sheet_name=sheet, engine="openpyxl")
        except Exception as e:
            df = pd.read_excel(p)
        return df
    elif p.suffix.lower() in [".csv", ".txt"]:
        kwargs = {}
        if encoding:
            kwargs["encoding"] = encoding
        try_delims = [",", "\t", "|", ";"]
        for d in try_delims:
            try:
                return pd.read_csv(p, delimiter=d, **kwargs)
            except Exception:
                continue
        return pd.read_csv(p, **kwargs)
    else:
        raise ValueError(f"Unsupported file type: {p.suffix}")


def build_items_from_df(df, source_file, id_prefix, explicit_text_cols=None):
    items = []
    col_map = {str(c): c for c in df.columns}
    lower_map = {str(c).lower(): c for c in df.columns}

    id_cols = []
    for key in ["task id", "id", "code", "step id", "opm_code"]:
        if key in lower_map:
            id_cols.append(lower_map[key])

    if explicit_text_cols:
        text_cols = [col_map.get(c, c) for c in explicit_text_cols if c in col_map or c in df.columns]
    else:
        text_cols = guess_text_columns(df.columns)

    context_cols = []
    for key in ["who", "where", "considerations", "policy needed?", "policy", "owner"]:
        if key in lower_map:
            context_cols.append(lower_map[key])

    for idx, row in df.iterrows():
        parts = []
        for c in text_cols:
            if c in df.columns:
                val = row[c]
                if pd.notna(val) and str(val).strip():
                    parts.append(str(val).strip())
        text = " — ".join(parts).strip()

        if not text:
            continue

        item = {
            "id": f"{id_prefix}:{idx+1}",
            "source_file": str(source_file),
            "row_index": int(idx),
            "text": text,
        }

        for c in id_cols:
            if c in df.columns:
                val = row[c]
                if pd.notna(val) and str(val).strip():
                    item.setdefault("ids", {})[str(c)] = str(val).strip()

        for c in context_cols:
            if c in df.columns:
                val = row[c]
                if pd.notna(val) and str(val).strip():
                    item.setdefault("context", {})[str(c)] = str(val).strip()

        items.append(item)

    return items, text_cols


def main(argv):
    parser = argparse.ArgumentParser(description="Generate SOP_narr JSON from a glob of .xlsx/.csv files.")
    parser.add_argument("--inputs", required=True, help="Glob for input files, e.g. '/path/to/Inputs/SRO/*.xlsx' or '**/*.csv'")
    parser.add_argument("--out", default="SOP_narr.json", help="Output JSON path")
    parser.add_argument("--sop", default="SRO", help="SOP code to embed in JSON header")
    parser.add_argument("--sheet", default=None, help="Sheet name or index (for Excel); default = first sheet")
    parser.add_argument("--encoding", default=None, help="Encoding to use for CSV (optional)")
    parser.add_argument("--text-cols", default=None, help="Comma-separated list of column names to use for narration text")
    args = parser.parse_args(argv)

    files = sorted(glob.glob(args.inputs, recursive=True))
    if not files:
        print(f"[ERROR] No files matched: {args.inputs}")
        sys.exit(2)

    explicit_text_cols = None
    if args.text_cols:
        explicit_text_cols = [c.strip() for c in args.text_cols.split(",") if c.strip()]

    all_items = []
    first_detected_text_cols = None

    for f in files:
        try:
            df = read_any(f, sheet=args.sheet, encoding=args.encoding)
        except Exception as e:
            print(f"[WARN] Skipping {f}: {e}")
            continue

        df = df.dropna(how="all").reset_index(drop=True)

        id_prefix = Path(f).stem
        items, detected_text_cols = build_items_from_df(
            df,
            source_file=f,
            id_prefix=id_prefix,
            explicit_text_cols=explicit_text_cols,
        )
        if detected_text_cols and first_detected_text_cols is None:
            first_detected_text_cols = detected_text_cols

        all_items.extend(items)

    payload = {
        "sop": args.sop,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs_glob": args.inputs,
        "text_columns": explicit_text_cols if explicit_text_cols else first_detected_text_cols,
        "count": len(all_items),
        "items": all_items,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[OK] Wrote {len(all_items)} items to {out_path}")
    if payload["text_columns"]:
        print(f"[INFO] Text columns used/detected: {payload['text_columns']}")
    else:
        print("[INFO] No text columns detected; items were built from non-empty rows only (rare).")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
