
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, sys, re, logging
from datetime import datetime
from pathlib import Path
import pandas as pd
from difflib import SequenceMatcher

TS_FMT = "%m%d%y_%H%M"  # MMDDYY_HHNN

def ts_now():
    return datetime.now().strftime(TS_FMT)

def setup_logger(outdir: Path, sop: str):
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / f"{sop}_transi_{ts_now()}.log"
    logger = logging.getLogger("transi")
    logger.setLevel(logging.INFO)
    logger.handlers[:] = []
    fh = logging.FileHandler(log_path, encoding="utf-8")
    ch = logging.StreamHandler(sys.stdout)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt); ch.setFormatter(fmt)
    logger.addHandler(fh); logger.addHandler(ch)
    logger.info(f"Log -> {log_path}")
    return logger

def read_csv(path: Path):
    return pd.read_csv(path, encoding="utf-8-sig", engine="python")

def write_csv(df: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")

def normalize_text(s):
    if pd.isna(s): return ""
    return re.sub(r"\s+", " ", str(s)).strip()

def first_nonempty(*vals):
    for v in vals:
        if normalize_text(v):
            return normalize_text(v)
    return ""

def fuzzy_score(a: str, b: str) -> float:
    if not a or not b: return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def poss_merge(logger, sop, raw_path: Path, narr_path: Path, outdir: Path, thresh: float=0.72):
    logger.info(f"[poss_merge] raw={raw_path} narr={narr_path}")
    raw = read_csv(raw_path).copy()
    narr = read_csv(narr_path).copy()

    for col in ["SelectionTitle","Title","Code","Title_short"]:
        if col in raw.columns: raw[col] = raw[col].map(normalize_text)
    for col in ["OPM_Step","Source_File","Source_Title","Step_narr_in"]:
        if col in narr.columns: narr[col] = narr[col].map(normalize_text)

    raw_cols  = ["SelectionTitle","Title","Code","Title_short"]
    narr_cols = ["OPM_Step","Source_File","Source_Title","Step_narr_in"]
    extra_cols = ["Code-OPM_S","Match_conf"]

    for c in raw_cols:
        if c not in raw.columns: raw[c] = ""
    for c in narr_cols:
        if c not in narr.columns: narr[c] = ""

    narr_list = list(narr[["OPM_Step","Source_Title"]].itertuples(index=False, name=None))

    rows = []
    for _, r in raw.iterrows():
        row = {c: "" for c in raw_cols + narr_cols + extra_cols}
        for c in raw_cols: row[c] = r.get(c, "")
        code = normalize_text(r.get("Code",""))
        title = normalize_text(r.get("Title",""))
        tshort = normalize_text(r.get("Title_short",""))
        suggest_step, suggest_conf = "", ""

        if code and code[0].upper() in {"D","Y","N","M"}:
            logger.info(f"[poss_merge] skip fuzzy for Code='{code}' per rule")
        else:
            q = first_nonempty(title, tshort)
            best = (0.0, "")
            if q:
                for opm, stitle in narr_list:
                    sc = fuzzy_score(q, stitle)
                    if sc > best[0]:
                        best = (sc, opm)
                if best[0] >= thresh:
                    suggest_step = best[1]
                    suggest_conf = f"{best[0]:.3f}"
                    logger.info(f"[poss_merge] suggest {suggest_step} @ {suggest_conf} for Code={code} ({q})")
        row["Code-OPM_S"] = suggest_step
        row["Match_conf"] = suggest_conf
        rows.append(row)

    for _, n in narr.iterrows():
        row = {c: "" for c in raw_cols + narr_cols + extra_cols}
        for c in narr_cols: row[c] = n.get(c, "")
        rows.append(row)

    out_path = outdir / f"{sop}_poss_merge_{ts_now()}.csv"
    write_csv(pd.DataFrame(rows), out_path)
    logger.info(f"[poss_merge] wrote -> {out_path}")
    return out_path

def premerge(logger, sop, raw_path: Path, narr_path: Path, resp_poss_merge_path: Path, outdir: Path):
    logger.info(f"[premerge] raw={raw_path} narr={narr_path} resp={resp_poss_merge_path}")
    raw = read_csv(raw_path).copy()
    narr = read_csv(narr_path).copy()
    resp = read_csv(resp_poss_merge_path).copy()

    for df in (raw, resp):
        for c in ["Code","Title","Title_short"]:
            if c in df.columns: df[c] = df[c].map(normalize_text)

    for c in ["OPM_Step","Source_File","Source_Title","Step_narr_in","Step_narr_out_simple","Step_narr_out","Step_narr_m_out_simple","Step_narr_m_out"]:
        if c in narr.columns: narr[c] = narr[c].map(normalize_text)

    narr_by_step = {}
    for _, n in narr.iterrows():
        k = normalize_text(n.get("OPM_Step",""))
        if k and k not in narr_by_step:
            narr_by_step[k] = n

    mapping = {}
    if "Code-OPM_S" in resp.columns:
        resp_raw_only = resp[resp["Code"].notna() & (resp["Code"] != "")]
        for _, rr in resp_raw_only.iterrows():
            code = normalize_text(rr.get("Code",""))
            title = normalize_text(rr.get("Title",""))
            opm = normalize_text(rr.get("Code-OPM_S",""))
            if code:
                mapping.setdefault(code, {})[title] = opm

    out = raw.copy()
    for col in ["Narr1","Narr2","Narr3","OPM_Step","Source_Title_used"]:
        if col not in out.columns: out[col] = ""

    miss_map, used_map = 0, 0
    for idx, r in out.iterrows():
        code = normalize_text(r.get("Code",""))
        title = normalize_text(r.get("Title",""))
        opm = ""
        if code in mapping:
            opm = mapping[code].get(title) or next(iter(mapping[code].values()), "")
        if not opm:
            miss_map += 1
            continue

        if opm == "PM":
            src_title = "PM-selected"
            narr1 = src_title
            nrow = narr_by_step.get(opm)
            narr2 = normalize_text(nrow.get("Step_narr_m_out_simple","")) if nrow is not None else ""
            narr3 = normalize_text(nrow.get("Step_narr_m_out","")) if nrow is not None else ""
        else:
            nrow = narr_by_step.get(opm)
            if nrow is None:
                logger.warning(f"[premerge] No narr row for OPM_Step='{opm}' (Code={code}, Title={title})")
                miss_map += 1
                continue
            src_title = normalize_text(nrow.get("Source_Title",""))
            narr1 = src_title
            narr2 = normalize_text(nrow.get("Step_narr_out_simple",""))
            narr3 = normalize_text(nrow.get("Step_narr_out",""))

        out.at[idx, "OPM_Step"] = opm
        out.at[idx, "Source_Title_used"] = src_title
        out.at[idx, "Narr1"] = narr1
        out.at[idx, "Narr2"] = narr2
        out.at[idx, "Narr3"] = narr3
        used_map += 1

    out_path = outdir / f"{sop}_PreMerge_{ts_now()}.csv"
    write_csv(out, out_path)
    logger.info(f"[premerge] wrote -> {out_path}; mapped={used_map}, unmapped={miss_map}")
    return out_path

def tw_mk_in(logger, sop, premerge_path: Path, outdir: Path):
    logger.info(f"[tw_mk_in] premerge={premerge_path}")
    df = read_csv(premerge_path).copy()

    if "Source_Title" not in df.columns and "Source_Title_used" in df.columns:
        df["Source_Title"] = df["Source_Title_used"]

    cols = [
        "Source_PPT","SlideIndex","SelectionTitle","Title","Code","Title_short",
        "Image_sub_url","Deci_Question","Next1_Code","Next2_Code","match_code_OPM","OPM_Step",
        "Source_Title","Narr1","Narr2","Narr3","Disp_next1","Disp_next2","Disp_next3",
        "UAP url","UAP Label","start_here","Mismatch"
    ]

    out = pd.DataFrame()
    for c in cols:
        out[c] = df[c] if c in df.columns else ""

    out_path = outdir / f"{sop}_mk_tw_in_{ts_now()}.csv"
    write_csv(out, out_path)
    logger.info(f"[tw_mk_in] wrote -> {out_path}")
    return out_path

def main():
    ap = argparse.ArgumentParser(description="Generate transition files from raw + narr inputs.")
    ap.add_argument("--gen", required=True, choices=["poss_merge","premerge","tw_mk_in"], help="Stage to run")
    ap.add_argument("--sop", required=True, help="SOP code (e.g., SRO)")
    ap.add_argument("--raw", help="Path to SOP raw CSV (from PPT export)")
    ap.add_argument("--narr", help="Path to SOP_narr_latest.csv")
    ap.add_argument("--resp", help="Reviewed possible-merge CSV (SOP_Resp_poss_merge_*.csv)")
    ap.add_argument("--premerge", help="Path to enriched PreMerge CSV (for tw_mk_in)")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--thresh", type=float, default=0.72, help="Fuzzy match threshold for poss_merge (0..1)")
    args = ap.parse_args()

    outdir = Path(args.out)
    logger = setup_logger(outdir, args.sop)

    try:
        if args.gen == "poss_merge":
            if not (args.raw and args.narr):
                raise SystemExit("--gen poss_merge requires --raw and --narr")
            poss_merge(logger, args.sop, Path(args.raw), Path(args.narr), outdir, args.thresh)

        elif args.gen == "premerge":
            if not (args.raw and args.narr and args.resp):
                raise SystemExit("--gen premerge requires --raw, --narr and --resp")
            premerge(logger, args.sop, Path(args.raw), Path(args.narr), Path(args.resp), outdir)

        elif args.gen == "tw_mk_in":
            if not args.premerge:
                raise SystemExit("--gen tw_mk_in requires --premerge")
            tw_mk_in(logger, args.sop, Path(args.premerge), outdir)

        logger.info("Done.")
    except Exception as e:
        logger.exception(f"FAILED: {e}")
        raise

if __name__ == "__main__":
    main()
