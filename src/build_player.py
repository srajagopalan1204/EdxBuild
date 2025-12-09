#!/usr/bin/env python3
"""
build_player.py  v2.0  (2025-12-09)

Provenance:
  - new_SOP_Builder_Fix 20251208_1550
  - Replaces earlier ad-hoc build_player that generated a full HTML file per SOP.

Purpose:
  - Take an existing story.json file for a SOP.
  - Read the standard sop_player.html template.
  - Produce a SOP-specific *_player.html that:
      * Points to the correct story.json (web path).
      * Sets a meaningful <title>.
      * Points Entity Menu to the right index.html anchor based on story meta (SE → entity-distro, PALCO → entity-palco, etc.).
  - Keep the output directory pattern identical to the old script (e.g. site/BUILD/LineEnt_player.html).

Notes:
  - CLI flags are compatible with the original script so existing commands still work.
  - --mode, --image-width, and --exit are accepted for compatibility:
      * --image-width will adjust the main slide image width percentage.
      * --exit will set the Exit button link.
      * --mode is currently informational only (no behaviour change).
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple


def infer_meta_from_story(story_path: Path) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Peek into story.json and infer:
      - entity   (meta.entity)
      - function (meta.function)
      - subentity(meta.subentity)

    We look at the first frame that has meta fields.
    """
    try:
        data = json.loads(story_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] Could not read/parse story JSON {story_path}: {exc}", file=sys.stderr)
        return None, None, None

    frames = data.get("frames") or []
    for frame in frames:
        meta = frame.get("meta") or {}
        entity = meta.get("entity")
        function = meta.get("function")
        subentity = meta.get("subentity")
        if entity or function or subentity:
            return entity, function, subentity
    return None, None, None


def infer_anchor_id(entity: Optional[str]) -> str:
    """
    Decide which #anchor on index.html to use for goEntityMenu(),
    based on entity code.
    """
    e = (entity or "").upper()
    if e == "SE":
        return "entity-distro"
    if e == "PALCO":
        return "entity-palco"
    # fallback: generic section
    return "entity-other"


def fs_to_web_story_path(story_path: Path, explicit_web: Optional[str] = None) -> str:
    """
    Convert a filesystem story path into a web path suitable for the player.

    Rules:
      1) If explicit_web is given, use that as-is (ensuring leading slash).
      2) If the filesystem path contains "/workspaces/EdxBuild",
         strip that prefix and prepend "/EdxBuild".
      3) Otherwise, use the path relative to the repo root if possible,
         or just prefix "/" to the POSIX path.
    """
    if explicit_web:
        s = explicit_web.strip()
        if not s.startswith("/"):
            s = "/" + s
        return s

    posix = story_path.as_posix()

    marker = "/workspaces/EdxBuild"
    if marker in posix:
        after = posix.split(marker, 1)[1]
        if not after.startswith("/"):
            after = "/" + after
        return "/EdxBuild" + after

    # Try to use path relative to repo root if we can spot a "site" or ".build" folder
    for token in ["/site/", "/.build/"]:
        if token in posix:
            idx = posix.index(token)
            rel = posix[idx:]
            if not rel.startswith("/"):
                rel = "/" + rel
            # assume hosted under /EdxBuild
            return "/EdxBuild" + rel

    # Fallback: just prefix "/" (not ideal, but better than an absolute FS path)
    if not posix.startswith("/"):
        posix = "/" + posix
    return posix


def adjust_title(html: str, title: str) -> str:
    """Replace the <title>...</title> element."""
    return re.sub(
        r"<title>.*?</title>",
        f"<title>{title}</title>",
        html,
        count=1,
        flags=re.S,
    )


def adjust_story_input(html: str, story_web: str) -> str:
    """Set value=\"...\" for <input id=\"story\" ...>."""
    return re.sub(
        r'(<input id="story"[^>]*\bvalue=")[^"]*(")',
        r'\1' + story_web + r'\2',
        html,
        count=1,
    )


def adjust_entity_menu(html: str, anchor_id: str) -> str:
    """Set window.location.href in goEntityMenu() to the correct index.html anchor."""
    href = f"/EdxBuild/index.html#{anchor_id}"
    return re.sub(
        r'(function goEntityMenu\(\)\s*\{[^}]*window\.location\.href\s*=\s*")[^"]*(";\s*[^}]*\})',
        r'\1' + href + r'\2',
        html,
        count=1,
        flags=re.S,
    )


def adjust_exit_link(html: str, exit_href: Optional[str]) -> str:
    """
    Point the 'Exit' button (id=\"exitBtn\") to the requested href.
    If exit_href is None, leave template default unchanged.
    """
    if not exit_href:
        return html
    return re.sub(
        r'(<a\s+id="exitBtn"[^>]*\bhref=")[^"]*(")',
        r'\1' + exit_href + r'\2',
        html,
        count=1,
    )


