#!/usr/bin/env python3
import argparse, json, os, shutil

def append_json_block(src_json, dest_json):
    with open(src_json, encoding="utf-8") as f:
        block = json.load(f)
    os.makedirs(os.path.dirname(dest_json), exist_ok=True)
    if not os.path.exists(dest_json):
        with open(dest_json, "w", encoding="utf-8") as f:
            json.dump({"blocks":[block]}, f, ensure_ascii=False, indent=2)
        return 1
    with open(dest_json, encoding="utf-8") as f:
        dest = json.load(f)
    dest.setdefault("blocks", []).append(block)
    with open(dest_json, "w", encoding="utf-8") as f:
        json.dump(dest, f, ensure_ascii=False, indent=2)
    return len(dest["blocks"])

def copy_tree(src_root, dst_root):
    n=0
    for root, _, files in os.walk(src_root):
        for fn in files:
            s = os.path.join(root, fn)
            rel = os.path.relpath(s, src_root)
            d = os.path.join(dst_root, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d); n+=1
    return n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="story json in EdxBuild")
    ap.add_argument("--dest", required=True, help="Edu env/Unit_staging/story.json")
    ap.add_argument("--images", required=True, help="EdxBuild images folder")
    ap.add_argument("--images-dest", required=True, help="Edu images folder")
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    lines=[]
    copied = copy_tree(args.images, args.images_dest) if os.path.exists(args.images) else 0
    lines.append(f"Images copied: {copied} -> {args.images_dest}")
    blocks = append_json_block(args.src, args.dest)
    lines.append(f"Appended story block; total blocks now: {blocks}")
    text = "\n".join(lines); print(text)
    if args.log: open(args.log,"w",encoding="utf-8").write(text+"\n")

if __name__ == "__main__":
    main()
