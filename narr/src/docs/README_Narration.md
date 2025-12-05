# Narration Pipeline (son_e_lum/narr)

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


some useful commands at the terminal to make copy 
"
cp /workspaces/son_e_lum/narr/src/narr_build_phased.py \
   /workspaces/son_e_lum/narr/src/narr_build_phased.backup.2.py
echo "OK: backup saved"
OK: backup saved
"


12/04/2025 
create ppt 
"C:\Users\scottuser\Documents\SonetLumier\Input\SE_SLS_Enter_line_Opt2_251203_1402.pptx"
create overall file with steps as your guide 
"C:\Users\scottuser\Documents\SonetLumier\Input\Monday_excel\SLS_Line_Ent\Overall_line_entry_251204_0637.xlsx"
python /workspaces/EdxBuild/narr/src/narr_split.py \
--input "/workspaces/EdxBuild/narr/Inputs/LineEnt/Overall_line_entry_251204_0637.xlsx" \
--sop "LineEnt" \
--out-dir "/workspaces/EdxBuild/narr/Inputs/LineEnt/Excel"
_+_+_+_+
python "/workspaces/EdxBuild/narr/src/make_sop_nar_json_v6.py" \
  --inputs "/workspaces/EdxBuild/narr/Inputs/LineEnt/Excel/*.xlsx,/workspaces/EdxBuild/narr/Inputs/LineEnt/Excel/*.csv" \
  --out "/workspaces/EdxBuild/narr/Outputs/LineEnt/LineEnt_narr_files.json5" \
  --sop "LineEnt" \
  --text-cols "Task Description,What" \
  --join-style bullets
  +_+_+_+_+
  python narr/src/build_narr_latest_v3.py \
  --json5-in "/workspaces/EdxBuild/narr/Outputs/LineEnt/LineEnt_narr_files.json5" \
  --sop LineEnt \
  --out-dir narr/Outputs/LineEnt
  _+_+_+_+
  