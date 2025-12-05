#!/usr/bin/env python3
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
        kept = kept.rstrip() + "\n}"

    return kept

# ---------- helper: strip comments / trailing commas so json.loads works ----------
def strip_json5_comments_and_trailing_commas(raw_text: str) -> str:
    no_line_comments = re.sub(r"//.*", "", raw_text)
    no_block_comments = re.sub(r"/\*.*?\*/", "", no_line_comments, flags=re.DOTALL)
    no_trail_commas = re.sub(r",(\s*[}\]])", r"\1", no_block_comments)
    return no_trail_commas.strip()

# ---------- normalize to single paragraph for 'in' ----------
def bullets_to_paragraph(joined_text: str) -> str:
    lines = []
    for line in joined_text.splitlines():
        line = line.strip()
        line = re.sub(r"^[-•]\s*", "", line)
        if line:
            lines.append(line)
    para = " ".join(lines)
    para = para.replace("/", " ")
    para = re.sub(r"\s+", " ", para).strip()
    return para

# ---------- 8th grade voice placeholder ----------
def normalize_whitespace(txt: str) -> str:
    txt = txt.strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt

# ---------- 5th grade voice IMPROVED ----------
def simplify_for_grade5(txt: str) -> str:
    """
    Grade 5-ish simplifier for SOP narration.

    Strategy:
    - Normalize punctuation and spacing.
    - Split into action-like chunks using common verbs / separators.
    - Clean filler phrases like "From the Service Orders Screen".
    - Truncate long chunks (~20 words).
    - Return short, direct, imperative sentences joined with ". ".
    """

    import re

    # normalize punctuation / unicode dashes / bullets
    t = txt
    t = t.replace("â€”", "-").replace("—", "-").replace("–", "-").replace("•", "-")
    t = re.sub(r"\s+", " ", t).strip()

    # insert split markers before common action verbs so we get shorter steps
    verbs = [
        r"Click", r"Select", r"Change", r"Mark", r"Enter", r"Save",
        r"Apply", r"Open", r"Go to", r"Drill", r"Search", r"Filter",
        r"Choose", r"Type", r"Set", r"Exit", r"Pick"
    ]
    pattern_verbs = r"(" + r"|".join(verbs) + r")\b"
    t_marked = re.sub(pattern_verbs, r"| \1", t, flags=re.I)

    # also break on " - " and ". " (common in your input)
    t_marked = t_marked.replace(" - ", " | ")
    t_marked = t_marked.replace(". ", " | ")

    raw_chunks = [c.strip() for c in t_marked.split("|")]

    cleaned_steps = []
    for chunk in raw_chunks:
        if not chunk:
            continue

        # remove boilerplate screen intros and UI fluff
        chunk = re.sub(
            r"\b(From the|From The|In the|In The|On the|On The|At the|At The|"
            r"Use the|Use The|Using the|Using The|With the|With The|"
            r"From The Service Order[s]? Screen|From The Warranty Claim Reconciliation Screen|"
            r"From The Order Inquiry Screen|From The CSD Search Field)\b",
            "",
            chunk,
            flags=re.I
        )

        # remove common UI nouns that don't add meaning for the tech
        chunk = re.sub(
            r"\b(Screen|Button|Icon|Tab|Field|Section|Menu|Funnel Icon|Menu)\b",
            "",
            chunk,
            flags=re.I
        )

        # collapse leftover commas/space
        chunk = re.sub(r"\s+", " ", chunk).strip(" ,.")

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
    - Warranty-style with:
        sequence_order
        file_titles
        extraction.files[*] = {file, joined_text}
    """

    rows_ordered = []

    if "files" in narr_data:
        # SRO-style
        for idx, fobj in enumerate(narr_data["files"], start=1):
            filename = (fobj.get("source_file","") or "").strip()
            base = os.path.basename(filename)
            joined = (fobj.get("joined_text","") or "").strip()

            # guess a human-ish title from first bullet
            title_guess = ""
            for line in joined.splitlines():
                tline = re.sub(r"^[-•]\s*", "", line.strip())
                if tline:
                    title_guess = tline
                    break

            step_in = bullets_to_paragraph(joined)

            rows_ordered.append({
                "opm_step": f"P{idx}",
                "src_file": base,
                "title": title_guess,
                "step_in": step_in
            })

    else:
        # Warranty-style (json5 schema from make_sop_nar_json_v6)
        seq = narr_data.get("sequence_order", [])
        file_titles = narr_data.get("file_titles", {})
        extraction_files = narr_data.get("extraction", {}).get("files", [])

        joined_lookup = {}
        for fobj in extraction_files:
            fname = (fobj.get("file","") or "").strip()
            joined_lookup[fname] = (fobj.get("joined_text","") or "").strip()

        for idx, fname in enumerate(seq, start=1):
            joined = joined_lookup.get(fname, "")
            human_title = file_titles.get(fname, fname)
            step_in = bullets_to_paragraph(joined)

            rows_ordered.append({
                "opm_step": f"P{idx}",
                "src_file": fname,
                "title": human_title,
                "step_in": step_in
            })

    return rows_ordered

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
            "Step_narr_m_out_simple": ""
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
        help="Where *_narr_latest_<timestamp>.csv + *_narr_latest.csv go")
    args = ap.parse_args()

    # read JSON5-ish file
    with open(args.json5_in, "r", encoding="utf-8") as f:
        raw_txt = f.read()

    trimmed = trim_after_config_block(raw_txt)
    cleaned = strip_json5_comments_and_trailing_commas(trimmed)
    narr_data = json.loads(cleaned)

    rows = build_narr_latest(narr_data, args.sop)

    # approximate Eastern timestamp (UTC-4 for now)
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
