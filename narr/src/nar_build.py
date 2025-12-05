#!/usr/bin/env python3
"""
nar_build.py (stub)
Validate→extract→merge→summarize narration from Monday Excel per SOP.
Replace with full implementation or wire to your existing tooling.
"""
import argparse

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sop", required=True)
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--logs", required=True)
    ap.add_argument("--keep-latest", action="store_true")
    args = ap.parse_args()
    print("[STUB] nar_build.py called with:", vars(args))
    print("Implement validate→extract→merge→summarize here.")
