#!/usr/bin/env python3
"""
narr_build_phased.py (clean)
Phased narration builder with:
 - JSON5 config (fallback to JSON5-lite)
 - Sheet pick: override -> 'OPM' (any case) -> 'Sheet1' (any case) -> first sheet
 - Phases: validate -> extract -> merge -> summarize
 - Intermediates + timestamped finals -> <outdir>/Intm/
 - QA reports -> <outdir>/QA/
 - Latest files overwrite in <outdir>/
 - Scrub NaN/None/'nan' and drop empty rows
 - Simple columns (K5/K4) alongside standard summaries
"""
import argparse, glob, json, os, re, sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd

# ---------------- Config loader ----------------
def load_config_any(path: str) -> Dict[str, Any]:
    # Prefer real json5 if available
    try:
        import json5  # type: ignore
        with open(path, "r", encoding="utf-8") as f:
            return json5.load(f)
    except Exception:
        pass
    # Fallback: strip comments/trailing commas, quote keys
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    cleaned = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)                 # /* ... */
    cleaned = re.sub(r"(^|[^:])//.*?$", r"\1", cleaned, flags=re.M)     # // ...
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)                    # trailing commas
    def _repl(m): return f'{m.group(1)}"{m.group(2)}":'
    cleaned = re.sub(r'([[{\s,])([A-Za-z_]\w*)\s*:', _repl, cleaned)    # quote bare keys
    return json.loads(cleaned)

# ---------------- Helpers ----------------
def norm_header(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "")).strip().lower()

def list_sheets(path: str) -> List[str]:
    with pd.ExcelFile(path) as xlf:
        return list(xlf.sheet_names)

def resolve_sheet(path: str, desired: Optional[str], fallback_opm: bool = True):
    """desired (case-insensitive) -> 'OPM' -> 'Sheet1' -> first sheet."""
    try:
        names = list_sheets(path)
        lower = {n.lower(): n for n in names}
        if desired:
            d = str(desired).lower()
            if d in lower:
                return lower[d]
        if fallback_opm and "opm" in lower:
            return lower["opm"]
        if "sheet1" in lower:
            return lower["sheet1"]
        return names[0] if names else 0
    except Exception:
        return 0

def read_excel_resolved(path: str, desired_sheet: Optional[str]) -> pd.DataFrame:
    sheet_to_use = resolve_sheet(path, desired_sheet, fallback_opm=True)
    return pd.read_excel(path, sheet_name=sheet_to_use, dtype=str)

def pick_text_columns(df: pd.DataFrame, preferred: List[str]) -> List[str]:
    nmap = {norm_header(c): c for c in df.columns}
    chosen = [nmap.get(norm_header(c)) for c in preferred if norm_header(c) in nmap]
    chosen = [c for c in chosen if c]
    if chosen:
        return chosen
    # fallback: all object columns
    return [c for c in df.columns if df[c].dtype == "object"]

BAD_TOKEN_RE = re.compile(r'\b(?:nan|none|null|na|n/a|nat|-)\b', re.I)

def _clean_cell(val: str) -> str:
    t = (val or "").strip()
    if BAD_TOKEN_RE.fullmatch(t):
        return ""
    t = BAD_TOKEN_RE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def extract_text_block(df: pd.DataFrame, text_cols: List[str], drop_values: List[str], joiner: str) -> str:
    if not text_cols:
        return ""
    # drop rows that equal any drop_values after cleaning
    def row_ok(row) -> bool:
        for c in text_cols:
            if _clean_cell(str(row.get(c, ""))) in drop_values:
                return False
        return True
    rows_ok = df.apply(row_ok, axis=1)
    df2 = df[rows_ok].copy()

    lines = []
    for _, row in df2.iterrows():
        parts = []
        for c in text_cols:
            v = _clean_cell(str(row.get(c, "")))
            if v:
                parts.append(v)
        if parts:
            lines.append(" ".join(parts))
    text = (" ".join(lines).strip() if joiner == " " else joiner.join(lines).strip())
    text = BAD_TOKEN_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def simplify_text(text: str, max_len: int = 24) -> str:
    if not text:
        return ""
    bits = re.split(r"[.;:\n]+", text)
    out = []
    for b in bits:
        b = b.strip()
        if not b:
            continue
        words = b.split()
        if len(words) > max_len:
            words = words[:max_len]
        s = " ".join(words)
        s = s[:1].upper() + s[1:]
        s = s.strip(", ")
        out.append(s)
    return (". ".join(out) + ".") if out else ""

