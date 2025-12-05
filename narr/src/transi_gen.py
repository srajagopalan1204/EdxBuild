#!/usr/bin/env python3
import os, re, glob, argparse, math
import pandas as pd
from difflib import SequenceMatcher
from datetime import datetime
import pytz

NY_TZ = pytz.timezone("America/New_York")

def ts_stamp():
    return datetime.now(NY_TZ).strftime("%d%m%y_%H%M")

def ensure_dir(d):
    os.makedirs(d, exist_ok=True)
    return d

def load_raw(path_csv: str) -> pd.DataFrame:
    df = pd.read_csv(path_csv, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    return df

def load_table(path: str, sheet=0) -> pd.DataFrame:
    if path.lower().endswith(".xlsx"):
        df = pd.read_excel(path, sheet_name=sheet, dtype=str).fillna("")
    else:
        df = pd.read_csv(path, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    return df

def discover_latest(patterns):
    cand = []
    for pat in patterns:
        cand.extend(glob.glob(pat))
    if not cand:
        return None
    cand.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return cand[0]

# --- Text normalization for fuzzy ---
PUNCT_RE = re.compile(r"[^\w\s]")
def strip_codes(text: str) -> str:
    s = str(text or "")
    s = re.sub(r"^\s*([A-Za-z]\d+[a-z]?)\s*[:\-–—]\s*", "", s)
    s = re.sub(r"\[[A-Za-z]\d+[a-z]?\]", " ", s)
    s = re.sub(r"\b[A-Za-z]\d+[a-z]?\b", " ", s)
    s = s.replace("_"," ").replace("-"," ")
    s = PUNCT_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def sim(a,b):
    return SequenceMatcher(None, strip_codes(a), strip_codes(b)).ratio()

LEAD_CODE_RE = re.compile(r"^\s*([A-Za-z]\d+[a-z]?)\b")
def lead_code_token(s: str) -> str:
    m = LEAD_CODE_RE.match(str(s or ""))
    return m.group(1).upper() if m else ""

def pick_col(df, names):
    for n in names:
        for c in df.columns:
            if c.strip().lower() == n.lower():
                return c
    return None

# ---- MANUAL (mapping workbook with suggestions) ----
def build_manual_autofill(raw_path, narr_path, out_dir, thresh=0.80, ignore_prefixes=("D","N","Y"), sheet=0):
    df_raw = load_raw(raw_path)
    df_narr = load_table(narr_path, sheet=sheet)
    for c in ["Code","OPM_Step","Source_Title","Step_narr_out_simple"]:
        if c not in df_narr.columns: df_narr[c] = ""

    mask_keep = ~df_narr["Code"].astype(str).str.upper().str.match(rf"^[{''.join(ignore_prefixes)}]")
    df_cand = df_narr[mask_keep].copy()
    match_col = "Source_Title" if "Source_Title" in df_cand.columns else "OPM_Step"
    cand_text = df_cand[match_col].astype(str)
    cand_dict = dict(cand_text.items())

    rows = []
    for _, r in df_raw.iterrows():
        raw_title = str(r.get("Title",""))
        best_idx, best_score = None, 0.0
        if raw_title.strip():
            for j, txt in cand_dict.items():
                score = sim(raw_title, txt)
                if score > best_score:
                    best_idx, best_score = j, score
        sel_code = str(df_cand.at[best_idx, "Code"]) if (best_idx is not None and best_score >= thresh) else ""
        conf = int(math.ceil((best_score or 0)*100))
        rows.append({
            "Code": str(r.get("Code","")),
            "OPM_Step": "",
            "Title": raw_title,
            "Source_Title": "",
            "match_code_OPM": sel_code,
            "Match_Conf": conf
        })
    map_df = pd.DataFrame(rows)
    lookup_df = df_narr[["Code","OPM_Step","Source_Title","Step_narr_out_simple"]].copy()
    ensure_dir(out_dir)
    out_xlsx = os.path.join(out_dir, f"Manual_Match_{ts_stamp()}_autofill.xlsx")
    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        map_df.to_excel(writer, index=False, sheet_name="Map_Entries")
        lookup_df.to_excel(writer, index=False, sheet_name="OPM_Code_Lookup")
        wb  = writer.book
        wsM = writer.sheets["Map_Entries"]
        last_row_lookup = len(lookup_df) + 1
        wb.define_name("OPM_Code_Lookup", f"=OPM_Code_Lookup!$A$1:$D${last_row_lookup}")
        nrows = len(map_df)
        for r in range(2, nrows+2):
            f_opm = '=IF($E{row}="","",IFERROR(VLOOKUP($E{row}, OPM_Code_Lookup, 2, FALSE), ""))'.format(row=r)
            f_src = '=IF($E{row}="","",IFERROR(VLOOKUP($E{row}, OPM_Code_Lookup, 3, FALSE), ""))'.format(row=r)
            wsM.write_formula(r-1, 1, f_opm)  # OPM_Step
            wsM.write_formula(r-1, 3, f_src)  # Source_Title
    return out_xlsx

# ---- TWEE (legacy path: mapping -> mk_tw input XLSX) ----
def build_twee_from_map(raw_path, narr_path, map_path, out_dir, sheet=0):
    df_raw = load_raw(raw_path)
    df_narr = load_table(narr_path, sheet=sheet)
    for c in ["Code","OPM_Step","Source_Title","Step_narr_out","Step_narr_out_simple","Step_narr_m_out","Step_narr_m_out_simple"]:
        if c not in df_narr.columns: df_narr[c] = ""

    df_map = load_table(map_path, sheet=0)
    col_match = pick_col(df_map, ["match_code_OPM","match_code","selected_code","opm_code","chosen_code","OPM_Step"])
    if col_match is None:
        df_map["_match_code"] = ""
    else:
        df_map["_match_code"] = df_map[col_match].apply(lead_code_token)

    join_cols = [k for k in ["Code","Title"] if k in df_raw.columns and k in df_map.columns]
    if join_cols:
        df_join = df_raw.merge(df_map[join_cols + ["_match_code"]], on=join_cols, how="left")
    else:
        df_join = df_raw.copy()
        df_join["_match_code"] = df_map["_match_code"] if len(df_map)==len(df_raw) else ""

    df_merged = df_join.merge(df_narr, left_on="_match_code", right_on="Code", how="left", suffixes=("","_narr"))

    def questionize(title: str) -> str:
        t = (title or "").strip()
        if not t: return ""
        t = re.sub(r"[.?!\s]+$", "", t)
        if not t.endswith("?"): t += "?"
        return t
    def narr_from_title_prefix(title: str) -> str:
        t = str(title or "")
        parts = re.split(r"\s[–-]\s", t, maxsplit=1)
        return parts[0].strip()

    rows = []
    for _, r in df_merged.iterrows():
        raw_code = str(r.get("Code",""))
        raw_title = str(r.get("Title",""))
        opm_code = str(r.get("_match_code",""))
        opm_step = str(r.get("OPM_Step",""))
        lead = lead_code_token(opm_step) or lead_code_token(opm_code)
        narr1 = narr2 = narr3 = ""
        if lead.startswith("D"):
            narr1 = questionize(raw_title)
        elif lead.startswith("Y") or lead.startswith("N"):
            narr1 = narr_from_title_prefix(raw_title)
        else:
            narr1 = str(r.get("Step_narr_out_simple","")) or raw_title
            if "M" in (lead or ""):
                narr2 = str(r.get("Step_narr_m_out_simple",""))
                narr3 = str(r.get("Step_narr_m_out",""))
        rows.append({
            "Code": raw_code,
            "Title": raw_title,
            "match_code_OPM": opm_code,
            "OPM_Step": opm_step,
            "Source_Title": str(r.get("Source_Title","")),
            "Narr1": narr1,
            "Narr2": narr2,
            "Narr3": narr3
        })
    df_out = pd.DataFrame(rows)
    raw_tail = [c for c in df_raw.columns if c not in ["Code","Title"]]
    df_mk = df_out[["Code","match_code_OPM","Title","Source_Title","Narr1","Narr2","Narr3"]].merge(
        df_raw[["Code"]+raw_tail], on="Code", how="left"
    )
    ensure_dir(out_dir)
    out_xlsx = os.path.join(out_dir, f"mk_tw_in_{ts_stamp()}.xlsx")
    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        df_mk.to_excel(writer, index=False, sheet_name="mk_tw_in")
    return out_xlsx

# ---- PREMERGE (new) ----
def first_half_title(title: str) -> str:
    t = str(title or "")
    if " – " in t:
        return t.split(" – ", 1)[0].strip()
    if " - " in t:
        return t.split(" - ", 1)[0].strip()
    return t.strip()

def premerge_build(raw_path, narr_path, resp_transi_in, out_dir, sop, sheet=0):
    df_raw = load_raw(raw_path)
    df_narr = load_table(narr_path, sheet=sheet)
    for c in ["Code","OPM_Step","Source_Title","Step_narr_out","Step_narr_out_simple","Step_narr_m_out","Step_narr_m_out_simple"]:
        if c not in df_narr.columns: df_narr[c] = ""

    opm_to_idx = {str(v): i for i, v in df_narr["OPM_Step"].astype(str).items()}
    code_to_idx = {str(v).upper(): i for i, v in df_narr["Code"].astype(str).items()}

    code_to_match = {}
    if resp_transi_in and os.path.exists(resp_transi_in):
        df_resp = load_table(resp_transi_in, sheet=0)
        col_code  = pick_col(df_resp, ["CODE","Code"])
        col_match = pick_col(df_resp, ["Match","match_code_OPM","selected_code","opm_code"])
        col_opm   = pick_col(df_resp, ["OPM_Step","OPM step","opm_step"])
        if col_code:
            for _, r in df_resp.iterrows():
                raw_code = str(r.get(col_code,"")).strip()
                if not raw_code: 
                    continue
                mval = str(r.get(col_match,"")).strip() if col_match else ""
                oval = str(r.get(col_opm,"")).strip() if col_opm else ""
                code_to_match[raw_code] = mval if mval else oval

    raw_title_by_code = {str(r.get("Code","")).strip(): str(r.get("Title","")) for _, r in df_raw.iterrows()}

    def narr_fields_from_match(match_val: str):
        opm_step = ""
        code = ""
        src = ""
        narr2 = ""
        narr3 = ""
        if not match_val:
            return opm_step, code, src, narr2, narr3
        mcode = lead_code_token(match_val)
        if mcode and mcode in code_to_idx:
            idx = code_to_idx[mcode]
            row = df_narr.loc[idx]
            opm_step = str(row.get("OPM_Step",""))
            code = str(row.get("Code",""))
            src = str(row.get("Source_Title",""))
            lead = lead_code_token(opm_step) or lead_code_token(code)
            if lead.startswith("M"):
                narr2 = str(row.get("Step_narr_m_out_simple",""))
                narr3 = str(row.get("Step_narr_m_out",""))
            else:
                narr2 = str(row.get("Step_narr_out_simple",""))
                narr3 = str(row.get("Step_narr_out",""))
            return opm_step, code, src, narr2, narr3
        if match_val in opm_to_idx:
            idx = opm_to_idx[match_val]
            row = df_narr.loc[idx]
            opm_step = str(row.get("OPM_Step",""))
            code = str(row.get("Code",""))
            src = str(row.get("Source_Title",""))
            lead = lead_code_token(opm_step) or lead_code_token(code)
            if lead.startswith("M"):
                narr2 = str(row.get("Step_narr_m_out_simple",""))
                narr3 = str(row.get("Step_narr_m_out",""))
            else:
                narr2 = str(row.get("Step_narr_out_simple",""))
                narr3 = str(row.get("Step_narr_out",""))
        return opm_step, code, src, narr2, narr3

    rows = []
    for _, rr in df_raw.iterrows():
        rcode = str(rr.get("Code","")).strip()
        rtitle = str(rr.get("Title",""))
        match_val = code_to_match.get(rcode, "")
        opm_step, ncode, src, narr2, narr3 = narr_fields_from_match(match_val)
        narr1 = first_half_title(rtitle)

        next1 = str(rr.get("next1_code","")).strip() if "next1_code" in df_raw.columns else ""
        next2 = str(rr.get("next2_code","")).strip() if "next2_code" in df_raw.columns else ""
        next3 = str(rr.get("next3_code","")).strip() if "next3_code" in df_raw.columns else ""

        disp1 = raw_title_by_code.get(next1, "") if next1 else ""
        disp2 = raw_title_by_code.get(next2, "") if next2 else ""
        disp3 = raw_title_by_code.get(next3, "") if next3 else ""

        row = {**{c: str(rr.get(c,"")) for c in df_raw.columns},
            "match_code_OPM": ncode,
            "OPM_Step": opm_step,
            "Source_Title": src,
            "Narr1": narr1,
            "Narr2": narr2,
            "Narr3": narr3,
            "Disp_next1": disp1,
            "Disp_next2": disp2,
            "Disp_next3": disp3,
            "UAP url": "",
            "UAP Label": "",
            "start_here": "No",
            "Mismatch": "No",
        }
        rows.append(row)
    df_pre = pd.DataFrame(rows)

    ensure_dir(out_dir)
    base = os.path.join(out_dir, f"{sop}_PreMerge_{ts_stamp()}")
    csv_path = base + ".csv"
    xlsx_path = base + ".xlsx"
    df_pre.to_csv(csv_path, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        df_pre.to_excel(writer, index=False, sheet_name="PreMerge")
    return csv_path, xlsx_path

# ---- MK-TW-IN (new): consumes resp_merge, logs changes, emits mk_tw_in ----
def diff_and_apply(premerge_csv, resp_merge_csv, out_dir, sop):
    df_pre = load_table(premerge_csv)
    df_resp = load_table(resp_merge_csv)

    # Normalize key and columns
    key = "Code" if "Code" in df_pre.columns else ("CODE" if "CODE" in df_pre.columns else None)
    if key is None:
        raise ValueError("PreMerge must include 'Code' or 'CODE' column.")

    pre_by_code = df_pre.set_index(key, drop=False)
    resp_by_code = df_resp.set_index(key, drop=False) if key in df_resp.columns else pd.DataFrame()

    changed_rows = []
    out_rows = []
    all_cols = list(df_pre.columns)

    for code, prow in pre_by_code.iterrows():
        orow = prow.copy()
        if code in resp_by_code.index:
            rrow = resp_by_code.loc[code]
            if isinstance(rrow, pd.DataFrame):
                rrow = rrow.iloc[0]
            for c in df_resp.columns:
                if c == key:
                    continue
                if c in all_cols:
                    val = str(rrow.get(c,""))
                    if str(val).strip() != "" and str(orow.get(c,"")) != str(val):
                        changed_rows.append({"Code": code, "Field": c, "From": str(orow.get(c,"")), "To": str(val)})
                        orow[c] = val
            if any(ch["Code"] == code for ch in changed_rows):
                orow["Mismatch"] = "Yes"
        out_rows.append(orow)

    df_out = pd.DataFrame(out_rows, columns=all_cols)
    df_changes = pd.DataFrame(changed_rows, columns=["Code","Field","From","To"])

    ensure_dir(out_dir)
    base = os.path.join(out_dir, f"{sop}_mk_tw_in_{ts_stamp()}")
    df_out.to_csv(base + ".csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(base + ".xlsx", engine="xlsxwriter") as writer:
        df_out.to_excel(writer, index=False, sheet_name="mk_tw_in")
        if not df_changes.empty:
            df_changes.to_excel(writer, index=False, sheet_name="ChangeLog")
    return base + ".csv", base + ".xlsx", (df_changes if not df_changes.empty else None)

def main():
    parser = argparse.ArgumentParser(description="Transi/Narr pipeline generator")
    parser.add_argument("--gen", choices=["manual","twee","premerge","mk-tw-in"], required=True, help="Which stage to generate")
    parser.add_argument("--sop", default="Tech", help="SOP code (e.g., Tech)")
    parser.add_argument("--raw", required=False, help="Path to RAW CSV")
    parser.add_argument("--narr", required=False, help="Path to Narration CSV/XLSX")
    parser.add_argument("--narr-sheet", default="0", help="Narration sheet name or index (default 0)")
    parser.add_argument("--map", required=False, help="(twee/manual) Mapping CSV/XLSX")
    parser.add_argument("--out", required=False, help="Output directory")
    parser.add_argument("--thresh", type=float, default=0.80, help="Manual suggestion threshold")
    parser.add_argument("--ignore-codes-prefix", default="D,N,Y", help="Prefixes to ignore in manual suggestions (comma-separated)")
    parser.add_argument("--resp-transi-in", required=False, help="(premerge) resp_transi_in CSV from user")
    parser.add_argument("--premerge", required=False, help="(mk-tw-in) PreMerge CSV path")
    parser.add_argument("--resp-merge", required=False, help="(mk-tw-in) User-edited resp_merge CSV path")

    args = parser.parse_args()

    base_root = "/workspaces/son_e_lum/narr"
    if not args.raw:
        args.raw = discover_latest([os.path.join(base_root, "Inputs", args.sop, "raw", "*.csv")]) or args.raw
    if not args.narr:
        args.narr = discover_latest([os.path.join(base_root, "Outputs", args.sop, f"{args.sop}_Narr_*.*"),
                                     os.path.join(base_root, "Outputs", args.sop, "*Narr_latest.*")])
    if not args.out:
        args.out = os.path.join(base_root, "Outputs", args.sop, "transi")
    ensure_dir(args.out)

    try:
        narr_sheet = int(args.narr_sheet)
    except:
        narr_sheet = args.narr_sheet

    if args.gen == "manual":
        ignore_prefixes = tuple([p.strip().upper() for p in args.ignore_codes_prefix.split(",") if p.strip()])
        out = build_manual_autofill(args.raw, args.narr, args.out, thresh=args.thresh, ignore_prefixes=ignore_prefixes, sheet=narr_sheet)
        print(out)
    elif args.gen == "twee":
        if not args.map:
            raise ValueError("--map is required for --gen twee")
        out = build_twee_from_map(args.raw, args.narr, args.map, args.out, sheet=narr_sheet)
        print(out)
    elif args.gen == "premerge":
        csvp, xlsp = premerge_build(args.raw, args.narr, args.resp_transi_in, args.out, args.sop, sheet=narr_sheet)
        print(csvp)
        print(xlsp)
    else:  # mk-tw-in
        if not args.premerge or not args.resp_merge:
            raise ValueError("--premerge and --resp-merge are required for --gen mk-tw-in")
        csvp, xlsp, changes = diff_and_apply(args.premerge, args.resp_merge, args.out, args.sop)
        print(csvp)
        print(xlsp)

if __name__ == "__main__":
    main()
