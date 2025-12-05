#!/usr/bin/env python3
import argparse, json, glob, re, sys
from pathlib import Path
from datetime import datetime
import pandas as pd  # keep ONE import at module level

SUPPORTED_XL = {".xlsx", ".xlsm", ".xls"}
SUPPORTED_CSV = {".csv", ".txt"}

DO_NOT_EDIT_START = "// ===== BEGIN DEFAULT NARR CONFIG (do not edit) ====="
DO_NOT_EDIT_END   = "// ===== END DEFAULT NARR CONFIG ====="

DEFAULT_SUMMARIZE = """{
  reading_grade: 8,
  style: "short_simple",
  max_sentence_len: 24,
  bullets: false,
  simple_grade: 5,
  simple_max_len: 14,
  simple_bullets: false
}"""

DEFAULT_OUTPUT = """{
  timezone: "America/New_York",
  timestamp_fmt: "DDMMYY_HHMM",
  keep_latest: true
}"""

DEFAULT_LOGGING = """{
  nonconformance_policy: "log_and_continue",
  qa_filename_suffix: "_QA.txt"
}"""

def json5_header(lines):
    return "\n".join(f"// {ln}" for ln in lines)

def insert_or_replace_top_level(json5_text: str, key: str, body: str) -> str:
    pattern = re.compile(r'(^|\n)\s*' + re.escape(key) + r'\s*:\s*\{.*?\}\s*(,)?', flags=re.S)
    if pattern.search(json5_text):
        return pattern.sub(lambda m: f"\n  {key}: {body},\n", json5_text)
    return json5_text

def ensure_trailing_comma_before_closing_brace(text: str) -> str:
    idx = text.rfind('}')
    if idx == -1:
        raise ValueError("Output doesn't look like a JSON5 object (no closing }).")
    prefix, suffix = text[:idx].rstrip(), text[idx:]
    if not prefix.endswith(','):
        prefix += ','
    return prefix + "\n" + suffix

def append_defaults_guarded(text: str) -> str:
    changed = False
    t = insert_or_replace_top_level(text, "summarize", DEFAULT_SUMMARIZE)
    changed |= (t != text); text = t
    t = insert_or_replace_top_level(text, "output", DEFAULT_OUTPUT)
    changed |= (t != text); text = t
    t = insert_or_replace_top_level(text, "logging", DEFAULT_LOGGING)
    changed |= (t != text); text = t

    guard = (
        f"\n{DO_NOT_EDIT_START}\n"
        f"  // The following default blocks are managed by the generator.\n"
        f"  summarize: {DEFAULT_SUMMARIZE},\n"
        f"  output: {DEFAULT_OUTPUT},\n"
        f"  logging: {DEFAULT_LOGGING}\n"
        f"{DO_NOT_EDIT_END}\n"
    )

    if changed:
        text = ensure_trailing_comma_before_closing_brace(text)
        last = text.rfind('}')
        return text[:last] + guard + text[last:]
    else:
        text = ensure_trailing_comma_before_closing_brace(text)
        last = text.rfind('}')
        return text[:last] + guard + text[last:]

def main(argv):
    ap = argparse.ArgumentParser(description="Emit a single SOP-level .json5 with aggregated narration and built-in defaults.")
    ap.add_argument("--inputs", required=True, help='Comma-separated globs (e.g. "/path/*.xlsx,/path/*.csv")')
    ap.add_argument("--out", required=True, help="Output .json5 path (e.g., Outputs/SRO/SRO_narr.json5)")
    ap.add_argument("--sop", default="SOP", help="SOP code")
    ap.add_argument("--text-cols", required=True, help='Comma-separated columns to aggregate (e.g. "Task Description,What")')
    ap.add_argument("--sheet", default=None, help="Excel sheet name/index (optional)")
    ap.add_argument("--encoding", default=None, help="CSV encoding (optional)")
    ap.add_argument("--sep", default=" — ", help="Separator between requested columns per row")
    ap.add_argument("--join-style", choices=["paragraph","bullets"], default="bullets", help="How to join rows per file")
    args = ap.parse_args(argv)

    if not args.out.lower().endswith(".json5"):
        print(f"[WARN] Output does not end with .json5; writing JSON5 anyway: {args.out}")

    globs = [g.strip() for g in args.inputs.split(",") if g.strip()]
    files = sorted({f for g in globs for f in glob.glob(g, recursive=True)})
    if not files:
        print(f"[ERROR] No files matched any glob: {args.inputs}")
        sys.exit(2)

    requested_cols = [c.strip() for c in args.text_cols.split(",") if c.strip()]
    if not requested_cols:
        print("[ERROR] --text-cols must list at least one column")
        sys.exit(2)

    results = []
    for f in files:
        try:
            suf = Path(f).suffix.lower()
            if suf in {".xlsx", ".xlsm", ".xls"}:
                df = pd.read_excel(f, engine="openpyxl") if args.sheet is None else pd.read_excel(f, sheet_name=args.sheet, engine="openpyxl")
            elif suf in {".csv", ".txt"}:
                kwargs = {}
                if args.encoding:
                    kwargs["encoding"] = args.encoding
                df = None
                for d in [",", "\t", "|", ";"]:
                    try:
                        df = pd.read_csv(f, delimiter=d, **kwargs)
                        break
                    except Exception:
                        continue
                if df is None:
                    df = pd.read_csv(f, **kwargs)
            else:
                continue
        except Exception as e:
            print(f"[WARN] Skipping {f}: {e}")
            continue

        df = df.dropna(how="all")

        # resolve columns case-insensitively
        lower = {str(c).lower(): c for c in df.columns}
        cols = []
        for name in requested_cols:
            key = name.lower()
            if key in lower:
                cols.append(lower[key])
            elif name in df.columns:
                cols.append(name)

        if not cols:
            print(f"[INFO] No requested columns present in {f}; skipping.")
            continue

        # combine per row
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

        results.append({
            "source_file": str(Path(f)),
            "sheet": args.sheet if args.sheet is not None else "default",
            "row_count_used": len(row_texts),
            "columns_used": cols,
            "joined_text": joined
        })

    payload = {
        "sop": args.sop,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": globs,
        "text_columns_requested": requested_cols,
        "file_count": len(results),
        "files": results
    }

    outp = Path(args.out)
    header = json5_header([
        f"{args.sop} narration aggregate (JSON5).",
        "This file is generated. You may add comments, but do not edit the guarded default config.",
    ])
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    text = f"{header}\n{body}\n"
    text = append_defaults_guarded(text)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(text, encoding="utf-8")
    print(f"[OK] Wrote {len(results)} file-level entries to {outp}")

if __name__ == "__main__":
    main(sys.argv[1:])