# --- simple summarizers (K–5 / K–4) ---
def simplify_text_k5(text: str, max_len: int = 14) -> str:
    """Very simple reducer: shorter sentences + easy-word swaps."""
    if not text:
        return ""
    # remove ( ... )
    text = re.sub(r"\([^)]*\)", "", text)
    # easy-word swaps
    swaps = {
        "utilize": "use", "assist": "help", "select": "choose",
        "confirm": "check", "navigate": "go to", "appropriate": "right",
        "document": "note", "verify": "check", "complete": "finish",
        "initialize": "start", "terminate": "stop",
    }
    for a, b in swaps.items():
        text = re.sub(rf"\b{a}\b", b, text, flags=re.I)
    # split on sentence-ish boundaries
    bits = re.split(r"[.!?;:\n]+", text)
    out = []
    for b in bits:
        b = b.strip()
        if not b:
            continue
        words = b.split()
        if len(words) > max_len:
            words = words[:max_len]
        snt = " ".join(words)
        snt = snt[:1].upper() + snt[1:]
        out.append(snt)
    return (". ".join(out) + ".") if out else ""

def summarize_to_grade(text: str, grade: int, max_len: int, k5_len: int) -> str:
    return simplify_text_k5(text, max_len=k5_len) if grade <= 5 else simplify_text(text, max_len=max_len)

def now_ny() -> str:
    return datetime.now().strftime("%d%m%y_%H%M")  # DDMMYY_HHMM

