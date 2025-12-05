#!/usr/bin/env python3
# EdxBuild Narration – transi_gen_new.py
# Version: 20251205_1000  (America/New_York)
# Authors: Subi Rajagopalan   with assistance from ChatGPT (OpenAI)
#
# USE (examples):
#   python /workspaces/EdxBuild/narr/src/transi_gen_new.py \
#       --gen poss_merge \
#       --sop LineEnt \
#       --raw "/workspaces/EdxBuild/narr/Inputs/LineEnt/LineEnt_raw.csv" \
#       --narr "/workspaces/EdxBuild/narr/Outputs/LineEnt/LineEnt_narr_latest.csv" \
#       --out "/workspaces/EdxBuild/narr/Outputs/LineEnt"
#
#   python /workspaces/EdxBuild/narr/src/transi_gen_new.py \
#       --gen premerge \
#       --sop LineEnt \
#       --raw "/workspaces/EdxBuild/narr/Inputs/LineEnt/LineEnt_raw.csv" \
#       --narr "/workspaces/EdxBuild/narr/Outputs/LineEnt/LineEnt_narr_latest.csv" \
#       --resp "/workspaces/EdxBuild/narr/Outputs/LineEnt/LineEnt_Resp_poss_merge_latest.csv" \
#       --out "/workspaces/EdxBuild/narr/Outputs/LineEnt"
#
#   python /workspaces/EdxBuild/narr/src/transi_gen_new.py \
#       --gen tw_mk_in \
#       --sop LineEnt \
#       --premerge "/workspaces/EdxBuild/narr/Outputs/LineEnt/LineEnt_PreMerge_latest.csv" \
#       --out "/workspaces/EdxBuild/narr/Outputs/LineEnt"
#

import argparse
import sys
import re
import logging
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd

TS_FMT = "%m%d%y_%H%M"  # MMDDYY_HHMM


def ts_now() -> str:
    return datetime.now().strftime(TS_FMT)


def setup_logger(outdir: Path, sop: str):
    outdir.mkdir(parents=True, exist_ok=True)
    log_path = outdir / f"{sop}_transi_gen_{ts_now()}.log"
    logger = logging.getLogger("transi_gen")
    logger.setLevel(logging.INFO)
    logger.handlers = []
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.info(f"Logging to {log_path}")
    return logger


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8")


