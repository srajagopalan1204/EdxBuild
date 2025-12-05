#!/usr/bin/env python3
"""
narr_build_phased.py  (updated)
Phased narration builder with:
  - Robust JSON5 config support (uses json5 if installed; else fallback cleaner)
  - Sheet resolution: override -> 'OPM' (any case) -> 'Sheet1' (any case) -> first sheet
  - Phase controls (validate/extract/merge/summarize)
  - Intermediates & timestamped finals go to: <outdir>/Intm/
  - QA reports go to: <outdir>/QA/
  - Only *_latest files live directly in <outdir>/ (overwritten each run)
  - Final outputs scrub NaN/None/'nan' to blanks and drop empty rows
"""
import argparse, glob, json, os, re, sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
import numpy as np

def load_config_any(path: str) -> Dict[str, Any]:
    try:
        import json5  # type: ignore
        with open(path, "r", encoding="utf-8") as f:
            return json5.load(f)
    except Exception:
        pass
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    cleaned = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    cleaned = re.sub(r"(^|[^:])//.*?$", r"\1", cleaned, flags=re.M)
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    def repl(m): return f'{m.group(1)}"{m.group(2)}":'
    cleaned = re.sub(r'([[{\s,])([A-Za-z_]\w*)\s*:', repl, cleaned)
    return json.loads(cleaned)

def norm_header(x: str) -> str:
    return re.sub(r"\s+", " ", (x or "")).strip().lower()

def list_sheets(path: str) -> list[str]:
    with pd.ExcelFile(path) as xlf:
        return list(xlf.sheet_names)

def resolve_sheet(path: str, desired: str|None, fallback_opm: bool = True) -> str|int:
    try:
        names = list_sheets(path)
        lower_map = {n.lower(): n for n in names}
        if desired:
            d = str(desired).lower()
            if d in lower_map:
                return lower_map[d]
        if fallback_opm and "opm" in lower_map:
            return lower_map["opm"]
        if "sheet1" in lower_map:
            return lower_map["sheet1"]
        return names[0] if names else 0
    except Exception:
        return 0

def read_excel_resolved(path: str, desired_sheet: str|None) -> pd.DataFrame:
    sheet_to_use = resolve_sheet(path, desired_sheet, fallback_opm=True)
    return pd.read_excel(path, sheet_name=sheet_to_use, dtype=str)

def pick_text_columns(df: pd.DataFrame, preferred: List[str]) -> List[str]:
    nmap = {norm_header(c): c for c in df.columns}
    chosen = [nmap.get(norm_header(c)) for c in preferred if norm_header(c) in nmap]
    chosen = [c for c in chosen if c]
    return chosen if chosen else [c for c in df.columns if df[c].dtype == "object"]

def extract_text_block(df: pd.DataFrame, text_cols: List[str], drop_values: List[str], joiner: str) -> str:
    if not text_cols:
        return ""
    def row_ok(row) -> bool:
        for c in text_cols:
            if str(row.get(c, "")) in drop_values:
                return False
        return True
    rows_ok = df.apply(row_ok, axis=1)
    df2 = df[rows_ok].copy()
    lines = []
    for _, row in df2.iterrows():
        parts = [str(row[c]).strip() for c in text_cols if str(row[c]).strip()]
        if parts:
            lines.append(" ".join(parts))
    text = " ".join(lines).strip() if joiner == " " else joiner.join(lines).strip()
    return re.sub(r"\s+", " ", text)

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