def adjust_image_width(html: str, width_percent: Optional[int]) -> str:
    """
    Adjust the slide image width in the CSS .imgbox img rule.

    Looks for a pattern like:
      .imgbox img{width:65%;max-width:100%;...}
    and replaces "width:65%" with the requested percentage.
    """
    if width_percent is None:
        return html

    def repl(match: re.Match) -> str:
        block = match.group(0)
        block = re.sub(r"width:\s*\d+%", f"width:{width_percent}%", block)
        return block

    return re.sub(
        r"\.imgbox\s*img\{[^}]*\}",
        repl,
        html,
        count=1,
        flags=re.S,
    )


def find_template() -> Path:
    """
    Locate sop_player.html template relative to this script.

    Search order:
      1) <repo_root>/templates/sop_player.html
      2) <repo_root>/site/sop_player.html

    If not found, exit with an error.
    """
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent  # assumes script is under src/

    candidates = [
        repo_root / "templates" / "sop_player.html",
        repo_root / "site" / "sop_player.html",
    ]
    for c in candidates:
        if c.exists():
            return c

    raise SystemExit(
        "ERROR: sop_player.html template not found.\n"
        f"Tried:\n  - {candidates[0]}\n  - {candidates[1]}\n"
        "Place the template in one of these locations or specify --template."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a SOP-specific *_player.html from story.json using the SOP player template."
    )
    parser.add_argument(
        "--story",
        required=True,
        help="Filesystem path to story.json (as used by csv_to_story.py).",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output HTML path for the SOP-specific player (e.g. site/BUILD/LineEnt_player.html).",
    )
    parser.add_argument(
        "--title",
        help="Browser tab title. If omitted, will use '<Function> – <SubEntity> SOP Player – EdxBuild' if available.",
    )
    parser.add_argument(
        "--mode",
        default="prod",
        help="Mode (dev/prod). Currently informational only; kept for CLI compatibility.",
    )
    parser.add_argument(
        "--image-width",
        type=int,
        default=None,
        help="Slide image width in percent (e.g. 65). Adjusts .imgbox img width in template.",
    )
    parser.add_argument(
        "--exit",
        dest="exit_href",
        help="Href for the Exit button (id='exitBtn') in the header.",
    )
    parser.add_argument(
        "--template",
        help="Optional explicit path to sop_player.html template. If omitted, the script will auto-locate it.",
    )
    parser.add_argument(
        "--story-web",
        help="Optional explicit web path to story.json (e.g. '/EdxBuild/.build/story/LineEnt/story.json').",
    )

    args = parser.parse_args()

    story_fs = Path(args.story)
    if not story_fs.exists():
        raise SystemExit(f"ERROR: story.json not found at {story_fs}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) Infer entity/function/subentity from story.json
    entity, function, subentity = infer_meta_from_story(story_fs)
    anchor_id = infer_anchor_id(entity)

    # 2) Decide web path for story.json
    story_web = fs_to_web_story_path(story_fs, explicit_web=args.story_web)

    # 3) Choose template location
    if args.template:
        template_path = Path(args.template)
        if not template_path.exists():
            raise SystemExit(f"ERROR: template not found at {template_path}")
    else:
        template_path = find_template()

    template_html = template_path.read_text(encoding="utf-8")

    # 4) Decide title
    if args.title:
        title = args.title
    else:
        if function and subentity:
            title = f"{function} – {subentity} SOP Player – EdxBuild"
        else:
            title = "SOP Player – EdxBuild"

    # 5) Apply adjustments
    html = template_html
    html = adjust_title(html, title)
    html = adjust_story_input(html, story_web)
    html = adjust_entity_menu(html, anchor_id)
    html = adjust_exit_link(html, args.exit_href)
    html = adjust_image_width(html, args.image_width)

    out_path.write_text(html, encoding="utf-8")

    print(f"[OK] Wrote SOP player to {out_path}")
    print(f"  story (fs)  : {story_fs}")
    print(f"  story (web) : {story_web}")
    print(f"  entity      : {entity or '(unknown)'}")
    print(f"  function    : {function or '(unknown)'}")
    print(f"  subentity   : {subentity or '(unknown)'}")
    print(f"  anchor      : {anchor_id}")
    print(f"  title       : {title}")
    print(f"  mode        : {args.mode}")
    if args.image_width is not None:
        print(f"  image width : {args.image_width}%")
    if args.exit_href:
        print(f"  exit href   : {args.exit_href}")


if __name__ == "__main__":
    main()
