# Procedure Manual — Build Input for TWEE
**Reading level:** High School  
**Program:** `transi_gen.py`  
**Phase:** Creation of Populated Input to create Input for TWEE  
**Version:** 221025_1440 (NY time)

## What You Need
- RAW file (slides): `Inputs/<SOP>/raw/<SOP>_Raw_*.csv`
- Narration file: `Outputs/<SOP>/<SOP>_Narr_*.csv` or `.xlsx`
- The Python script: `narr/src/transi_gen.py`

## Step 1 — Create the PreMerge File
This file combines RAW with narration fields and helper columns.

**Example command (no manual matches yet):**
```bash
python /workspaces/son_e_lum/narr/src/transi_gen.py --gen premerge   --sop Tech   --raw "/workspaces/son_e_lum/narr/Inputs/Tech/raw/Tech_Raw_211025_1138.csv"   --narr "/workspaces/son_e_lum/narr/Outputs/Tech/Tech_narr_latest.csv"   --out "/workspaces/son_e_lum/narr/Outputs/Tech/transi"
```

**If you already have `*_resp_transi_in*.csv`:**
```bash
python /workspaces/son_e_lum/narr/src/transi_gen.py --gen premerge   --sop Tech   --raw "/workspaces/son_e_lum/narr/Inputs/Tech/raw/Tech_Raw_211025_1138.csv"   --narr "/workspaces/son_e_lum/narr/Outputs/Tech/Tech_narr_latest.csv"   --resp-transi-in "/workspaces/son_e_lum/narr/Outputs/Tech/transi/Tech_resp_transi_in_221025_1100.csv"   --out "/workspaces/son_e_lum/narr/Outputs/Tech/transi"
```

**What you get:** `Outputs/<SOP>/transi/<SOP>_PreMerge_*.csv/.xlsx`  
It includes: all RAW fields, `match_code_OPM`, `OPM_Step`, `Source_Title`, `Narr1/2/3`, `Disp_next1..3`, `UAP url`, `UAP Label`, `start_here` (all *No*), `Mismatch` (all *No*).

## Step 2 — Review and Edit (Create resp_merge)
Open the PreMerge file.
- Fill **UAP url** and **UAP Label** where needed.
- Set exactly one **start_here = Yes** (all others remain No).
- (Optional) Edit `match_code_OPM`, `Narr1/2/3`, or `Disp_next1..3` if you want to override.
- Save your edits as: `Outputs/<SOP>/transi/<SOP>_resp_merge_<stamp>.xlsx` (or `.csv`).

## Step 3 — Build the Final mk_tw_in
This file is ready for `mk_tw` (TWEE).

**Command:**
```bash
python /workspaces/son_e_lum/narr/src/transi_gen.py --gen mk-tw-in   --sop Tech   --premerge "/workspaces/son_e_lum/narr/Outputs/Tech/transi/Tech_PreMerge_221025_1151.xlsx"   --resp-merge "/workspaces/son_e_lum/narr/Outputs/Tech/transi/Tech_Resp_PreMerge_221025_1151.xlsx"   --out "/workspaces/son_e_lum/narr/Outputs/Tech/transi"
```

**What you get:**
- `Outputs/<SOP>/transi/<SOP>_mk_tw_in_*.csv/.xlsx`
- A `ChangeLog` sheet (XLSX) showing what changed from PreMerge
- `Mismatch=Yes` marked where you made edits

## How to Check Your Results
- Confirm one row has `start_here = Yes`.
- Spot-check `Narr1/2/3` make sense for **M** vs non-M matches.
- Verify `Disp_next1..3` show the Titles of `next1_code..3`.
- Check that UAP links and labels are filled as intended.

## Common Issues & Fixes
- **Unrecognized arguments** → usually a stray `/` on a new line. Remove it.
- **Join failed** → ensure the `Code` column exists in both files.
- **Too many `start_here=Yes`** → set only one to Yes.
- **No Narr match** → leave it; `Narr1` will use the first half of Title.

## Next Step: TWEE
Hand the `*_mk_tw_in_*` file to your `mk_tw` process.  
If a row has no `next1_code`, you can place **Menu/Exit** in your authoring stage.
