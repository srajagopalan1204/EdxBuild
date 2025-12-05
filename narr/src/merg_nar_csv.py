#!/usr/bin/env python3
# merg_nar_csv.py (fixed argparse import)
# Build a Transi workbook by fuzzy-matching RAW Title -> Narration Source_Title (OPM_Step).
# Output XLSX only with tabs: Transi, Log, Unmatched_RAW, Unused_NARR.
# Defaults reflect /workspaces/son_e_lum layout; everything can be overridden via CLI.

import os, re, math, glob, argparse, sys
import pandas as pd
from datetime import datetime
from difflib import SequenceMatcher
import pytz

def ny_timestamp():
    ny = pytz.timezone("America/New_York")
    return datetime.now(ny).strftime("%d%m%y_%H%M")

def normalize(s: str) -> str:
    """Lowercase, strip, remove underscores & hyphens, strip punctuation, collapse whitespace."""
    if s is None:
        s = ""
    s = str(s).lower().strip()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"[^\w\s]", " ", s)  # strip punctuation
    s = re.sub(r"\s+", " ", s).strip()
    return s

def ratio(a, b) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()

def load_raw(path_csv: str) -> pd.DataFrame:
    df = pd.read_csv(path_csv, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    return df

def load_narr(path, sheet=0) -> pd.DataFrame:
    # Support .xlsx or .csv for narration
    if path.lower().endswith(".xlsx"):
        df = pd.read_excel(path, sheet_name=sheet, dtype=str).fillna("")
    else:
        df = pd.read_csv(path, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    return df

def discover_narr_file(narr_dir: str) -> str:
    """Find narration file in directory, preferring *_latest.csv, else a likely Narr file by recency."""
    cand = sorted(glob.glob(os.path.join(narr_dir, "*_latest.csv")))
    if cand:
        return cand[0]
    cand = sorted(glob.glob(os.path.join(narr_dir, "*_Narr_latest.*")))
    if cand:
        return cand[0]
    cands = glob.glob(os.path.join(narr_dir, "*_Narr_*.xlsx")) + glob.glob(os.path.join(narr_dir, "*_Narr_*.csv"))
    if cands:
        cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return cands[0]
    anyc = glob.glob(os.path.join(narr_dir, "*.xlsx")) + glob.glob(os.path.join(narr_dir, "*.csv"))
    if anyc:
        anyc.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return anyc[0]
    raise FileNotFoundError(f"No narration file found in {narr_dir}")

def ensure_cols(df: pd.DataFrame, cols):
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df

def build_transi(df_raw, df_narr, thresh=0.80, narr_prefixes=("OPM_", "Step_")):
    # Core narration columns
    core_narr = ["Code","OPM_Step","Step_narr_out","Step_narr_out_simple","Step_narr_m_out","Step_narr_m_out_simple"]
    df_narr = ensure_cols(df_narr, core_narr)

    # Extras
    extra_narr_cols = [c for c in df_narr.columns
                       if (any(c.startswith(p) for p in narr_prefixes))
                       and c not in ["OPM_Step","Step_narr_out","Step_narr_out_simple","Step_narr_m_out","Step_narr_m_out_simple"]]

    df_out = df_raw.copy()
    append_cols = ["OPM_Step","Step_narr_out","Step_narr_out_simple","Step_narr_m_out","Step_narr_m_out_simple"] + extra_narr_cols
    for col in append_cols + ["Merge_OPM","Match_Conf","Source_Title","Review_Flag"]:
        if col not in df_out.columns:
            df_out[col] = ""

    narr_candidates = list(df_narr["OPM_Step"].astype(str).items())

    used_narr_indices = set()
    unmatched_rows = []

    for i, r in df_out.iterrows():
        raw_title = r.get("Title", "")
        if not str(raw_title).strip():
            df_out.at[i, "Review_Flag"] = "Y"
            unmatched_rows.append({"raw_index": i, "Title": r.get("Title",""), "SelectionTitle": r.get("SelectionTitle","")})
            continue

        best_idx, best_text, best_r = None, "", 0.0
        for j, t in narr_candidates:
            s = ratio(raw_title, t)
            if s > best_r:
                best_r, best_idx, best_text = s, j, t

        if best_idx is None or best_r < thresh:
            df_out.at[i, "Review_Flag"] = "Y"
            unmatched_rows.append({"raw_index": i, "Title": r.get("Title",""), "SelectionTitle": r.get("SelectionTitle","")})
            continue

        narr_row = df_narr.loc[best_idx]

        df_out.at[i, "Source_Title"] = narr_row.get("OPM_Step", "")
        df_out.at[i, "Merge_OPM"] = narr_row.get("Code", "")
        df_out.at[i, "Match_Conf"] = str(int(math.ceil(best_r * 100)))
        for col in append_cols:
            df_out.at[i, col] = narr_row.get(col, "")

        used_narr_indices.add(best_idx)

    unused_mask = ~df_narr.index.isin(list(used_narr_indices))
    df_unused_narr = df_narr.loc[unused_mask].copy()

    lead = [c for c in ["Code","Merge_OPM","Match_Conf","Title","Source_Title"] if c in df_out.columns]
    raw_rest = [c for c in df_raw.columns if c not in ["Code","Title"]]
    narr_after = extra_narr_cols + ["Step_narr_out","Step_narr_out_simple","Step_narr_m_out","Step_narr_m_out_simple"]
    df_final = df_out[lead + raw_rest + [c for c in narr_after if c in df_out.columns]]

    return df_final, df_unused_narr, {"unused_mask": unused_mask}

def main():
    parser = argparse.ArgumentParser(description="Merge RAW + Narration into Transi (XLSX) for mk_tw pipeline")
    parser.add_argument("--sop", default="Tech", help="SOP code (default: Tech)")
    parser.add_argument("--raw", default=None, help="Path to RAW CSV; default uses SOP dir under Inputs/<SOP>/raw")
    parser.add_argument("--narr", default=None, help="Path to Narration file (.xlsx or .csv). If omitted, search Outputs/<SOP> for *_latest.csv")
    parser.add_argument("--narr-sheet", default="0", help="Narration sheet name or index (default: 0)")
    parser.add_argument("--out", default=None, help="Output .xlsx file or directory. If dir, use <SOP>_Transi_DDMMYY_HHMM.xlsx")
    parser.add_argument("--name-pattern", default="{sop}_Transi_{stamp}.xlsx", help="File name pattern when --out is a directory (default: {sop}_Transi_{stamp}.xlsx)")
    parser.add_argument("--thresh", type=float, default=0.80, help="Fuzzy match threshold (default: 0.80)")
    parser.add_argument("--narr-extra-prefix", default="OPM_,Step_", help="Comma-separated narration column prefixes to append (default: OPM_,Step_)")
    parser.add_argument("--xlsx-only", action="store_true", default=True, help="Emit only .xlsx (default: True)")
    parser.add_argument("--emit-summary", action="store_true", default=True, help="Print a short run summary (default: True)")

    args = parser.parse_args()

    sop = args.sop
    base = "/workspaces/son_e_lum/narr"
    raw_path = args.raw or os.path.join(base, "Inputs", sop, "raw")
    narr_path = args.narr
    if narr_path is None:
        narr_dir = os.path.join(base, "Outputs", sop)
        narr_path = discover_narr_file(narr_dir)
    if os.path.isdir(raw_path):
        csvs = glob.glob(os.path.join(raw_path, "*.csv"))
        if not csvs:
            raise FileNotFoundError(f"No RAW .csv files in {raw_path}")
        csvs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        raw_path = csvs[0]

    # narration sheet
    narr_sheet = 0
    try:
        narr_sheet = int(args.narr_sheet)
    except:
        narr_sheet = args.narr_sheet

    df_raw = load_raw(raw_path)
    df_narr = load_narr(narr_path, sheet=narr_sheet)

    prefixes = tuple([p.strip() for p in args.narr_extra_prefix.split(",") if p.strip()])
    df_final, df_unused_narr, meta = build_transi(df_raw, df_narr, thresh=args.thresh, narr_prefixes=prefixes)

    out_path = args.out or os.path.join(base, "Outputs", sop, "transi")
    if os.path.isdir(out_path) or not os.path.splitext(out_path)[1]:
        os.makedirs(out_path, exist_ok=True)
        fname = args.name_pattern.format(sop=sop, stamp=ny_timestamp())
        out_xlsx = os.path.join(out_path, fname)
    else:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        out_xlsx = out_path

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        df_final.to_excel(writer, index=False, sheet_name="Transi")
        summary = pd.DataFrame([{
            "raw_rows": len(df_final),
            "matched_rows": int(len(df_final) - int((df_final["Source_Title"] == "").sum())),
            "unmatched_rows": int((df_final["Source_Title"] == "").sum()),
            "unused_narr_rows": int(meta["unused_mask"].sum()),
            "threshold": args.thresh
        }])
        summary.to_excel(writer, index=False, sheet_name="Log")
        unmatched = df_final[df_final["Source_Title"] == ""][["Code","Title"]] if "Code" in df_final.columns else df_final[df_final["Source_Title"] == ""][["Title"]]
        unmatched.to_excel(writer, index=False, sheet_name="Unmatched_RAW")
        df_unused_narr.to_excel(writer, index=False, sheet_name="Unused_NARR")

    if args.emit_summary:
        print("=== merg_nar_csv complete ===")
        print(f"SOP           : {sop}")
        print(f"RAW           : {raw_path}")
        print(f"NARR          : {narr_path}")
        print(f"Output (XLSX) : {out_xlsx}")
        print(f"Threshold     : {args.thresh:.2f}")
        print(f"Rows: RAW={len(df_raw)}  Out={len(df_final)}  Unused_NARR={len(df_unused_narr)}")

if __name__ == "__main__":
    main()
