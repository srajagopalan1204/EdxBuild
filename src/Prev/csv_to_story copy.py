#!/usr/bin/env python3
import argparse, csv, json, os, re

def truthy(v): return str(v).strip().lower() in {"1","y","yes","true","start","start_here"}
def clean_txt(t): 
    t = (t or "").replace("_x000B_"," ")  # remove PPT artifact
    return re.sub(r"\s+\n", "\n", t).strip()

def build_story(csv_path, sop_id, default_image_root):
    frames=[]; start_code=None
    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        r=csv.DictReader(f)
        for row in r:
            code=(row.get("Code") or "").strip()
            title=clean_txt(row.get("Title") or code)
            img=(row.get("Image_sub_url") or "").strip()
            if img and not img.startswith(("/", "SOP/", ".build/")):
                img=os.path.join(default_image_root, img).replace("\\","/")
            if img and not img.startswith("/"): img="/"+img.lstrip("/")

            # Decisions
            q = clean_txt(row.get("Deci_Question") or "")
            choices=[]
            for kcode,klabel in [("Next1_Code","Disp_next1"),
                                 ("Next2_Code","Disp_next2"),
                                 ("Next3_Code","Disp_next3")]:
                nxt=(row.get(kcode) or "").strip()
                lbl=clean_txt(row.get(klabel) or "")
                if nxt: choices.append({"to": nxt, "label": lbl or nxt})

            # Narration (Read Me)
            narr_parts = [row.get("Narr1"), row.get("Narr2"), row.get("Narr3")]
            narr_text = "\n\n".join([clean_txt(x) for x in narr_parts if x and clean_txt(x)])

            # UAP
            uap_url   = (row.get("UAP url") or "").strip()
            uap_label = clean_txt(row.get("UAP Label") or "")

            frames.append({
                "sop_id": sop_id,
                "frame_code": code,
                "title": title,
                "image": img,
                "decision_question": q,
                "choices": choices,
                "narr_text": narr_text,   # 👈 Read Me
                "uap_url": uap_url,       # 👈 UAP
                "uap_label": uap_label,   # 👈 UAP Label
                "meta": {
                    "entity": row.get("Entity") or "Palco",
                    "function": row.get("Function") or "Service",
                    "subentity": row.get("SubEntity") or ""
                }
            })
            if start_code is None and truthy(row.get("start_here","")):
                start_code=code

    return {"sop_id": sop_id, "start_code": start_code or (frames[0]["frame_code"] if frames else None), "frames": frames}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--csv", required=True); ap.add_argument("--sop-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--default-image-root", default="SOP/images/Palco/Service/TechMobile/")
    ap.add_argument("--log", default=None)
    a=ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    story=build_story(a.csv, a.sop_id, a.default_image_root)
    with open(a.out,"w",encoding="utf-8") as f: json.dump(story,f,ensure_ascii=False,indent=2)
    msg=f"Wrote {a.out} with {len(story.get('frames',[]))} frames. Start={story.get('start_code')}"
    print(msg)
    if a.log: open(a.log,"w",encoding="utf-8").write(msg+"\n")

if __name__=="__main__": main()
