#!/usr/bin/env python3
import csv, json, argparse, os, re, sys

def load_json5(path):
    """
    Minimal JSON5 loader:
    - strips // line comments
    - strips /* block comments */
    Then parses as JSON.
    """
    with open(path, encoding="utf-8") as f:
        txt = f.read()

    # remove /* ... */ block comments
    txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)

    # strip // comments from each line
    cleaned_lines = []
    for line in txt.splitlines():
        if "//" in line:
            line = line.split("//", 1)[0]
        cleaned_lines.append(line)
    txt = "\n".join(cleaned_lines)

    try:
        return json.loads(txt)
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse {path} as JSON after comment stripping.", file=sys.stderr)
        print(e, file=sys.stderr)
        raise

def main():
    ap = argparse.ArgumentParser(
        description="Convert *_narr_files.json5 into *_narr_latest.csv for downstream pipeline."
    )
    ap.add_argument("--in-json5", required=True,
                    help="Path to Warranty_narr_files.json5 (from make_sop_nar_json_v6.py)")
    ap.add_argument("--out-csv", required=True,
                    help="Path to write Warranty_narr_latest.csv")
    ap.add_argument("--code-col", default="Code",
                    help="Which field in the JSON to treat as the step/frame code (e.g. M1, S1, etc.)")
    ap.add_argument("--narr1-col", default="Task Description",
                    help="Which field becomes Narr1 (Hear Me)")
    ap.add_argument("--narr2-col", default="What",
                    help="Which field becomes Narr2 (Read More)")
    ap.add_argument("--narr3-col", default="",
                    help="Optional deeper narration field for Narr3 (Deep Dive). Leave blank if none.")
    args = ap.parse_args()

    data = load_json5(args.in_json5)

    # Sometimes the root is a dict with a list inside e.g. {"rows":[...]}
    # We’ll try to unwrap automatically.
    if isinstance(data, dict):
        for guess_key in ["rows", "items", "steps", "data"]:
            if guess_key in data and isinstance(data[guess_key], list):
                data = data[guess_key]
                break

    if not isinstance(data, list):
        raise SystemExit("FATAL: JSON5 root is not a list of rows. Can't continue.")

    rows_out = []
    for row in data:
        # pull frame code, narration columns
        code = str(row.get(args.code-col, "")).strip()

        narr1 = str(row.get(args.narr1-col, "")).strip() if args.narr1-col else ""
        narr2 = str(row.get(args.narr2-col, "")).strip() if args.narr2-col else ""
        narr3 = str(row.get(args.narr3-col, "")).strip() if args.narr3-col else ""

        rows_out.append({
            "Code": code,
            "Narr1": narr1,
            "Narr2": narr2,
            "Narr3": narr3,
            "UAP url": "",
            "UAP Label": ""
        })

    os.makedirs(os.path.dirname(args.out_csv), exist_ok=True)

    # The header order below matches what downstream expects (Code, Narr1, Narr2, Narr3, UAP url, UAP Label).
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Code", "Narr1", "Narr2", "Narr3", "UAP url", "UAP Label"]
        )
        writer.writeheader()
        for r in rows_out:
            writer.writerow(r)

    print(f"Wrote {args.out_csv} with {len(rows_out)} rows.")

if __name__ == "__main__":
    main()
