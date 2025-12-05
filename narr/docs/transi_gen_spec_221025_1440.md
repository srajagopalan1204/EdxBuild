# `transi_gen.py` — Program Specification
**Phase:** Creation of Populated Input to create Input for TWEE  
**Version:** 221025_1440 (NY time)

## 1) Overview
`transi_gen.py` converts *RAW* (slide export), *Narration* (catalog), and your manual mappings into two key artifacts:
- **PreMerge** — a populated review file that combines RAW with narration fields, plus helper columns.
- **mk_tw_in** — the final, flat file to feed into `mk_tw` (TWEE builder).

Supported modes:
- `--gen manual` — builds a workbook with fuzzy **suggestions** to help mapping.
- `--gen twee` — legacy path: mapping → **mk_tw** input (XLSX).
- `--gen premerge` — **NEW**: builds `<SOP>_PreMerge_*.csv/.xlsx` using RAW + Narr + optional `*_resp_transi_in*.csv`.
- `--gen mk-tw-in` — **NEW**: consumes your edited `*_resp_merge*.csv/.xlsx`, logs changes, outputs final `mk_tw_in` CSV/XLSX.

## 2) Paths, Naming & Timestamps
- Default roots (can be overridden by flags):
  - RAW in: `/workspaces/son_e_lum/narr/Inputs/<SOP>/raw`
  - Narr in/out: `/workspaces/son_e_lum/narr/Outputs/<SOP>`
  - Transi/mktw out: `/workspaces/son_e_lum/narr/Outputs/<SOP>/transi`
  - Scripts: `/workspaces/son_e_lum/narr/src`
- Timestamp format: `DDMMYY_HHMM` (America/New_York).
- Each mode writes a timestamped file; you may also maintain a `*_latest.csv` alias if desired.

## 3) Inputs & Outputs by Mode
### `--gen premerge`
**Input:** RAW, Narr, optional `*_resp_transi_in*.csv`  
**Output:** `<SOP>_PreMerge_DDMMYY_HHMM.csv` (+ `.xlsx`) with:
- All RAW fields (unchanged)
- Merge fields: `match_code_OPM`, `OPM_Step`, `Source_Title`
- Narration fields per rules (see §5)
- `Narr1` = first half of RAW `Title` (split on “ – ” or “ - ”)
- `Disp_next1..3` from `next1_code..3` → corresponding RAW Titles
- Extra: `UAP url`, `UAP Label` (empty), `start_here` (all “No”), `Mismatch` (all “No”)

### `--gen mk-tw-in`
**Input:** the PreMerge you used, plus your edited response: `*_resp_merge*.csv/.xlsx`  
**Output:** `<SOP>_mk_tw_in_DDMMYY_HHMM.csv` (+ `.xlsx` with `ChangeLog` sheet)
- Applies your edits (only non-empty cells overwrite)
- Sets `Mismatch=Yes` for rows with changes
- Ready for `mk_tw`

### `--gen manual` (helper, optional)
Builds an XLSX with:
- `Map_Entries` — RAW rows + **suggested matches** (≥ threshold)
- `OPM_Code_Lookup` — Narr codes with titles for VLOOKUP

### `--gen twee` (legacy path)
Consumes a mapping workbook and builds an XLSX mk_tw input (older path).

## 4) Required Columns
**RAW (minimum):** `Code`, `Title`  
Optional (recommended): `Deci_Question`, `next1_code`, `next2_code`, `next3_code`

**Narr (minimum):** `Code`, `OPM_Step`, `Source_Title`  
Narr text fields:  
- `Step_narr_out_simple`, `Step_narr_out`  
- `Step_narr_m_out_simple`, `Step_narr_m_out`

**resp_transi_in (optional at premerge):**  
- `CODE` (RAW code) and `Match` (either Narr `Code` like `M1` or full `OPM_Step`).

**resp_merge (your edits at mk-tw-in):**  
- Usually a copy of PreMerge with edits to any field, plus `UAP url`, `UAP Label`, and exactly one `start_here=Yes`.

## 5) Matching & Narration Rules
- If `Match` resolves to an **M*** Narr step →  
  `Narr2 = Step_narr_m_out_simple`, `Narr3 = Step_narr_m_out`, and `Narr1 = Step_narr_out_simple` (fallback: first half of Title).
- If `Match` resolves to a **non-M** step →  
  `Narr1 = Step_narr_out_simple`, `Narr2 = Step_narr_out`, `Narr3` remains as configured for premerge (or blank).
- If **no match** →  
  `Narr1 =` first half of RAW `Title` (before “ – ” / “ - ”); `Narr2/Narr3` blank.

## 6) Display Labels
- `Disp_next1..3` are populated from RAW via `next1_code..3` → the **Title** of those codes.

## 7) CLI Reference
Common flags:
- `--sop <SOP>`  (e.g., `Tech`)
- `--raw <path/to/Raw.csv>`
- `--narr <path/to/Narr.csv|.xlsx>`
- `--resp-transi-in <path/to/*resp_transi_in*.csv>` (premerge)
- `--premerge <path/to/PreMerge.csv|.xlsx>` and `--resp-merge <path/to/Resp_Merge.csv|.xlsx>` (mk-tw-in)
- `--out <output/dir>` (default: `Outputs/<SOP>/transi`)

## 8) Validation & Change Log (mk-tw-in)
- Only **non-empty** cells in `resp_merge` overwrite PreMerge.
- `Mismatch=Yes` for rows where any field changed.
- `ChangeLog` sheet lists `Code, Field, From, To`.

## 9) Notes & Limits
- Use **exactly one** `start_here = Yes`.
- Menu/Exit handling: you may place these where `next1_code` is blank in the authoring stage.
- If a `Match` equals a full `OPM_Step`, it must map *uniquely*. Otherwise prefer a Narr `Code`.
