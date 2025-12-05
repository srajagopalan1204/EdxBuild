#!/usr/bin/env python3
import argparse, csv, json, os, re
from pathlib import Path

def load_json5(path):
    if not os.path.exists(path):
        return {}
    txt = Path(path).read_text(encoding="utf-8")
    # strip // and /* */ comments so JSON5-ish files work
    txt = re.sub(r"//.*?$", "", txt, flags=re.M)
    txt = re.sub(r"/\*.*?\*/", "", txt, flags=re.S)
    return json.loads(txt or "{}")

def basename_only(p):
    p = str(p or "").replace("\\", "/").strip()
    return p.split("/")[-1] if p else ""

def main():
    ap = argparse.ArgumentParser(description="Normalize taxonomy + image filenames in mk_tw_in/PreMerge CSV.")
    ap.add_argument("--in", dest="inp", required=True, help="Input CSV (PreMerge or mk_tw_in)")
    ap.add_argument("--out", dest="out", required=True, help="Output CSV (normalized)")
    ap.add_argument("--sop-id", required=True, help="SOP id (e.g., TechMobile, SRO)")
    ap.add_argument("--taxonomy-config", default="narr/Config/taxonomy.json5",
                    help="JSON/JSON5 with defaults and per-SOP overrides")
    ap.add_argument("--entity", default=None)
    ap.add_argument("--function", default=None)
    ap.add_argument("--subentity", default=None)
    args = ap.parse_args()

    cfg = load_json5(args.taxonomy_config)
    dfl = (cfg.get("defaults") or {})
    per = (cfg.get(args.sop_id) or {})

    # Precedence: CLI > per-SOP config > defaults
    entity    = args.entity    or per.get("Entity")    or dfl.get("Entity")    or "Palco"
    function  = args.function  or per.get("Function")  or dfl.get("Function")  or "Service"
    subentity = args.subentity or per.get("SubEntity") or dfl.get("SubEntity") or ""

    sop_id   = args.sop_id
    sop_path = f"SOP/images/{entity}/{function}/{sop_id}"

    inp = Path(args.inp)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with inp.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = list(reader.fieldnames or [])

    # Ensure required columns exist
    need_cols = ["Entity","Function","SubEntity","SOP_id","SOP_path","Image_sub_url"]
    for c in need_cols:
        if c not in headers:
            headers.append(c)

    out_rows = []
    for r in rows:
        # Normalize image to filename only
        img = r.get("Image_sub_url") or r.get("Image") or ""
        r["Image_sub_url"] = basename_only(img)

        # Canonical taxonomy (keep existing value if present)
        r["Entity"]    = r.get("Entity")    or entity
        r["Function"]  = r.get("Function")  or function
        r["SubEntity"] = r.get("SubEntity") or subentity
        r["SOP_id"]    = sop_id
        r["SOP_path"]  = sop_path

        out_rows.append(r)

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(out_rows)

    print(f"Normalized {len(out_rows)} rows -> {out}")
    print(f"SOP_id={sop_id}  Entity={entity}  Function={function}  SubEntity={subentity}")
    print(f"SOP_path={sop_path}")

if __name__ == "__main__":
    main()