# ---------------- Main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sop", required=True)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--logs", required=True)
    ap.add_argument("--keep-latest", action="store_true")
    ap.add_argument("--stop-after", choices=["validate", "extract", "merge"])
    ap.add_argument("--only-validate", action="store_true")
    ap.add_argument("--no-summarize", action="store_true")
    ap.add_argument("--emit-intermediate", action="store_true")
    args = ap.parse_args()

    cfg = load_config_any(args.config)
    std_sheet: Optional[str] = cfg.get("standard", {}).get("sheet")
    std_cols  = [c for c in cfg.get("standard", {}).get("columns", [])]
    overrides = { o.get("file"): o for o in cfg.get("overrides", []) if isinstance(o, dict) }
    preferred = cfg.get("extraction", {}).get(
        "preferred_text_columns",
        ["Detail","Step"]
    )
    line_join = cfg.get("extraction", {}).get("line_join", " ")
    drop_vals = cfg.get("extraction", {}).get("drop_values", ["Subitems"])
    file_titles = cfg.get("file_titles", {})
    seq_order = cfg.get("sequence_order", [])
    summarize_cfg = cfg.get("summarize", {})
    max_sentence_len = int(summarize_cfg.get("max_sentence_len", 24))
    simple_grade = int(summarize_cfg.get("simple_grade", 5))
    simple_max_len = int(summarize_cfg.get("simple_max_len", 14))
    simple_bullets = bool(summarize_cfg.get("simple_bullets", False))
    reading_grade = int(summarize_cfg.get("reading_grade", 8))

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    logs_dir = Path(args.logs); logs_dir.mkdir(parents=True, exist_ok=True)
    intm_dir = outdir / "Intm"; intm_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = outdir / "QA"; qa_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(glob.glob(args.inputs))
    if not files:
        print("[ERROR] No input files matched.", file=sys.stderr); sys.exit(2)

    # Optional explicit order
    if seq_order:
        order_map = {fn: i for i, fn in enumerate(seq_order)}
        def key_fn(f):
            b = os.path.basename(f)
            return (0, order_map[b]) if b in order_map else (1, b.lower())
        files.sort(key=key_fn)

    # -------- VALIDATE --------
    print("== Phase: VALIDATE ==")
    issues: List[str] = []
    validation = []
    for f in files:
        base = os.path.basename(f)
        ov = overrides.get(base, {})
        sheet = ov.get("sheet", std_sheet)
        ok, err = True, ""
        try:
            df = read_excel_resolved(f, sheet)
            df.columns = [norm_header(c) for c in df.columns]
            manual_map = ov.get("manual_map", {})
            missing = [
                norm_header(c) for c in std_cols
                if norm_header(c) not in df.columns and
                   norm_header(c) not in [norm_header(k) for k in manual_map.keys()]
            ]
            if missing:
                ok, err = False, f"missing expected {missing}"
        except Exception as e:
            ok, err = False, f"cannot read sheet '{sheet}': {e}"
        validation.append((base, ok, err))
        if not ok:
            issues.append(f"{base}: {err}")

    for base, ok, err in validation:
        print(f" - {base}: {'OK' if ok else 'ISSUE'}{'' if ok else '  -> ' + err}")

    if args.only_validate or args.stop_after == "validate":
        ts = now_ny()
        qa = qa_dir / f"{args.sop}_narr_{ts}_QA.txt"
        qa.write_text("\n".join([f"{b}: {'OK' if ok else 'ISSUE - ' + e}" for (b,ok,e) in validation]), encoding="utf-8")
        print(f"[QA] Wrote validation report: {qa}")
        return

    # -------- EXTRACT --------
    print("== Phase: EXTRACT ==")
    rows = []
    p_idx = 1
    for f in files:
        base = os.path.basename(f)
        ov = overrides.get(base, {})
        sheet = ov.get("sheet", std_sheet)
        try:
            df = read_excel_resolved(f, sheet)
        except Exception as e:
            issues.append(f"{base}: cannot read sheet '{sheet}': {e}")
            continue
        df.columns = [norm_header(c) for c in df.columns]

        # manual header rename if provided
        rename = {norm_header(src): norm_header(tgt) for src, tgt in ov.get("manual_map", {}).items()}
        if rename:
            df = df.rename(columns=rename)

        # soft check
        missing = [norm_header(c) for c in std_cols if norm_header(c) not in df.columns]
        if missing:
            issues.append(f"{base}: missing expected columns {missing} (continuing)")

        text_cols = pick_text_columns(df, preferred)
        text_in = extract_text_block(df, text_cols, drop_vals, line_join)

        rows.append({
            "OPM_Step": f"P{p_idx}",
            "Source_File": base,
            "Source_Title": file_titles.get(base, os.path.splitext(base)[0]),
            "Step_narr_in": text_in,
        })
        p_idx += 1

    ts = now_ny()
    if args.emit_intermediate:
        pd.DataFrame(rows, columns=["OPM_Step", "Source_File", "Source_Title", "Step_narr_in"]) \
          .to_csv(intm_dir / f"{args.sop}_narr_EXTRACT_{ts}.csv", index=False, encoding="utf-8-sig")
        print(f"[INTERMEDIATE] Extract CSV: {intm_dir / f'{args.sop}_narr_EXTRACT_{ts}.csv'}")

    if args.stop_after == "extract":
        print("[STOP] Stopped after extract phase.")
        return

    # -------- MERGE --------
    print("== Phase: MERGE ==")
    if rows:
        merged = " ".join([r["Step_narr_in"] for r in rows if r.get("Step_narr_in")]).strip()
        merged = BAD_TOKEN_RE.sub("", merged)
        merged = re.sub(r"\s+", " ", merged).strip()
        rows_merge = rows + [{
            "OPM_Step": "PM",
            "Source_File": "",
            "Source_Title": f"{args.sop} – Master",
            "Step_narr_in": merged,
            "Step_narr_m_in": merged,
        }]
    else:
        issues.append("No usable rows produced during extract.")
        rows_merge = rows

    if args.emit_intermediate:
        pd.DataFrame(rows_merge, columns=["OPM_Step","Source_File","Source_Title","Step_narr_in","Step_narr_m_in"]) \
          .to_csv(intm_dir / f"{args.sop}_narr_MERGE_{ts}.csv", index=False, encoding="utf-8-sig")
        print(f"[INTERMEDIATE] Merge CSV: {intm_dir / f'{args.sop}_narr_MERGE_{ts}.csv'}")

    if args.stop_after == "merge":
        print("[STOP] Stopped after merge phase.")
        return

    # -------- SUMMARIZE --------
    print("== Phase: SUMMARIZE ==")
    df_out = pd.DataFrame(rows_merge)

    if not args.no_summarize:
        # Standard summaries (grade ~8) + Simple summaries (grade <=5/4)
        df_out["Step_narr_out"] = df_out["Step_narr_in"].fillna("").apply(
            lambda t: summarize_to_grade(t, reading_grade, max_sentence_len, simple_max_len)
        )
        df_out["Step_narr_out_simple"] = df_out["Step_narr_in"].fillna("").apply(
            lambda t: summarize_to_grade(t, simple_grade, max_sentence_len, simple_max_len)
        )
        if "Step_narr_m_in" in df_out.columns:
            df_out["Step_narr_m_out"] = df_out["Step_narr_m_in"].fillna("").apply(
                lambda t: summarize_to_grade(t, reading_grade, max_sentence_len, simple_max_len)
            )
            df_out["Step_narr_m_out_simple"] = df_out["Step_narr_m_in"].fillna("").apply(
                lambda t: summarize_to_grade(t, simple_grade, max_sentence_len, simple_max_len)
            )
            if simple_bullets:
                def _to_bullets(txt: str) -> str:
                    if not txt: return ""
                    parts = [p.strip() for p in re.split(r"[.!?]+", txt) if p.strip()]
                    return "\n".join(f"- {p}" for p in parts)
                df_out["Step_narr_out_simple"] = df_out["Step_narr_out_simple"].apply(_to_bullets)
                df_out["Step_narr_m_out_simple"] = df_out["Step_narr_m_out_simple"].apply(_to_bullets)
    else:
        df_out["Step_narr_out"] = ""
        if "Step_narr_m_in" in df_out.columns:
            df_out["Step_narr_m_out"] = ""

    # Clean NaN/None/"nan" and drop empty rows
    df_out = df_out.replace({np.nan: ""})
    df_out = df_out.applymap(lambda v: "" if (isinstance(v, str) and v.strip().lower() == "nan") else v)

    def _blank(x): return (not isinstance(x, str)) or (x.strip() == "")
    keep_mask = ~(df_out["Step_narr_in"].apply(_blank) & df_out["Step_narr_out"].apply(_blank))
    df_out = df_out[keep_mask].copy()

    # -------- WRITE --------
    base_name = f"{args.sop}_narr_{ts}"
    csv_path_ts  = (outdir / "Intm") / f"{base_name}.csv"
    xlsx_path_ts = (outdir / "Intm") / f"{base_name}.xlsx"
    qa_path      = (outdir / "QA") / f"{base_name}_QA.txt"

    df_out.to_csv(csv_path_ts, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path_ts, engine="xlsxwriter") as xlw:
        df_out.to_excel(xlw, index=False, sheet_name="Narration")

    qa_lines = []
    qa_lines.append(f"SOP: {args.sop}")
    qa_lines.append(f"Inputs matched: {len(files)}")
    for f in files:
        qa_lines.append(f"  - {os.path.basename(f)}")
    qa_lines.append("")
    qa_lines.append(f"Rows output: {len(df_out)}")
    qa_lines.append(f"Columns: {list(df_out.columns)}")
    if issues:
        qa_lines.append("Issues:")
        qa_lines.extend([f"  - {i}" for i in issues])
    else:
        qa_lines.append("Issues: none detected")
    qa_path.write_text("\n".join(qa_lines), encoding="utf-8")

    print(f"[OK] CSV (timestamped -> Intm): {csv_path_ts}")
    print(f"[OK] XLSX (timestamped -> Intm): {xlsx_path_ts}")
    print(f"[OK] QA  (-> QA): {qa_path}")

    latest_csv  = outdir / f"{args.sop}_narr_latest.csv"
    latest_xlsx = outdir / f"{args.sop}_narr_latest.xlsx"
    df_out.to_csv(latest_csv, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(latest_xlsx, engine="xlsxwriter") as xlw:
        df_out.to_excel(xlw, index=False, sheet_name="Narration")
    print(f"[OK] Latest CSV (-> outdir): {latest_csv}")
    print(f"[OK] Latest XLSX (-> outdir): {latest_xlsx}")

if __name__ == "__main__":
    main()
