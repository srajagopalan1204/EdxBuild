#!/usr/bin/env python3
import argparse, csv, json, os

def truthy(v):
    return str(v).strip().lower() in {
        "1","y","yes","true","start","start_here"
    }

def build_story(csv_path, sop_id):
    frames = []
    index = {}
    start_code = None

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader):
            code  = (row.get("Code") or "").strip()
            if not code:
                # fallback so we don't end up with "" frame_code
                code = (row.get("SlideIndex") or "START").strip()

            title = (row.get("Title") or code).strip()
            # clean weird "_x000B_" artifacts from PPT exports
            title = title.replace("_x000B_", " ").strip()

            # Build image path using SOP_path + Image_sub_url
            sop_path = (row.get("SOP_path") or "").strip().strip("/")
            img_leaf = (row.get("Image_sub_url") or "").strip().lstrip("/")

            image_full = ""
            if img_leaf:
                if img_leaf.startswith("SOP/") or img_leaf.startswith("/SOP/"):
                    # already looks like SOP/images/Palco/Service/ServReqOrd/S1.png
                    image_full = "/" + img_leaf.lstrip("/")
                elif sop_path:
                    # combine SOP_path + filename
                    # becomes /SOP/images/Palco/Service/ServReqOrd/S1.png
                    image_full = "/" + sop_path + "/" + img_leaf
                else:
                    # last fallback
                    image_full = "/" + img_leaf

                # normalize accidental double slashes
                while "//" in image_full:
                    image_full = image_full.replace("//", "/")

            # Decisions / branching
            q = (row.get("Deci_Question") or "").strip()
            choices = []
            for kcode, klabel in [
                ("Next1_Code","Disp_next1"),
                ("Next2_Code","Disp_next2"),
                ("Next3_Code","Disp_next3")
            ]:
                nxt = (row.get(kcode) or "").strip()
                lbl = (row.get(klabel) or "").strip()
                if nxt:
                    choices.append({
                        "to": nxt,
                        "label": lbl or nxt
                    })

            frame = {
                "sop_id": sop_id,
                "frame_code": code,
                "title": title,
                "image": image_full,
                "decision_question": q,
                "choices": choices,
                "narr1": (row.get("Narr1") or "").strip(),
                "narr2": (row.get("Narr2") or "").strip(),
                "narr3": (row.get("Narr3") or "").strip(),
                "uap_url": (row.get("UAP url") or "").strip(),
                "uap_label": (row.get("UAP Label") or "").strip(),
                "meta": {
                    "entity": (row.get("Entity") or "Palco").strip(),
                    "function": (row.get("Function") or "Service").strip(),
                    "subentity": (row.get("SubEntity") or "").strip()
                }
            }

            frames.append(frame)
            index[code] = i

            # Mark the start frame
            if start_code is None and truthy(row.get("start_here","")):
                start_code = code

    if start_code is None and frames:
        start_code = frames[0]["frame_code"]

    return {
        "sop_id": sop_id,
        "start_code": start_code,
        "frames": frames
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--sop-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()

    story = build_story(args.csv, args.sop_id)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)

    msg = f"Wrote {args.out} with {len(story.get('frames', []))} frames. Start={story.get('start_code')}"
    print(msg)
    if args.log:
        with open(args.log, "w", encoding="utf-8") as lf:
            lf.write(msg + "\n")

if __name__ == "__main__":
    main()
