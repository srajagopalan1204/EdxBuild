#!/usr/bin/env python3
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

def strip_json5_comments_and_trailing_commas(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?<!:)//.*?$", "", text, flags=re.M)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text

def json5_dump_with_header(obj: dict, path: Path, header_lines: list[str]):
    body = json.dumps(obj, ensure_ascii=False, indent=2)
    header = "\n".join(f"// {line}" for line in header_lines)
    text = f"{header}\n{body}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def read_any(path, sheet=None, encoding=None):
    p = Path(path)
    if p.suffix.lower() in SUPPORTED_XL:
        if sheet is None:
            return pd.read_excel(p, engine="openpyxl")
        else:
            return pd.read_excel(p, sheet_name=sheet, engine="openpyxl")
    elif p.suffix.lower() in SUPPORTED_CSV:
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

def pick_columns(df, text_cols):
    cols_lower = {str(c).lower(): c for c in df.columns}
    resolved = []
    for name in text_cols:
        key = name.strip().lower()
        if key in cols_lower:
            resolved.append(cols_lower[key])
        else:
            if name in df.columns:
                resolved.append(name)
    return resolved

def build_filelevel_text(df, cols, sep=" — ", join_style="bullets"):
    row_texts = []
    for _, row in df.iterrows():
        bits = []
        for c in cols:
            val = row.get(c)
            if pd.notna(val) and str(val).strip():
                bits.append(str(val).strip())
        if bits:
            row_texts.append(sep.join(bits))
    if not row_texts:
        return "", 0
    if join_style == "paragraph":
        return "  ".join(row_texts), len(row_texts)
    return "\n".join(f"- {t}" for t in row_texts), len(row_texts)

def insert_or_replace_top_level(json5_text: str, key: str, body: str) -> str:
    # Replace existing 'key: { ... }' or mark for append by returning unchanged.
    pattern = re.compile(
        r'(^|\n)\s*' + re.escape(key) + r'\s*:\s*\{.*?\}\s*(,)?',
        flags=re.S
    )
    if pattern.search(json5_text):
        new_block = f"\n  {key}: {body},\n"
        return pattern.sub(lambda m: new_block, json5_text)
    return json5_text  # not found; we'll append later

def ensure_trailing_comma_before_closing_brace(text: str) -> str:
    idx = text.rfind('}')
    if idx == -1:
        raise ValueError("Output doesn't look like a JSON5 object (no closing }).")
    prefix = text[:idx].rstrip()
    suffix = text[idx:]
    if not prefix.endswith(','):
        prefix += ','
    return prefix + "\n" + suffix

def append_defaults_guarded(text: str) -> str:
    # First, attempt to replace existing blocks if present.
    text2 = insert_or_replace_top_level(text, "summarize", DEFAULT_SUMMARIZE)
    text2 = insert_or_replace_top_level(text2, "output", DEFAULT_OUTPUT)
    text2 = insert_or_replace_top_level(text2, "logging", DEFAULT_LOGGING)

    if text2 != text:
        # Blocks were replaced; ensure guard comments exist around them.
        # For simplicity, we append guards once at the end.
        text2 = ensure_trailing_comma_before_closing_brace(text2)
        guard = (
            f"\n{DO_NOT_EDIT_START}\n"
            f"  // The following default blocks may be replaced by the generator; avoid manual edits.\n"
            f"  summarize: {DEFAULT_SUMMARIZE},\n"
            f"  output: {DEFAULT_OUTPUT},\n"
            f"  logging: {DEFAULT_LOGGING}\n"
            f"{DO_NOT_EDIT_END}\n"
        )
        last = text2.rfind('}')
        return text2[:last] + guard + text2[last:]

    # No existing keys found; append a fresh guarded section.
    text3 = ensure_trailing_comma_before_closing_brace(text)
    guard = (
        f"\n{DO_NOT_EDIT_START}\n"
        f"  // The following default blocks were added by the generator; do not modify.\n"
        f"  summarize: {DEFAULT_SUMMARIZE},\n"
        f"  output: {DEFAULT_OUTPUT},\n"
        f"  logging: {DEFAULT_LOGGING}\n"
        f"{DO_NOT_EDIT_END}\n"
    )
    last = text3.rfind('}')
    return text3[:last] + guard + text3[last:]

def main(argv):
    ap = argparse.ArgumentParser(description="Emit a single SOP-level .json5 with aggregated narration and built-in defaults.")
    ap.add_argument("--inputs", required=True, help='One or more globs, comma-separated (e.g. "/path/*.xlsx,/path/*.csv")')
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
    files = []
    for g in globs:
        files.extend(glob.glob(g, recursive=True))
    files = sorted(set(files))
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
            if Path(f).suffix.lower() in SUPPORTED_XL:
                df = pd.read_excel(f, engine="openpyxl") if args.sheet is None else pd.read_excel(f, sheet_name=args.sheet, engine="openpyxl")
            elif Path(f).suffix.lower() in SUPPORTED_CSV:
                df = None
                import pandas as pd  # ensure imported
                kwargs = {}
                if args.encoding:
                    kwargs["encoding"] = args.encoding
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

        # Pick columns (case-insensitive)
        cols_lower = {str(c).lower(): c for c in df.columns}
        cols = []
        for name in requested_cols:
            key = name.strip().lower()
            if key in cols_lower:
                cols.append(cols_lower[key])
            elif name in df.columns:
                cols.append(name)

        if not cols:
            print(f"[INFO] No requested columns present in {f}; skipping.")
            continue

        # Build text
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

        if args.join_style == "paragraph":
            joined = "  ".join(row_texts)
        else:
            joined = "\n".join(f"- {t}" for t in row_texts)

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
    header = [
        f"{args.sop} narration aggregate (JSON5).",
        "This file is generated. You may add comments, but avoid editing the default config section below.",
    ]
    # Write base JSON5
    json_body = json.dumps(payload, ensure_ascii=False, indent=2)
    header_text = "\n".join(f"// {line}" for line in header)
    text = f"{header_text}\n{json_body}\n"
    # Append or replace defaults with guard comments
    text = append_defaults_guarded(text)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(text, encoding="utf-8")
    print(f"[OK] Wrote {len(results)} file-level entries to {outp}")

if __name__ == "__main__":
    main(sys.argv[1:])
