#!/usr/bin/env python3
"""
narr_bootstrap_fixed.py
One-time scaffold for the Son_E_Lum narration pipeline.
Usage (run from repo root):
  python narr_bootstrap_fixed.py --root son_e_lum/narr
Creates a minimal, namespaced tree without touching existing folders.
"""
import argparse
from pathlib import Path

TEMPLATE_JSON5 = """{
  // Narration config (per SOP)
  "sop": "<SOP>",
  "standard": {
    "sheet": "OPM",
    "columns": ["Step", "Detail"]
  },
  "overrides": [
    // {
    //   "file": "Change Status to Closed.xlsx",
    //   "issue": "missing 'Detail' column",
    //   "manual_map": {"Action": "Step", "Notes": "Detail"}
    // }
  ],
  "extraction": {
    "step_builder": "concat_lines",
    "line_join": " ",
    "drop_values": ["Subitems"]
  },
  "summarize": {
    "reading_grade": 8,
    "style": "imperative_short",
    "max_sentence_len": 24
  }
}
"""

README = """# Narration Pipeline (son_e_lum/narr)

This area holds inputs from Monday Excel (per SOP), outputs, configs, and logs for the narration step.

## Folders
- Inputs/<SOP>/ : source Excel files
- Outputs/<SOP>/ : narration CSV/XLSX with timestamps and _latest
- Config/ : per-SOP JSON5 rules (conformance + overrides)
- src/ : builders/utilities
- docs/ : how-to + changelog
- logs/<SOP>/ : QA reports and run logs

## One-time run
```
python narr_bootstrap_fixed.py --root son_e_lum/narr
```
Then add at least one SOP folder under Inputs/ and Outputs/ (e.g., Tech).
"""

NAR_BUILD_STUB = """#!/usr/bin/env python3
\"\"\"
nar_build.py (stub)
Validate→extract→merge→summarize narration from Monday Excel per SOP.
Replace with full implementation or wire to your existing tooling.
\"\"\"
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
"""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="relative path like son_e_lum/narr")
    args = parser.parse_args()
    root = Path(args.root)

    # Create core folders
    for sub in ["Inputs", "Outputs", "Config", "src", "docs", "logs"]:
        (root / sub).mkdir(parents=True, exist_ok=True)

    # Place starter files
    (root / "docs" / "README_Narration.md").write_text(README, encoding="utf-8")
    (root / "Config" / "_schema_nar.json5").write_text("{}", encoding="utf-8")
    (root / "Config" / "Tech_Nar.json5").write_text(TEMPLATE_JSON5.replace("<SOP>", "Tech"), encoding="utf-8")

    # Stubs
    (root / "src" / "nar_build.py").write_text(NAR_BUILD_STUB, encoding="utf-8")
    (root / "src" / "nar_utils.py").write_text("# utils go here\n", encoding="utf-8")
    (root / "src" / "nar_summarize.py").write_text("# summarization helpers go here\n", encoding="utf-8")

    print(f"[OK] Created narration scaffold at: {root}")
    print("You can now: git add, commit, and push these files.")

if __name__ == "__main__":
    main()
