#!/usr/bin/env python3
import argparse, json, csv, re, os
from datetime import datetime, timezone, timedelta

def bullets_to_paragraph(joined_text: str) -> str:
    # Take bullet-y text like "- Do thing\n- Next thing" and flatten it
    lines = []
    for line in joined_text.splitlines():
        line = line.strip()
        # strip common bullet markers
        line = re.sub(r'^[-•]\s*', '', line)
        if line:
            lines.append(line)
    para = " ".join(lines)
    # soften "/" to space (because we don't want slash in narration)
    para = para.replace("/", " ")
    # collapse whitespace
    para = re.sub(r"\s+", " ", para).strip()
    return para

def first_bullet_title(joined_text: str) -> str:
    # Use first non-empty bullet line as Source_Title
    for line in joined_text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r'^[-•]\s*', '', line)
        return line.strip()
    return ""

def normalize_whitespace(txt: str) -> str:
    # "Grade 8" placeholder: just make it one smooth readable paragraph
    txt = txt.strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt

def simplify_for_grade5(txt: str) -> str:
    # "Grade 5" placeholder:
    # break on sentence-ish boundaries, cap ~25 words per sentence,
    # then stitch back together as short sentences.
    parts = re.split(r"[.!?]+", txt)
    simple_bits = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        words = p.split()
        short_words = words[:25]  # cap length
        simple_bits.append(" ".join(short_words))
    out = ". ".join(simple_bits).strip()
    if out:
        out += "."
    return out

def build_narr_latest(data: dict, sop_name: str):
    """
    data is the parsed *_narr_files.json[5] with a top-level "files" list.
    sop_name is "SRO", "Warranty", etc.
    Returns a list of row dicts in final _narr_latest format.
    """
    files_list = data.get("files", [])

    rows = []
    all_step_narr_in = []

    # 1. Build P1..Pn
    for idx, fobj in enumerate(files_list, start=1):
        opm_step = f"P{idx}"

        src_file_full = (fobj.get("source_file","") or "").strip()
        src_file_base = os.path.basename(src_file_full)

        joined_text = (fobj.get("joined_text","") or "").strip()

        # Build Step_narr_in from bullets
        step_in = bullets_to_paragraph(joined_text)

        # Guess a "title" from first bullet line
        title_guess = first_bullet_title(joined_text)

        # "grade 8" and "grade 5" placeholders
        out_8 = normalize_whitespace(step_in)
        out_5 = simplify_for_grade5(step_in)

        row = {
            "OPM_Step": opm_step,
            "Source_File": src_file_base,
            "Source_Title": title_guess,
            "Step_narr_in": step_in,
            "Step_narr_m_in": "",              # BLANK for normal P-rows
            "Step_narr_out": out_8,
            "Step_narr_out_simple": out_5,
            "Step_narr_m_out": "",
            "Step_narr_m_out_simple": "",
        }
        rows.append(row)

        if step_in:
            all_step_narr_in.append(step_in)

    # 2. Build PM row
    mega = " ".join(all_step_narr_in).strip()
    mega = re.sub(r"\s+", " ", mega)

    pm_row = {
        "OPM_Step": "PM",
        "Source_File": "",
        "Source_Title": "Process Overview",
        "Step_narr_in": "",           # MUST stay empty for PM
        "Step_narr_m_in": mega,       # roll-up of all P Step_narr_in text
        "Step_narr_out": "",
        "Step_narr_out_simple": "",
        "Step_narr_m_out": normalize_whitespace(mega),
        "Step_narr_m_out_simple": simplify_for_grade5(mega),
    }
    rows.append(pm_row)

    return rows

def write_csv(rows, out_csv_path):
    fieldnames = [
        "OPM_Step",
        "Source_File",
        "Source_Title",
        "Step_narr_in",
        "Step_narr_m_in",
        "Step_narr_out",
        "Step_narr_out_simple",
        "Step_narr_m_out",
        "Step_narr_m_out_simple",
    ]
    with open(out_csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json5-in", required=True,
                    help="Path to <SOP>_narr_files.json or .json5 from make_sop_nar_json_v6.py")
    ap.add_argument("--sop", required=True,
                    help='Short SOP code like "SRO", "Warranty", etc.')
    ap.add_argument("--out-dir", required=True,
                    help="Folder where *_narr_latest_<timestamp>.csv and *_narr_latest.csv go")
    args = ap.parse_args()

    # load narration summary json/json5
    with open(args.json5_in, "r", encoding="utf-8") as f:
        narr_data = json.load(f)

    # build rows
    rows = build_narr_latest(narr_data, args.sop)

    # timestamp in Eastern-ish (we'll approximate with UTC-4 unless you add zoneinfo)
    now_est = datetime.utcnow() - timedelta(hours=4)
    ts = now_est.strftime("%m%d%y_%H%M")

    os.makedirs(args.out_dir, exist_ok=True)
    out_ts = os.path.join(args.out_dir, f"{args.sop}_narr_latest_{ts}.csv")
    out_latest = os.path.join(args.out_dir, f"{args.sop}_narr_latest.csv")

    write_csv(rows, out_ts)
    write_csv(rows, out_latest)

    print(f"Wrote {out_ts}")
    print(f"Wrote {out_latest}")
    print(f"Rows: {len(rows)} (including PM)")

if __name__ == "__main__":
    main()