def write_csv(df: pd.DataFrame, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")


def normalize_text(s) -> str:
    if pd.isna(s):
        return ""
    s = str(s)
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def fuzzy_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# poss_merge
# ---------------------------------------------------------------------------
def poss_merge(logger, sop: str, raw_path: Path, narr_path: Path, outdir: Path) -> Path:
    logger.info(f"[poss_merge] raw={raw_path} narr={narr_path}")
    raw = read_csv(raw_path).copy()
    narr = read_csv(narr_path).copy()

    # Build lookup from OPM_Step (normalized) -> narr row
    narr_by_opm = {}
    for _, n in narr.iterrows():
        opm_orig = n.get("OPM_Step", "")
        opm_key = normalize_text(opm_orig)
        if opm_key and opm_key not in narr_by_opm:
            narr_by_opm[opm_key] = n

    # Build lookup from Step_Code (normalized) -> OPM key (normalized)
    step_by_code = {}
    for _, n in narr.iterrows():
        opm_orig = n.get("OPM_Step", "")
        opm_key = normalize_text(opm_orig)
        code_orig = n.get("Step_Code", "")
        code_key = normalize_text(code_orig)
        if opm_key and code_key and code_key not in step_by_code:
            step_by_code[code_key] = opm_key

    raw_cols = list(raw.columns)
    narr_cols = [
        "OPM_Step",
        "Source_File",
        "Source_Title",
        "Step_narr_in",
        "Step_narr_out_simple",
        "Step_narr_out",
        "Step_narr_m_out_simple",
        "Step_narr_m_out",
        "Step_Code",
        "Oth1",
        "Oth2",
        "UAP url",
        "UAP Label",
    ]
    extra_cols = ["Code-OPM_S", "Match_conf"]

    rows = []

    # For each raw row, propose an OPM step
    for _, r in raw.iterrows():
        code_raw = r.get("Code", "")
        title_raw = r.get("Title", "")
        title_short_raw = r.get("Title_short", "")

        code_key = normalize_text(code_raw)
        title_key = normalize_text(title_raw)
        title_short_key = normalize_text(title_short_raw)

        best_opm_key = ""
        best_conf = 0.0

        # 1) Code-based match (preferred)
        if code_key and code_key in step_by_code:
            best_opm_key = step_by_code[code_key]
            best_conf = 1.0
        else:
            # 2) Fuzzy match on Title / Title_short
            for opm_key, n in narr_by_opm.items():
                src_title = n.get("Source_Title", "")
                joined = n.get("Step_narr_in", "")
                cand = normalize_text(f"{src_title} {joined}")

                r1 = fuzzy_ratio(title_key, cand)
                r2 = fuzzy_ratio(title_short_key, cand) if title_short_key else 0.0
                ratio = max(r1, r2)

                if ratio > best_conf:
                    best_conf = ratio
                    best_opm_key = opm_key

        # Build combined row
        row = {c: r.get(c, "") for c in raw_cols}
        for c in narr_cols:
            row[c] = ""

        if best_opm_key and best_opm_key in narr_by_opm:
            n = narr_by_opm[best_opm_key]
            row["Code-OPM_S"] = n.get("OPM_Step", "")  # original OPM_Step (P1, P2...)
            row["Match_conf"] = best_conf
        else:
            row["Code-OPM_S"] = ""
            row["Match_conf"] = 0.0

        rows.append(row)

    # Append a narr-only block so any steps with no raw usage are visible
    for _, n in narr.iterrows():
        row = {c: "" for c in raw_cols + narr_cols + extra_cols}
        for c in narr_cols:
            row[c] = n.get(c, "")
        rows.append(row)

    out_path = outdir / f"{sop}_poss_merge_{ts_now()}.csv"
    write_csv(pd.DataFrame(rows), out_path)
    logger.info(f"[poss_merge] wrote -> {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# premerge
# ---------------------------------------------------------------------------
def premerge(
    logger,
    sop: str,
    raw_path: Path,
    narr_path: Path,
    resp_poss_merge_path: Path,
    outdir: Path,
) -> Path:
    logger.info(
        f"[premerge] raw={raw_path} narr={narr_path} resp={resp_poss_merge_path}"
    )
    raw = read_csv(raw_path).copy()
    narr = read_csv(narr_path).copy()
    resp = read_csv(resp_poss_merge_path).copy()

    # Index narration by OPM_Step (normalized)
    narr_by_opm = {}
    for _, n in narr.iterrows():
        opm_orig = n.get("OPM_Step", "")
        opm_key = normalize_text(opm_orig)
        if opm_key and opm_key not in narr_by_opm:
            narr_by_opm[opm_key] = n

    # Build mapping from (Code, Title) -> OPM key (normalized) from reviewed poss_merge
    mapping = {}
    if "Code-OPM_S" in resp.columns:
        resp_raw_only = resp[resp["Code"].notna() & (resp["Code"] != "")]
        for _, rr in resp_raw_only.iterrows():
            code_key = normalize_text(rr.get("Code", ""))
            title_key = normalize_text(rr.get("Title", ""))
            opm_key = normalize_text(rr.get("Code-OPM_S", ""))
            if not code_key or not opm_key:
                continue
            mapping.setdefault(code_key, {})[title_key] = opm_key

    out = raw.copy()

    # Ensure all needed columns exist
    base_cols = [
        "Narr1",
        "Narr2",
        "Narr3",
        "OPM_Step",
        "Source_Title_used",
        "Disp_next1",
        "Disp_next2",
        "Disp_next3",
        "Step_Code",
        "Oth1",
        "Oth2",
        "UAP url",
        "UAP Label",
        "start_here",
    ]
    for col in base_cols:
        if col not in out.columns:
            out[col] = ""

    miss_map, used_map = 0, 0

    for idx, r in out.iterrows():
        code_raw = r.get("Code", "")
        title_raw = r.get("Title", "")
        title_short_raw = r.get("Title_short", "")

        code_key = normalize_text(code_raw)
        title_key = normalize_text(title_raw)
        title_short_key = normalize_text(title_short_raw)

        opm_key = ""

        if code_key and code_key in mapping:
            # Prefer exact Title match, then Title_short, then any
            if title_key in mapping[code_key]:
                opm_key = mapping[code_key][title_key]
            elif title_short_key in mapping[code_key]:
                opm_key = mapping[code_key][title_short_key]
            else:
                # fallback: first mapping for that code
                opm_key = next(iter(mapping[code_key].values()))

        if not opm_key:
            miss_map += 1
            continue

        nrow = narr_by_opm.get(opm_key)
        if nrow is None:
            logger.warning(
                f"[premerge] No narr row for OPM key='{opm_key}' (Code={code_raw}, Title={title_raw})"
            )
            miss_map += 1
            continue

        opm_display = nrow.get("OPM_Step", "")
        src_title = nrow.get("Source_Title", "")

        if opm_display == "PM":
            narr1 = "PM-selected"
            narr2 = nrow.get("Step_narr_m_out_simple", "")
            narr3 = nrow.get("Step_narr_m_out", "")
        else:
            narr1 = src_title
            narr2 = nrow.get("Step_narr_out_simple", "")
            narr3 = nrow.get("Step_narr_out", "")

        out.at[idx, "OPM_Step"] = opm_display
        out.at[idx, "Source_Title_used"] = src_title
        out.at[idx, "Narr1"] = narr1
        out.at[idx, "Narr2"] = narr2
        out.at[idx, "Narr3"] = narr3

        # Carry metadata from narr_latest
        out.at[idx, "Step_Code"] = nrow.get("Step_Code", "")
        out.at[idx, "Oth1"] = nrow.get("Oth1", "")
        out.at[idx, "Oth2"] = nrow.get("Oth2", "")
        out.at[idx, "UAP url"] = nrow.get("UAP url", "")
        out.at[idx, "UAP Label"] = nrow.get("UAP Label", "")

        used_map += 1

    # Default all start_here flags to 'No'
    out["start_here"] = "No"

    out_path = outdir / f"{sop}_PreMerge_{ts_now()}.csv"
    write_csv(out, out_path)
    logger.info(
        f"[premerge] wrote -> {out_path}; mapped={used_map}, unmapped={miss_map}"
    )
    return out_path


# ---------------------------------------------------------------------------
# tw_mk_in
# ---------------------------------------------------------------------------
def tw_mk_in(logger, sop: str, premerge_path: Path, outdir: Path) -> Path:
    logger.info(f"[tw_mk_in] premerge={premerge_path}")
    df = read_csv(premerge_path).copy()

    if "Source_Title" not in df.columns and "Source_Title_used" in df.columns:
        df["Source_Title"] = df["Source_Title_used"]

    cols = [
        "Source_PPT",
        "SlideIndex",
        "SelectionTitle",
        "Title",
        "Code",
        "Title_short",
        "Image_sub_url",
        "Deci_Question",
        "Next1_Code",
        "Next2_Code",
        "match_code_OPM",
        "OPM_Step",
        "Source_Title",
        "Narr1",
        "Narr2",
        "Narr3",
        "Disp_next1",
        "Disp_next2",
        "Disp_next3",
        "UAP url",
        "UAP Label",
        "start_here",
        "Mismatch",
        "Oth1",
        "Oth2",
    ]

    out = pd.DataFrame()
    for c in cols:
        out[c] = df[c] if c in df.columns else ""

    out_path = outdir / f"{sop}_mk_tw_in_{ts_now()}.csv"
    write_csv(out, out_path)
    logger.info(f"[tw_mk_in] wrote -> {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Generate transition files from raw + narr inputs."
    )
    ap.add_argument(
        "--gen",
        required=True,
        choices=["poss_merge", "premerge", "tw_mk_in"],
        help="Stage to run",
    )
    ap.add_argument("--sop", required=True, help="SOP code (e.g., SRO, LineEnt)")
    ap.add_argument("--raw", help="Path to SOP raw CSV (from PPT export)")
    ap.add_argument("--narr", help="Path to SOP_narr_latest.csv")
    ap.add_argument("--resp", help="Reviewed poss_merge CSV (SOP_Resp_poss_merge_*.csv)")
    ap.add_argument("--premerge", help="Path to enriched PreMerge CSV (for tw_mk_in)")
    ap.add_argument("--out", required=True, help="Output directory")
    args = ap.parse_args()

    outdir = Path(args.out)
    logger = setup_logger(outdir, args.sop)

    try:
        if args.gen == "poss_merge":
            if not (args.raw and args.narr):
                raise SystemExit("--gen poss_merge requires --raw and --narr")
            poss_merge(logger, args.sop, Path(args.raw), Path(args.narr), outdir)

        elif args.gen == "premerge":
            if not (args.raw and args.narr and args.resp):
                raise SystemExit("--gen premerge requires --raw, --narr, and --resp")
            premerge(
                logger,
                args.sop,
                Path(args.raw),
                Path(args.narr),
                Path(args.resp),
                outdir,
            )

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
