#!/usr/bin/env python3
# EdxBuild Narration – build_narr_latest_v3.py
# Version: 20251205_0900  (America/New_York)
# Authors: Subi Rajagopalan   with assistance from ChatGPT (OpenAI)
#
# USE (example):
#   python /workspaces/EdxBuild/narr/src/build_narr_latest_v3.py \
#       --json5-in "/workspaces/EdxBuild/narr/Outputs/LineEnt/LineEnt_narr_files.json5" \
#       --sop "LineEnt" \
#       --out-dir "/workspaces/EdxBuild/narr/Outputs/LineEnt"
#
import argparse, json, csv, re, os
from datetime import datetime, timedelta

# ---------- helper: cut off tail config block (invalid JSON5 keys) ----------
def trim_after_config_block(full_text: str) -> str:
    marker = "===== BEGIN DEFAULT NARR CONFIG"
    idx = full_text.find(marker)
    if idx == -1:
        return full_text

    kept = full_text[:idx]

    kept = kept.rstrip(", \n\r\t")

    if not kept.rstrip().endswith("}"):
        return full_text

    return kept + "\n}\n"

# ---------- helpers for JSON5-ish to JSON ----------
def strip_json5_comments(text: str) -> str:
    out_lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("//"):
            continue
        out_lines.append(line)
    return "\n".join(out_lines)

def load_json5(path: str) -> dict:
    raw = open(path, "r", encoding="utf-8").read()
    raw = trim_after_config_block(raw)
    raw = strip_json5_comments(raw)
    return json.loads(raw)

# ---------- text shaping helpers ----------
def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def simplify_for_grade5(text: str) -> str:
    """
    Heuristic: turn long bullet text into shorter "do this" steps
    aimed at roughly 5th grade reading level.
    """
    if not text:
        return ""

    lines = [normalize_whitespace(ln) for ln in text.splitlines() if normalize_whitespace(ln)]
    cleaned_steps = []

    for ln in lines:
        # strip leading bullet marks
        ln = re.sub(r"^[\-•]\s*", "", ln)

        # split on sentence enders, keep first clause
        parts = re.split(r"[.!?]+", ln)
        chunk = parts[0].strip() if parts else ""
        if not chunk:
            continue

        # cap length ~20 words
        words = chunk.split()
        words = words[:20]
        short = " ".join(words)

        # Capitalize for readability
        if short:
            short = short[0].upper() + short[1:]

        cleaned_steps.append(short)

    out = ". ".join(cleaned_steps).strip()
    if out and not out.endswith("."):
        out += "."
    return out

# ---------- build ordered rows from narr_data ----------
def build_rows(narr_data: dict):
    """
    Returns:
    [
      { "opm_step": "P1", "src_file": "...", "title": "...", "step_in": "..." },
      ...
    ]

    Supports:
    - SRO-style narr_data["files"][i] = {"source_file","joined_text",...}
    - Warranty-style narr_data["extraction"]["files"][i] as emitted by make_sop_nar_json_v6
    """

    rows_ordered = []

    if "files" in narr_data:
        # SRO-style: files array of {"source_file","joined_text"}
        for idx, fobj in enumerate(narr_data.get("files", []), start=1):
            src_file = fobj.get("source_file") or fobj.get("file") or fobj.get("path")
            joined = fobj.get("joined_text", "") or ""
            title_guess = ""

            # guess title from first non-empty bullet
            for line in joined.splitlines():
                tline = re.sub(r"^[-•]\s*", "", line.strip())
                if tline:
                    title_guess = tline
                    break

            step_in = bullets_to_paragraph(joined)

            rows_ordered.append({
                "opm_step": f"P{idx}",
                "src_file": src_file,
                "title": title_guess,
                "step_in": step_in
            })

    else:
        # Warranty-style (json5 schema from make_sop_nar_json_v6)
        seq = narr_data.get("sequence_order", [])
        file_titles = narr_data.get("file_titles", {})
        extraction_files = narr_data.get("extraction", {}).get("files", [])

        # Build per-file lookup including optional metadata from make_sop_nar_json_v6
        meta_lookup = {}
        for fobj in extraction_files:
            fname = (fobj.get("file","") or "").strip()
            if not fname:
                continue
            meta_lookup[fname] = {
                "joined_text": (fobj.get("joined_text","") or "").strip(),
                "step_code": (fobj.get("step_code","") or "").strip(),
                "uap_label": (fobj.get("uap_label","") or "").strip(),
                "uap_url": (fobj.get("uap_url","") or "").strip(),
                "oth1": (fobj.get("oth1","") or "").strip(),
                "oth2": (fobj.get("oth2","") or "").strip(),
            }

        for idx, fname in enumerate(seq, start=1):
            meta = meta_lookup.get(fname, {})
            joined = meta.get("joined_text", "")
            human_title = file_titles.get(fname, fname)
            step_in = bullets_to_paragraph(joined)

            rows_ordered.append({
                "opm_step": f"P{idx}",
                "src_file": fname,
                "title": human_title,
                "step_in": step_in,
                "step_code": meta.get("step_code", ""),
                "uap_label": meta.get("uap_label", ""),
                "uap_url": meta.get("uap_url", ""),
                "oth1": meta.get("oth1", ""),
                "oth2": meta.get("oth2", ""),
            })

    return rows_ordered

