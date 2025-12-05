#!/usr/bin/env python3
import argparse, json, csv, re, os
from datetime import datetime, timedelta

#
# --- helper: strip off the config tail that isn't valid JSON ---
#
def trim_after_config_block(full_text: str) -> str:
    """
    Your Warranty_narr_files.json5 ends with a block like:

    // ===== BEGIN DEFAULT NARR CONFIG ...
    summarize: { ... },
    output: { ... },
    logging: { ... }
    // ===== END DEFAULT NARR CONFIG =====
    }

    That block uses unquoted keys ("summarize:", etc.) so it's not valid JSON.

    We don't need that tail to build *_narr_latest.csv. We only need:
      - sequence_order
      - file_titles
      - extraction.files[*].file
      - extraction.files[*].joined_text

    So: if we see the marker line for the default config, we cut everything
    from that marker onward, and then make sure we close the main object "}".
    """
    marker = "===== BEGIN DEFAULT NARR CONFIG"
    idx = full_text.find(marker)
    if idx == -1:
        # no marker, return as-is
        return full_text

    # keep everything BEFORE the marker
    kept = full_text[:idx]

    # Now, 'kept' likely ends with a comma and maybe some whitespace/newlines,
    # because the config block in the .json5 is preceded by a comma.
    # Example:  },\n\n// ===== BEGIN DEFAULT...
    # We should safely strip trailing commas, then close the JSON object.

    # Drop anything after the last newline before the marker that's just commas/braces.
    kept = kept.rstrip(", \n\r\t")

    # Make sure it ends with a single newline then a closing brace
    if not kept.rstrip().endswith("}"):
        kept = kept.rstrip() + "\n}"

    return kept

#
# --- JSON5 helper: strip comments + trailing commas so we can json.loads() ---
#
def strip_json5_comments_and_trailing_commas(raw_text: str) -> str:
    # remove // line comments
    no_line_comments = re.sub(r"//.*", "", raw_text)
    # remove /* block */ comments
    no_block_comments = re.sub(r"/\*.*?\*/", "", no_line_comments, flags=re.DOTALL)
    # remove trailing commas before } or ]
    no_trail_commas = re.sub(r",(\s*[}\]])", r"\1", no_block_comments)
    return no_trail_commas.strip()

#
# --- Text shaping helpers (your narration rules) ---
#
def bullets_to_paragraph(joined_text: str) -> str:
    """
    Take bullet text like:
      - Step one
      - Step two / do X
    and flatten into one paragraph:
      "Step one Step two do X"
    Rules you asked for:
    - strip leading "- " / "• "
    - replace "/" with a space
    - collapse whitespace
    - DO NOT add extra wording
    """
    lines = []
    for line in joined_text.splitlines():
        line = line.strip()
        # strip common bullet prefix
        line = re.sub(r"^[-•]\s*", "", line)
        if line:
            lines.append(line)
    para = " ".join(lines)
    # soften "/" so screen reader voice is nicer
    para = para.replace("/", " ")
    # collapse whitespace
    para = re.sub(r"\s+", " ", para).strip()
    return para

def normalize_whitespace(txt: str) -> str:
    """
    Placeholder "8th grade" voice:
    - keep the user's language
    - just normalize spaces
    """
    txt = txt.strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt

def simplify_for_grade5(txt: str) -> str:
    """
    Placeholder "5th grade" voice:
    - short chunks
    - cap ~25 words per chunk
    - join with ". "
    """
    parts = re.split(r"[.!?]+", txt)
    simple_bits = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        words = p.split()
        short_words = words[:25]
        simple_bits.append(" ".join(short_words))
    out = ". ".join(simple_bits).strip()
    if out:
        out += "."
    return out

