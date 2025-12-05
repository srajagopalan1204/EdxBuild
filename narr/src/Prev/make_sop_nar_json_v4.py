#!/usr/bin/env python3
import argparse, json, glob, re, sys
from pathlib import Path
from datetime import datetime
import pandas as pd

SUPPORTED_XL = {".xlsx", ".xlsm", ".xls"}
SUPPORTED_CSV = {".csv", ".txt"}

def strip_json5_comments_and_trailing_commas(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"(?<!:)//.*?$", "", text, flags=re.M)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text

def load_json5_or_json(path: Path):
    raw = path.read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except Exception:
        cleaned = strip_json5_comments_and_trailing_commas(raw)
        return json.loads(cleaned)

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

def json5_dump_with_header(obj: dict, path: Path, header_lines: list[str]):
    body = json.dumps(obj, ensure_ascii=False, indent=2)
    header = "\n".join(f"// {line}" for line in header_lines)
    text = f"{header}\n{body}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def main(argv):
    ap = argparse.ArgumentParser(description="Emit a single SOP-level .json5 with aggregated narration and inline static inserts.")
    ap.add_argument("--inputs", required=True, help='One or more globs, comma-separated (e.g. "/path/*.xlsx,/path/*.csv")')
    ap.add_argument("--out", required=True, help="Output .json5 path (e.g., Outputs/SRO/SRO_narr.json5)")
    ap.add_argument("--sop", default="SOP", help="SOP code")
    ap.add_argument("--text-cols", required=True, help='Comma-separated columns to aggregate (e.g. \"Task Description,What\")')
    ap.add_argument("--sheet", default=None, help="Excel sheet name/index (optional)")
    ap.add_argument("--encoding", default=None, help="CSV encoding (optional)")
    ap.add_argument("--sep", default=" — ", help="Separator between the requested columns per row")
    ap.add_argument("--join-style", choices=["paragraph","bullets"], default="bullets", help="How to join all rows for a file")
    ap.add_argument("--static-inserts", default=None, help="Path to JSON5/JSON; contents will be INLINED into the output json5")
    args = ap.parse_args(argv)

    if not args.out.lower().endswith(".json5"):
        print(f"[WARN] Output does not end with .json5; using JSON5 anyway: {args.out}")

    # Collect files
    globs = [g.strip() for g in args.inputs.split(",") if g.strip()]
    files = []
    for g in globs:
        files.extend(glob.glob(g, recursive=True))
    files = sorted(set(files))
    if not files:
        print(f"[ERROR] No files matched any glob: {args.inputs}")
        sys.exit(2)

    # Columns
    requested_cols = [c.strip() for c in args.text_cols.split(",") if c.strip()]
    if not requested_cols:
        print("[ERROR] --text-cols must list at least one column")
        sys.exit(2)

    # Load static inserts (optional)
    static = {}
    if args.static_inserts:
        p = Path(args.static_inserts)
        if not p.exists():
            print(f"[WARN] --static-inserts file not found: {p}")
        else:
            try:
                static = load_json5_or_json(p)
            except Exception as e:
                print(f"[WARN] Could not parse static inserts as JSON/JSON5: {e}")
                static = {}
    static_global = static.get("global", {}) if isinstance(static, dict) else {}
    static_files = static.get("files", {}) if isinstance(static, dict) else {}

    # Aggregate
    results = []
    for f in files:
        try:
            df = read_any(f, sheet=args.sheet, encoding=args.encoding)
        except Exception as e:
            print(f"[WARN] Skipping {f}: {e}")
            continue

        df = df.dropna(how="all")

        per_file = static_files.get(Path(f).name, {}) if isinstance(static_files, dict) else {}
        cols_override = per_file.get("columns_used")
        if cols_override and isinstance(cols_override, list):
            cols = pick_columns(df, cols_override)
        else:
            cols = pick_columns(df, requested_cols)

        if not cols:
            print(f"[INFO] No requested columns present in {f}; skipping.")
            continue

        joined_text, used_rows = build_filelevel_text(df, cols, sep=args.sep, join_style=args.join_style)

        override_text = per_file.get("override_text")
        append_text = per_file.get("append_text")

        if isinstance(override_text, str) and override_text.strip():
            final_text = override_text.strip()
        else:
            final_text = joined_text
            if isinstance(append_text, str) and append_text.strip():
                if final_text and not final_text.endswith("\n"):
                    final_text = final_text + "\n"
                final_text = final_text + append_text.strip()

        # Pass-through per-file meta (excluding control keys)
        extra_meta = {}
        for k, v in per_file.items():
            if k not in {"columns_used", "override_text", "append_text"}:
                extra_meta[k] = v

        results.append({
            "source_file": str(Path(f)),
            "sheet": args.sheet if args.sheet is not None else "default",
            "row_count_used": int(used_rows),
            "columns_used": cols,
            "joined_text": final_text,
            "static_meta": extra_meta if extra_meta else None
        })

    payload = {
        "sop": args.sop,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": globs,
        "text_columns_requested": requested_cols,
        "file_count": len(results),
        "files": results,
        "static_global": static_global if static_global else None,
        # Keep a copy of static inserts (already applied) for transparency
        "static_inserts_source": Path(args.static_inserts).name if args.static_inserts else None
    }

    # Compose JSON5 with header comments
    header = [
        f"{args.sop} narration aggregate (JSON5).",
        "This file was generated and already includes any static inserts you provided.",
        "Safe to edit by hand: you can add comments, tweak text, etc.",
        "If you re-run generation with a static inserts file, those entries will be applied again.",
    ]
    json5_dump_with_header(payload, Path(args.out), header)

    print(f"[OK] Wrote {len(results)} file-level entries to {args.out}")

if __name__ == "__main__":
    main(sys.argv[1:])
