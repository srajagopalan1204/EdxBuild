#!/usr/bin/env python3
"""
create_sop_template.py

Create a SOP-specific player HTML by copying a generic sop_player.html template
and wiring it based on information in a *_mk_tw_in_READY_*.csv file.

Intended position in pipeline:
  - Run AFTER the READY CSV is created/cleaned
  - Run BEFORE story.json is built
    (the player will point at the conventional story.json path
     /.build/story/<sop_id>/story.json which will be created later)

Provenance:
  new_SOP_Builder_Fix 20251208_1550
"""

import argparse
import csv
import re
from pathlib import Path
from typing import Tuple, Optional


def infer_identity_from_ready(ready_path: Path) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Look into the READY CSV and infer Entity, Function, SubEntity, SOP_id.
    We only need one representative row; all rows should share these fields.
    """
    entity = function = subentity = sop_id = None
    with ready_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entity = (row.get("Entity") or "").strip() or entity
            function = (row.get("Function") or "").strip() or function
            subentity = (row.get("SubEntity") or "").strip() or subentity
            sop_id = (row.get("SOP_id") or "").strip() or sop_id
            # stop after first non-empty set
            if entity or function or subentity or sop_id:
                break
    return entity, function, subentity, sop_id


def infer_anchor_id(entity: Optional[str], function: Optional[str]) -> str:
    """
    Decide which #anchor on index.html to use for goEntityMenu(),
    based on Entity/Function.
    """
    e = (entity or "").upper()
    f = (function or "").lower()

    # Simple first-pass mapping; can extend later if needed
    if e == "SE":
        # Scott Electric Distribution → use the Distro section
        return "entity-distro"
    if e == "PALCO":
        return "entity-palco"

    # Fallback: generic entity anchor (you can add a section later)
    return "entity-other"


def build_player_html(template_text: str, title: str, story_rel: str, anchor_id: str) -> str:
    """
    Apply SOP-specific customizations to the sop_player.html template:

    - Set the <title>...</title>
    - Set default value= for <input id="story">
    - Set goEntityMenu() to point at /EdxBuild/index.html#<anchor_id>
    """
    story_val = "/" + story_rel.lstrip("/")
    entity_href_norm = f"/EdxBuild/index.html#{anchor_id}"

    # 1) Replace <title>...</title>
    out = re.sub(
        r"<title>.*?</title>",
        f"<title>{title}</title>",
        template_text,
        count=1,
        flags=re.S,
    )

    # 2) Replace value="..." on <input id="story" ...>
    out = re.sub(
        r'(<input id="story"[^>]*\\bvalue=")[^"]*(")',
        r'\\1' + story_val + r'\\2',
        out,
        count=1,
    )

    # 3) Replace window.location.href inside goEntityMenu()
    out = re.sub(
        r'(function goEntityMenu\\(\\)\\s*\\{[^}]*window\\.location\\.href\\s*=\\s*")[^"]*(";\\s*[^}]*\\})',
        r'\\1' + entity_href_norm + r'\\2',
        out,
        count=1,
        flags=re.S,
    )

    return out


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create a SOP-specific *_player.html by copying sop_player.html "
            "and wiring it using a *_mk_tw_in_READY_*.csv file."
        )
    )
    parser.add_argument(
        "--ready",
        required=True,
        help="Path to *_mk_tw_in_READY_*.csv for this SOP.",
    )
    parser.add_argument(
        "--base-template",
        default="sop_player.html",
        help="Path to generic sop_player.html template (default: sop_player.html).",
    )
    parser.add_argument(
        "--sop-id",
        help=(
            "Short SOP id, e.g. LineEnt2, ShipFB, ServReqOrd. "
            "If omitted, will try SubEntity then SOP_id from READY."
        ),
    )
    parser.add_argument(
        "--out",
        help=(
            "Output HTML path for the SOP-specific player. "
            "Default: site/BUILD/<sop_id>_player.html (relative to current dir)."
        ),
    )
    parser.add_argument(
        "--title",
        help=(
            "Browser tab title. Default: "
            "'<Function> – <SubEntity> SOP Player – EdxBuild' "
            "or '<sop_id> SOP Player – EdxBuild' if function/subentity not available."
        ),
    )
    parser.add_argument(
        "--story-path",
        help=(
            "Story JSON path as used by the player, relative to the web root. "
            "Default: '.build/story/<sop_id>/story.json'."
        ),
    )

    args = parser.parse_args()

    ready_path = Path(args.ready)
    if not ready_path.exists():
        raise SystemExit(f"READY CSV not found: {ready_path}")

    base_template_path = Path(args.base_template)
    if not base_template_path.exists():
        raise SystemExit(f"Base template not found: {base_template_path}")

    entity, function, subentity, sop_id_csv = infer_identity_from_ready(ready_path)
    sop_id = args.sop_id or subentity or sop_id_csv
    if not sop_id:
        raise SystemExit("Unable to infer sop-id from READY; please pass --sop-id explicitly.")

    anchor_id = infer_anchor_id(entity, function)

    # Decide default output path
    out_path = Path(args.out) if args.out else Path(f"site/BUILD/{sop_id}_player.html")

    # Decide story path used in player
    if args.story_path:
        story_rel = args.story_path
    else:
        story_rel = f".build/story/{sop_id}/story.json"

    # Decide title
    if args.title:
        title = args.title
    else:
        if function and subentity:
            title = f"{function} – {subentity} SOP Player – EdxBuild"
        else:
            title = f"{sop_id} SOP Player – EdxBuild"

    template_text = base_template_path.read_text(encoding="utf-8")

    out_html = build_player_html(
        template_text=template_text,
        title=title,
        story_rel=story_rel,
        anchor_id=anchor_id,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_html, encoding="utf-8")

    print(f"[OK] Created SOP-specific player template: {out_path}")
    print(f"  Entity     : {entity or '(unknown)'}")
    print(f"  Function   : {function or '(unknown)'}")
    print(f"  SubEntity  : {subentity or '(unknown)'}")
    print(f"  SOP id     : {sop_id}")
    print(f"  Anchor id  : {anchor_id}")
    print(f"  Story JSON : /{story_rel.lstrip('/')}")
    print(f"  Title      : {title}")


if __name__ == "__main__":
    main()