#
# --- Core row builder that understands Warranty + SRO shapes ---
#
def build_rows(narr_data: dict):
    """
    Produce ordered list of step dicts:

    [
      {
        "opm_step": "P1",
        "src_file": "Something.xlsx",
        "title":    "Human title or first bullet line",
        "step_in":  "flattened bullet text"
      },
      ...
    ]

    Supports:
    (A) SRO-style:
        narr_data["files"] = [
          {"source_file": "...", "joined_text": "..."},
          ...
        ]
        Order = list order.

    (B) Warranty-style:
        narr_data["sequence_order"] = [ "file1.xlsx", "file2.csv", ...]
        narr_data["file_titles"][filename] = "Nice title"
        narr_data["extraction"]["files"] = [
           {"file": "file1.xlsx", "joined_text": "..."},
           ...
        ]
        Order = sequence_order.
    """

    rows_ordered = []

    if "files" in narr_data:
        # SRO-style
        for idx, fobj in enumerate(narr_data["files"], start=1):
            filename = (fobj.get("source_file","") or "").strip()
            base = os.path.basename(filename)
            joined = (fobj.get("joined_text","") or "").strip()

            # guess a Source_Title: first non-empty bullet-ish line
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
        # Warranty-style
        seq = narr_data.get("sequence_order", [])
        file_titles = narr_data.get("file_titles", {})
        extraction_files = narr_data.get("extraction", {}).get("files", [])

        # build quick lookup filename -> joined_text
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

def build_narr_latest(narr_data: dict, sop_name: str):
    """
    Turn those step dicts into final *_narr_latest rows:
    - P1..Pn (each input file)
    - PM (roll-up)
    Apply your rules exactly:
      • Step_narr_in = raw flattened bullet text (no extra words added)
      • Step_narr_out = grade ~8 style (currently same content, cleaned)
      • Step_narr_out_simple = grade ~5 style
      • *_m_* columns blank for P rows
      • PM row:
          Step_narr_in stays ""
          Step_narr_m_in = concat of all Step_narr_in
          Step_narr_m_out / _simple = summarized from that concat
    """
    ordered_steps = build_rows(narr_data)

    final_rows = []
    all_step_in = []

    # P rows
    for step in ordered_steps:
        opm_step = step["opm_step"]        # "P1"
        src_file = step["src_file"]        # filename.xlsx
        title    = step["title"]           # Source_Title
        step_in  = step["step_in"]         # flattened bullets

        out_8 = normalize_whitespace(step_in)
        out_5 = simplify_for_grade5(step_in)

        final_rows.append({
            "OPM_Step": opm_step,
            "Source_File": src_file,
            "Source_Title": title,
            "Step_narr_in": step_in,
            "Step_narr_m_in": "",                      # blank for P rows
            "Step_narr_out": out_8,                    # grade ~8
            "Step_narr_out_simple": out_5,             # grade ~5
            "Step_narr_m_out": "",
            "Step_narr_m_out_simple": ""
        })

        if step_in:
            all_step_in.append(step_in)

    # PM row
    mega = " ".join(all_step_in)
    mega = re.sub(r"\s+", " ", mega).strip()

    final_rows.append({
        "OPM_Step": "PM",
        "Source_File": "",
        "Source_Title": "Process Overview",
        "Step_narr_in": "",                            # must be blank for PM
        "Step_narr_m_in": mega,                        # concat of all step_in
        "Step_narr_out": "",
        "Step_narr_out_simple": "",
        "Step_narr_m_out": normalize_whitespace(mega),       # ~8th grade
        "Step_narr_m_out_simple": simplify_for_grade5(mega), # ~5th grade
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

    # 1. read the raw .json5 text
    with open(args.json5_in, "r", encoding="utf-8") as f:
        raw_txt = f.read()

    # 2. cut off the config tail that has unquoted keys
    trimmed = trim_after_config_block(raw_txt)

    # 3. strip // comments, /* */ comments, trailing commas
    cleaned = strip_json5_comments_and_trailing_commas(trimmed)

    # 4. now we can json.loads()
    narr_data = json.loads(cleaned)

    # 5. build rows for narr_latest
    rows = build_narr_latest(narr_data, args.sop)

    # 6. timestamp ~Eastern (UTC minus 4h fallback)
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
