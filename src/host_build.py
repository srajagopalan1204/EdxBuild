#!/usr/bin/env python3
import argparse, os, shutil

def sync_images(src_root="SOP/images", dst_root="site/BUILD/SOP/images"):
    if not os.path.exists(src_root):
        print(f"WARNING: missing source {src_root}")
        return 0
    n=0
    for root, _, files in os.walk(src_root):
        for fn in files:
            s = os.path.join(root, fn)
            rel = os.path.relpath(s, src_root)
            d = os.path.join(dst_root, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copy2(s, d); n+=1
    print(f"Synced {n} images to {dst_root}."); return n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync-images", action="store_true")
    args = ap.parse_args()
    if args.sync_images:
        sync_images()

if __name__ == "__main__":
    main()