def bullets_to_paragraph(joined: str) -> str:
    if not joined:
        return ""
    lines = []
    for ln in joined.splitlines():
        ln = re.sub(r"^[\-•]\s*", "", ln.strip())
        if ln:
            lines.append(ln)
    return " ".join(lines)

# ---------- turn rows into *_narr_latest style table ----------
def build_narr_latest(narr_data: dict, sop_name: str):
    """
    Produces final rows for <SOP>_narr_latest.csv:
      - One row per step (P1, P2, ...)
      - One PM row that rolls them all up

    Column rules (locked in from SRO and agreed for Warranty):
      OPM_Step
      Source_File
      Source_Title
      Step_narr_in                (raw flattened bullets from that file)
      Step_narr_m_in              (blank for P*, mega text only for PM)
      Step_narr_out               (~8th grade, same content cleaned)
      Step_narr_out_simple        (~5th grade, short imperative steps)
      Step_narr_m_out             (~8th grade mega summary for PM)
      Step_narr_m_out_simple      (~5th grade mega summary for PM)
    """

    ordered_steps = build_rows(narr_data)

    final_rows = []
    all_step_in = []

    # P rows
    for step in ordered_steps:
        opm_step = step["opm_step"]
        src_file = step["src_file"]
        title    = step["title"]
        step_in  = step["step_in"]

        # Optional metadata carried from make_sop_nar_json_v6
        step_code = step.get("step_code", "")
        uap_label = step.get("uap_label", "")
        uap_url   = step.get("uap_url", "")
        oth1      = step.get("oth1", "")
        oth2      = step.get("oth2", "")

        out_8 = normalize_whitespace(step_in)
        out_5 = simplify_for_grade5(step_in)

        final_rows.append({
            "OPM_Step": opm_step,
            "Source_File": src_file,
            "Source_Title": title,
            "Step_narr_in": step_in,
            "Step_narr_m_in": "",
            "Step_narr_out": out_8,
            "Step_narr_out_simple": out_5,
            "Step_narr_m_out": "",
            "Step_narr_m_out_simple": "",
            "Step_Code": step_code,
            "Oth1": oth1,
            "Oth2": oth2,
            "UAP url": uap_url,
            "UAP Label": uap_label,
        })

        if step_in:
            all_step_in.append(step_in)

    # PM row (overview row)
    mega = " ".join(all_step_in)
    mega = re.sub(r"\s+", " ", mega).strip()

    final_rows.append({
        "OPM_Step": "PM",
        "Source_File": "",
        "Source_Title": "Process Overview",
        "Step_narr_in": "",
        "Step_narr_m_in": mega,
        "Step_narr_out": "",
        "Step_narr_out_simple": "",
        "Step_narr_m_out": normalize_whitespace(mega),
        "Step_narr_m_out_simple": simplify_for_grade5(mega),
        "Step_Code": "",
        "Oth1": "",
        "Oth2": "",
        "UAP url": "",
        "UAP Label": "",
    })

    return final_rows

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
        "Step_Code",
        "Oth1",
        "Oth2",
        "UAP url",
        "UAP Label",
    ]
    with open(out_csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json5-in", required=True,
        help="Path to <SOP>_narr_files.json5 from make_sop_nar_json_v6.py")
    ap.add_argument("--sop", required=True,
        help='Short SOP code like "SRO", "Warranty", etc.')
    ap.add_argument("--out-dir", required=True,
        help="Where *_narr_latest*.csv files are written")
    args = ap.parse_args()

    narr_data = load_json5(args.json5_in)
    rows = build_narr_latest(narr_data, args.sop)

    ts = datetime.now().strftime("%Y%m%d_%H%M")
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
