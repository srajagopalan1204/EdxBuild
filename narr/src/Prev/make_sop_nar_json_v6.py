#!/usr/bin/env python3
# EdxBuild Narration – make_sop_nar_json_v6.py
# Version: 20251205_0900  (America/New_York)
# Authors: Subi Rajagopalan   with assistance from ChatGPT (OpenAI)
#
# USE (example):
#   python /workspaces/EdxBuild/narr/src/make_sop_nar_json_v6.py \
#       --inputs "/workspaces/EdxBuild/narr/Inputs/LineEnt/Excel/*.xlsx,/workspaces/EdxBuild/narr/Inputs/LineEnt/Excel/*.csv" \
#       --out "/workspaces/EdxBuild/narr/Outputs/LineEnt/LineEnt_narr_files.json5" \
#       --sop "LineEnt" \
#       --text-cols "Task Description,What" \
#       --join-style bullets
#
import argparse, json, glob, re, sys
from pathlib import Path
from datetime import datetime
import pandas as pd

SUPPORTED_XL = {".xlsx", ".xlsm", ".xls"}
SUPPORTED_CSV = {".csv", ".txt"}

DO_NOT_EDIT_START = "// ===== BEGIN DEFAULT NARR CONFIG (do not edit) ====="
DO_NOT_EDIT_END   = "// ===== END DEFAULT NARR CONFIG ====="

DEFAULT_SUMMARIZE = """{
  reading_grade: 8,
  style: "short_simple",
  max_sentence_len: 24,
  explicit_steps: true,
}"""

DEFAULT_OUTPUT = """{
  format: "markdown",
  bullets: true,
}"""

DEFAULT_LOGGING = """{
  level: "info",
  include_timings: true,
}"""