def now_ny() -> str:
    return datetime.now().strftime("%d%m%y_%H%M")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sop", required=True)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--logs", required=True)
    ap.add_argument("--keep-latest", action="store_true")
    ap.add_argument("--stop-after", choices=["validate","extract","merge"])
    ap.add_argument("--only-validate", action="store_true")
    ap.add_argument("--no-summarize", action="store_true")
    ap.add_argument("--emit-intermediate", action="store_true")
    args = ap.parse_args()

    cfg = load_config_any(args.config)
    std_sheet = cfg.get("standard", {}).get("sheet")
    std_cols  = [c for c in cfg.get("standard", {}).get("columns", [])]
    overrides = { o.get("file"): o for o in cfg.get("overrides", []) if isinstance(o, dict) }
    preferred = cfg.get("extraction", {}).get("preferred_text_columns", ["Detail","Step"])
    line_join = cfg.get("extraction", {}).get("line_join", " ")
    drop_vals = cfg.get("extraction", {}).get("drop_values", ["Subitems"])
    file_titles = cfg.get("file_titles", {})
    seq_order = cfg.get("sequence_order", [])
    summarize_cfg = cfg.get("summarize", {})
    max_sentence_len = int(summarize_cfg.get("max_sentence_len", 24))

    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)
    logs_dir = Path(args.logs); logs_dir.mkdir(parents=True, exist_ok=True)
    intm_dir = outdir / "Intm"; intm_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = outdir / "QA"; qa_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(glob.glob(args.inputs))
    if not files:
        print("[ERROR] No input files matched.", file=sys.stderr); sys.exit(2)

    if seq_order:
        order_map = {fn: i for i, fn in enumerate(seq_order)}
        def key_fn(f):
            b = os.path.basename(f)
            return (0, order_map[b]) if b in order_map else (1, b.lower())
        files.sort(key=key_fn)

    print("== Phase: VALIDATE ==")
    issues, validation = [], []
    for f in files:
        base = os.path.basename(f)
        ov = overrides.get(base, {}); sheet = ov.get("sheet", std_sheet)
        ok, err = True, ""
        try:
            df = read_excel_resolved(f, sheet)
            df.columns = [norm_header(c) for c in df.columns]
            manual_map = ov.get("manual_map", {})
            missing = [norm_header(c) for c in std_cols
                       if norm_header(c) not in df.columns and
                          norm_header(c) not in [norm_header(k) for k in manual_map.keys()]]
            if missing:
                ok, err = False, f"missing expected {missing}"
        except Exception as e:
            ok, err = False, f"cannot read sheet '{sheet}': {e}"
        validation.append((base, ok, err))
        if not ok: issues.append(f"{base}: {err}")
    for base, ok, err in validation:
        print(f" - {base}: {'OK' if ok else 'ISSUE'}{'' if ok else '  -> ' + err}")

    if args.only_validate or args.stop_after == "validate":
        ts = now_ny()
        qa = qa_dir / f"{args.sop}_narr_{ts}_QA.txt"
        qa.write_text("\n".join([f"{b}: {'OK' if ok else 'ISSUE - ' + e}" for (b,ok,e) in validation]), encoding="utf-8")
        print(f"[QA] Wrote validation report: {qa}")
        return

    print("== Phase: EXTRACT ==")
    rows, p_idx = [], 1
    for f in files:
        base = os.path.basename(f)
        ov = overrides.get(base, {}); sheet = ov.get("sheet", std_sheet)
        try:
            df = read_excel_resolved(f, sheet)
        except Exception as e:
            issues.append(f"{base}: cannot read sheet '{sheet}': {e}"); continue
        df.columns = [norm_header(c) for c in df.columns]
        rename = { norm_header(src): norm_header(tgt) for src, tgt in ov.get("manual_map", {}).items() }
        if rename: df = df.rename(columns=rename)
        missing = [norm_header(c) for c in std_cols if norm_header(c) not in df.columns]
        if missing: issues.append(f"{base}: missing expected columns {missing} (continuing)")
        text_cols = pick_text_columns(df, preferred)
        text_in = extract_text_block(df, text_cols, drop_vals, line_join)
        rows.append({"OPM_Step": f"P{p_idx}", "Source_File": base,
                     "Source_Title": file_titles.get(base, os.path.splitext(base)[0]),
                     "Step_narr_in": text_in})
        p_idx += 1

    ts = now_ny()
    if args.emit_intermediate:
        pd.DataFrame(rows, columns=["OPM_Step","Source_File","Source_Title","Step_narr_in"])           .to_csv(intm_dir / f"{args.sop}_narr_EXTRACT_{ts}.csv", index=False, encoding="utf-8-sig")
        print(f"[INTERMEDIATE] Extract CSV: {intm_dir / f'{args.sop}_narr_EXTRACT_{ts}.csv'}")

    if args.stop_after == "extract":
        print("[STOP] Stopped after extract phase."); return

    print("== Phase: MERGE ==")
    if rows:
        merged = " ".join([r["Step_narr_in"] for r in rows if r.get("Step_narr_in")]).strip()
        rows_merge = rows + [{"OPM_Step":"PM","Source_File":"","Source_Title":f"{args.sop} – Master",
                              "Step_narr_in": merged, "Step_narr_m_in": merged}]
    else:
        issues.append("No usable rows produced during extract."); rows_merge = rows

    if args.emit_intermediate:
        pd.DataFrame(rows_merge, columns=["OPM_Step","Source_File","Source_Title","Step_narr_in","Step_narr_m_in"])           .to_csv(intm_dir / f"{args.sop}_narr_MERGE_{ts}.csv", index=False, encoding="utf-8-sig")
        print(f"[INTERMEDIATE] Merge CSV: {intm_dir / f'{args.sop}_narr_MERGE_{ts}.csv'}")

    if args.stop_after == "merge":
        print("[STOP] Stopped after merge phase."); return

    print("== Phase: SUMMARIZE ==")
    df_out = pd.DataFrame(rows_merge)
    if not args.no_summarize:
        df_out["Step_narr_out"] = df_out["Step_narr_in"].fillna("").apply(lambda s: simplify_text(s, max_len=max_sentence_len))
        if "Step_narr_m_in" in df_out.columns:
            df_out["Step_narr_m_out"] = df_out["Step_narr_m_in"].fillna("").apply(lambda s: simplify_text(s, max_len=max_sentence_len))
    else:
        df_out["Step_narr_out"] = ""
        if "Step_narr_m_in" in df_out.columns:
            df_out["Step_narr_m_out"] = ""

    # Clean NaN/None/'nan' and drop empty rows
    df_out = df_out.replace({np.nan: ""})
    df_out = df_out.applymap(lambda v: "" if (isinstance(v, str) and v.strip().lower() == "nan") else v)
    def _blank(x): return (not isinstance(x, str)) or (x.strip() == "")
    keep_mask = ~(df_out["Step_narr_in"].apply(_blank) & df_out["Step_narr_out"].apply(_blank))
    df_out = df_out[keep_mask].copy()

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
    for f in files: qa_lines.append(f"  - {os.path.basename(f)}")
    qa_lines.append(""); qa_lines.append(f"Rows output: {len(df_out)}")
    qa_lines.append(f"Columns: {list(df_out.columns)}")
    if issues:
        qa_lines.append("Issues:"); qa_lines.extend([f"  - {i}" for i in issues])
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