def is_excel(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_XL

def is_csv_like(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_CSV

def read_any(path: str, sheet=None, encoding=None) -> pd.DataFrame:
    p = Path(path)
    if is_excel(p):
        if sheet is None:
            return pd.read_excel(p)
        return pd.read_excel(p, sheet_name=sheet)
    elif is_csv_like(p):
        kw = {}
        if encoding:
            kw["encoding"] = encoding
        return pd.read_csv(p, **kw)
    else:
        raise ValueError(f"Unsupported file type: {path}")

def to_title(stem: str) -> str:
    # crude: split on underscores/dashes, capitalize words
    parts = re.split(r"[_\-]+", stem)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        return stem
    return " ".join(w.capitalize() for w in parts)

def main(argv):
    ap = argparse.ArgumentParser(description="Emit Tech_Nar-style JSON5 with file-level joined narration.")
    ap.add_argument("--inputs", required=True, help='Comma-separated globs (e.g. "/path/*.xlsx,/path/*.csv")')
    ap.add_argument("--out", required=True, help="Output .json5 path")
    ap.add_argument("--sop", required=True, help="SOP code (e.g., SRO)")
    ap.add_argument("--text-cols", required=True, help='Comma-separated columns to aggregate (e.g. "Task Description,What")')
    ap.add_argument("--sheet", default=None, help="Excel sheet name/index")
    ap.add_argument("--encoding", default=None, help="CSV encoding")
    ap.add_argument("--sep", default=" — ", help="Separator between the requested columns per row")
    ap.add_argument("--join-style", choices=["paragraph","bullets"], default="bullets", help="How to join row texts per file")
    args = ap.parse_args(argv)

    globs = [g.strip() for g in args.inputs.split(",") if g.strip()]
    files = sorted({f for g in globs for f in glob.glob(g, recursive=True)})
    if not files:
        print(f"[ERROR] No files matched any glob: {args.inputs}")
        sys.exit(1)

    requested_cols = [c.strip() for c in args.text_cols.split(",") if c.strip()]
    if not requested_cols:
        print("[ERROR] --text-cols must list at least one column")
        sys.exit(2)

    entries = []  # aggregated per-file
    for f in files:
        try:
            df = read_any(f, sheet=args.sheet, encoding=args.encoding)
        except Exception as e:
            print(f"[WARN] Skipping {f}: {e}")
            continue
        df = df.dropna(how="all")

        lower = {str(c).lower(): c for c in df.columns}
        cols = []
        for name in requested_cols:
            key = name.lower()
            cols.append(lower.get(key, name if name in df.columns else None))
        cols = [c for c in cols if c is not None]

        if not cols:
            print(f"[INFO] No requested columns present in {f}; skipping.")
            continue

        row_texts = []
        for _, row in df.iterrows():
            bits = []
            for c in cols:
                val = row.get(c)
                if pd.notna(val) and str(val).strip():
                    bits.append(str(val).strip())
            if bits:
                row_texts.append((args.sep).join(bits))

        if not row_texts:
            continue

        joined = "  ".join(row_texts) if args.join_style == "paragraph" else "\n".join(f"- {t}" for t in row_texts)

        # Optional per-file metadata (Code, UAP fields, Oth1/Oth2)
        def _first_nonblank(col_name: str):
            if not col_name or col_name not in df.columns:
                return ""
            series = df[col_name]
            for v in series:
                if pd.notna(v):
                    s = str(v).strip()
                    if s:
                        return s
            return ""

        code_col = lower.get("code")
        uap_label_col = lower.get("uap label") or lower.get("uap_label")
        uap_url_col = lower.get("uap url") or lower.get("uap_url")
        oth1_col = lower.get("oth1")
        oth2_col = lower.get("oth2")

        step_code = _first_nonblank(code_col)
        uap_label = _first_nonblank(uap_label_col)
        uap_url = _first_nonblank(uap_url_col)
        oth1 = _first_nonblank(oth1_col)
        oth2 = _first_nonblank(oth2_col)

        p = Path(f)
        base = p.name
        stem = p.stem
        entries.append({
            "base": base,
            "title": to_title(stem),
            "path": str(p),
            "sheet": args.sheet if args.sheet is not None else "default",
            "columns_used": cols,
            "row_count_used": len(row_texts),
            "joined_text": joined,
            "step_code": step_code,
            "uap_label": uap_label,
            "uap_url": uap_url,
            "oth1": oth1,
            "oth2": oth2,
        })

    # Build Tech_Nar-style sections
    file_titles = {e["base"]: e["title"] for e in entries}
    sequence_order = [e["base"] for e in entries]  # current sort order
    extraction = {
        "method": "file_level_join",
        "join_style": args.join_style,
        "sep": args.sep,
        "text_columns_requested": requested_cols,
        "sources": [
            {"file": e["path"], "sheet": e["sheet"], "columns_used": e["columns_used"], "rows": e["row_count_used"]}
            for e in entries
        ],
        "files": [
            {
                "file": e["base"],
                "joined_text": e["joined_text"],
                "step_code": e.get("step_code", ""),
                "uap_label": e.get("uap_label", ""),
                "uap_url": e.get("uap_url", ""),
                "oth1": e.get("oth1", ""),
                "oth2": e.get("oth2", "")
            }
            for e in entries
        ]
    }

    payload = {
        "sop": args.sop,
        "standard": {},          # placeholder (kept for schema parity)
        "overrides": {},         # placeholder (kept for schema parity)
        "file_titles": file_titles,
        "sequence_order": sequence_order,
        "extraction": extraction,
        # guarded defaults appended after JSON body
    }

    # Compose JSON5 with guard block
    header = [
        f"{args.sop} narration aggregate (JSON5) — Tech_Nar-style schema.",
        "Auto-generated. You may comment anywhere, but do not edit the guarded default config below."
    ]
    header_txt = "\n".join(f"// {ln}" for ln in header)
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    guard = (
        f"\n// ===== BEGIN DEFAULT NARR CONFIG (do not edit) =====\n"
        f"  summarize: {DEFAULT_SUMMARIZE},\n"
        f"  output: {DEFAULT_OUTPUT},\n"
        f"  logging: {DEFAULT_LOGGING}\n"
        f"// ===== END DEFAULT NARR CONFIG =====\n"
    )

    # Insert guard before final closing brace by adding a trailing comma safely
    # Our body ends with '}\n'. We'll insert before that.
    if body.rstrip().endswith('}'):
        body2 = body.rstrip()[:-1] + ",\n" + guard + "}\n"
    else:
        body2 = body + "\n" + guard

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(f"{header_txt}\n{body2}", encoding="utf-8")
    print(f"[OK] Wrote {len(entries)} entries to {outp}")

if __name__ == "__main__":
    main(sys.argv[1:])
