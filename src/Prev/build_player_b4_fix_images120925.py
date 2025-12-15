#!/usr/bin/env python3
"""
build_player.py

Generate a self-contained SOP HTML player from a story.json file.

New-look player:
- Top bar: Back, Restart, story path, Load
- Bottom bar: Back, Restart, Entity Menu, Home
- Narration controls with hover tooltips
- Optional breadcrumbs and details block (dev vs prod)

We avoid str.format() (which conflicts with CSS/JS braces) and instead
use simple token replacement:

  __TITLE__
  __STORY_PATH__
  __IMAGE_WIDTH__
  __SHOW_BREADCRUMB__
  __SHOW_DETAILS__
  __EXIT_HREF__
  __ENTITY_NAME__
  __ENTITY_HREF__
  __HOME_HREF__
"""

import argparse
import json
import os

TEMPLATE = r"""<!doctype html><meta charset="utf-8" />
<title>__TITLE__</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root{
    --bg:#f7f7fb;
    --card:#fff;
    --text:#111;
    --muted:#6b7280;
    --line:#e5e7eb;
    --brand:#0b5fff;
    --brand-ink:#fff;
    --radius:14px;
    --shadow:0 6px 24px rgba(0,0,0,.06);
    --maxw:1100px;
  }
  html,body{height:100%}
  body{
    margin:0;
    background:var(--bg);
    color:var(--text);
    font:16px/1.45 system-ui,Segoe UI,Arial;
  }
  header.sticky{
    position:fixed;
    top:0;left:0;right:0;
    background:rgba(255,255,255,.9);
    backdrop-filter:saturate(140%) blur(8px);
    border-bottom:1px solid var(--line);
    z-index:10;
  }
  .bar{
    max-width:var(--maxw);
    margin:0 auto;
    padding:12px 18px;
    display:flex;
    gap:10px;
    align-items:center;
    justify-content:center;
    flex-wrap:wrap;
    text-align:center;
  }
  .wrap{
    max-width:var(--maxw);
    margin:112px auto 48px;
    padding:0 18px;
  }
  .card{
    background:var(--card);
    border:1px solid var(--line);
    border-radius:var(--radius);
    box-shadow:var(--shadow);
    padding:18px;
  }
  .center{text-align:center}
  .crumbs{
    color:var(--muted);
    font-size:14px;
    margin:-6px 0 12px 0;
  }
  .crumbs a{
    color:var(--muted);
    text-decoration:none;
  }
  .crumbs a:hover{text-decoration:underline}

  input[type=text]{
    min-width:360px;
    max-width:90vw;
    padding:10px 12px;
    border:1px solid var(--line);
    border-radius:10px;
    background:#fff;
    text-align:center;
  }
  button,.btn{
    padding:6px 10px;
    border-radius:12px;
    border:1px solid var(--line);
    background:#fff;
    cursor:pointer;
  }
  button.primary{
    background:var(--brand);
    color:var(--brand-ink);
    border-color:var(--brand);
  }
  button:disabled{
    opacity:.5;
    cursor:not-allowed;
  }
  a.btn{
    text-decoration:none;
    color:inherit;
    display:inline-flex;
    align-items:center;
    gap:6px;
  }

  .imgbox{
    display:flex;
    justify-content:center;
  }
  .imgbox img{
    width:__IMAGE_WIDTH__;
    max-width:100%;
    height:auto;
    border-radius:12px;
    display:block;
  }
  @media (max-width:720px){
    .imgbox img{width:100%}
  }
  .toolbar,
  .choices,
  .bottomnav{
    display:flex;
    gap:10px;
    flex-wrap:wrap;
    justify-content:center;
    margin:14px 0;
  }

  .narr{
    white-space:pre-wrap;
    background:#fafafa;
    border:1px solid var(--line);
    padding:16px 40px 12px 12px;
    border-radius:10px;
    position:relative;
    max-width:800px;
    margin:0 auto;
    text-align:left;
  }
  .narr .closeX{
    position:absolute;
    top:6px;
    right:8px;
    border:0;
    background:transparent;
    font-size:20px;
    line-height:1;
    cursor:pointer;
  }
  details{
    margin-top:10px;
    max-width:800px;
    margin-left:auto;
    margin-right:auto;
  }
</style>

<header class="sticky">
  <div class="bar">
    <!-- TOP NAV: Back + Restart + story path + Load -->
    <button
      id="backTop"
      onclick="back()"
      title="Go back to the previous step in this module">
      Back
    </button>

    <button
      onclick="restart()"
      title="Start this module again from the first step">
      Restart
    </button>

    <input
      id="story"
      type="text"
      value="__STORY_PATH__"
      aria-label="Story JSON path" />

    <button class="primary" onclick="load()">Load</button>

    <!-- Exit kept for possible future use; hidden unless configured -->
    <a id="exitBtn" class="btn" href="#" target="_blank" rel="noopener" style="display:none">
      Exit
    </a>
  </div>
</header>

<div class="wrap">
  <div class="card">
    <div id="crumbs" class="crumbs center"></div>
    <div id="view"></div>

    <!-- BOTTOM NAV: Back, Restart, Entity Menu, Home -->
    <div class="bottomnav">
      <button
        id="backBottom"
        onclick="back()"
        title="Go back to the previous step in this module">
        Back
      </button>

      <button
        onclick="restart()"
        title="Start this module again from the first step">
        Restart
      </button>

      <button
        onclick="goEntityMenu()"
        title="Return to the __ENTITY_NAME__ training menu">
        Entity Menu
      </button>

      <button
        onclick="goHome()"
        title="Go to the main Scott Electric training landing page">
        Home
      </button>
    </div>
  </div>
</div>

<script>
const CONFIG = {
  showBreadcrumb: __SHOW_BREADCRUMB__,
  showDetails: __SHOW_DETAILS__,
  exitHref: __EXIT_HREF__,
  entityHref: __ENTITY_HREF__,
  homeHref: __HOME_HREF__
};

// Project-aware absolute path helper:
// Pages serve under /<repo>/..., while local dev is at /...
function toAbsolute(p){
  const root = location.pathname.replace(/\/site\/BUILD\/.*$/, "");
  return p.startsWith("/") ? (root + p) : (root + "/" + p);
}

let data=null, byCode={}, historyStack=[], speaking=false;

function stopTTS(){
  try{ speechSynthesis.cancel(); speaking=false; }catch(e){}
}
function speak(text){
  try{
    stopTTS();
    if(!text) return;
    const u=new SpeechSynthesisUtterance(text);
    u.rate=1.0; u.pitch=1.0;
    u.onend=()=>{ speaking=false; };
    speaking=true;
    speechSynthesis.speak(u);
  } catch(e){ speaking=false; }
}
function escapeHTML(s){
  return (s||"").replace(/[&<>"]/g, m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[m]));
}
function escapeJS(s){
  return (s||"").replace(/`/g,"\\`").replace(/\\/g,"\\\\");
}
function setExit(){
  const a=document.getElementById('exitBtn');
  if(CONFIG.exitHref){
    a.href = CONFIG.exitHref;
    a.style.display = 'inline-flex';
  }
}

function goEntityMenu(){
  stopTTS();
  if(CONFIG.entityHref) location.href = CONFIG.entityHref;
}
function goHome(){
  stopTTS();
  if(CONFIG.homeHref) location.href = CONFIG.homeHref;
}

async function load(){
  stopTTS();
  let path=document.getElementById('story').value.trim() || "__STORY_PATH__";
  const res=await fetch(path);
  if(!res.ok){ alert('Failed '+path+' ('+res.status+')'); return; }
  data=await res.json();
  byCode={};
  (data.frames||[]).forEach(f=>byCode[f.frame_code]=f);
  const start=data.start_code || (data.frames[0] && data.frames[0].frame_code);
  historyStack=[start];
  render(start);
  setExit();
  updateBackState();
}

function updateBackState(){
  const canBack = historyStack.length > 1;
  const b1=document.getElementById('backTop'),
        b2=document.getElementById('backBottom');
  if(b1) b1.disabled = !canBack;
  if(b2) b2.disabled = !canBack;
}

function render(code){
  stopTTS();
  const f=byCode[code];
  if(!f){
    document.getElementById('view').innerHTML =
      '<p class="center">Missing frame <code>'+code+'</code></p>';
    updateBackState();
    return;
  }

  const crumbsEl=document.getElementById('crumbs');
  if(CONFIG.showBreadcrumb){
    const crumbs=historyStack
      .map(c=>`<a href="#" onclick="goto('${c}')">${c}</a>`)
      .join(' › ');
    crumbsEl.innerHTML = crumbs;
    crumbsEl.style.display='block';
  } else {
    crumbsEl.style.display='none';
  }

  const img = f.image ? toAbsolute(f.image) : '';
  const q=f.decision_question||'';
  const choices=Array.isArray(f.choices)?f.choices:[];
  const n1=(f.narr1||'').trim();
  const n2=(f.narr2||'').trim();
  const n3=(f.narr3||'').trim();
  const uapUrl=(f.uap_url||'').trim();

  const hearMeBtn   = n1
    ? `<button aria-label="Hear me (Narration 1)" title="Hear the narration for this step" onclick="speak(\`${escapeJS(n1)}\`)">Hear me</button>
       <button aria-label="Stop audio" title="Stop the narration audio" onclick="stopTTS()">Stop</button>`
    : '';
  const readMeBtn   = n1
    ? `<button aria-label="Read me (Narration 1)" title="Show the narration text for this step" onclick="openRead('read1')">Read me</button>`
    : '';
  const readMoreBtn = n2
    ? `<button aria-label="Read more (Narration 2)" title="Show additional details for this step" onclick="openRead('read2')">Read more</button>`
    : '';
  const hearMoreBtn = n3
    ? `<button aria-label="Hear more (Narration 3)" title="Hear additional narration for this step" onclick="speak(\`${escapeJS(n3)}\`)">Hear more</button>
       <button aria-label="Stop audio" title="Stop the narration audio" onclick="stopTTS()">Stop</button>`
    : '';
  const uapBtn      = uapUrl
    ? `<a class="btn" href="${uapUrl}" target="_blank" rel="noopener">To learn the steps, click here</a>`
    : '';

  const toolbar = [hearMeBtn, readMeBtn, readMoreBtn, hearMoreBtn, uapBtn]
    .filter(Boolean)
    .join('\n');

  document.getElementById('view').innerHTML = `
    <div class="center">
      <div class="imgbox">${img?`<img src="${img}" alt="">`:''}</div>
      <div class="toolbar">${toolbar}</div>
      ${n1?panel('read1', n1, 'Close read'):''}
      ${n2?panel('read2', n2, 'Close read'):''}
      ${q?`<p><strong>${q}</strong></p>`:''}
    </div>
    <div class="choices center">
      ${choices.map(ch=>`<button class="primary" onclick="choose('${ch.to}')">${ch.label||ch.to}</button>`).join('')}
    </div>
    ${CONFIG.showDetails ? `<details><summary>Details</summary><pre>${JSON.stringify(f, null, 2)}</pre></details>` : ''}
  `;

  document.addEventListener("click", outsideCloser, { once: true });
  updateBackState();
}

function panel(id, text, closeLabel){
  return `<div id="${id}" class="narr" style="display:none">
            <button class="closeX" onclick="closeRead('${id}')" aria-label="Close read panel">×</button>
            ${escapeHTML(text)}
            <div style="margin-top:8px;text-align:right">
              <button onclick="closeRead('${id}')">${closeLabel}</button>
            </div>
          </div>`;
}
function openRead(id){
  ['read1','read2'].forEach(x=>{
    const el=document.getElementById(x);
    if(el) el.style.display = (x===id?'block':'none');
  });
}
function closeRead(id){
  const el=document.getElementById(id);
  if(el) el.style.display='none';
}
function outsideCloser(e){
  const p1=document.getElementById("read1"),
        p2=document.getElementById("read2");
  const inside=(el)=> el && (el===e.target || el.contains(e.target));
  if(!inside(p1) && !inside(p2)){
    if(p1) p1.style.display="none";
    if(p2) p2.style.display="none";
  }
}

function choose(nextCode){
  if(!nextCode) return;
  historyStack.push(nextCode);
  render(nextCode);
}
function goto(code){
  const idx=historyStack.indexOf(code);
  if(idx>=0){
    historyStack=historyStack.slice(0,idx+1);
  }
  render(code);
}
function back(){
  if(historyStack.length>1){
    historyStack.pop();
    render(historyStack[historyStack.length-1]);
  }
}
function restart(){
  if(!data) return;
  stopTTS();
  const s=data.start_code || (data.frames[0] && data.frames[0].frame_code);
  historyStack=[s];
  render(s);
}

document.addEventListener('keydown',(e)=>{
  if(e.key==='Escape'){
    closeRead('read1');
    closeRead('read2');
  }
});
load();
</script>
"""

def main() -> None:
  ap = argparse.ArgumentParser(description="Build SOP HTML player from story.json")
  ap.add_argument("--story", required=True, help="Path to story.json (as used in the browser)")
  ap.add_argument("--out", required=True, help="Output HTML file path")
  ap.add_argument("--title", required=True, help="HTML <title> text")
  ap.add_argument("--image-width", default="65%", help="Flowchart image width (e.g. 65% or 100%)")
  ap.add_argument("--mode", choices=["prod", "dev"], default="prod",
                  help="prod = hide Details, dev = show Details section")
  ap.add_argument("--no-breadcrumb", action="store_true",
                  help="Disable breadcrumb trail at top of player")
  ap.add_argument("--exit", default="", help="Optional Exit URL (hidden if empty)")
  ap.add_argument("--entity-name", default="this",
                  help="Entity name for tooltip (e.g. 'Electrical Distribution (Distro)')")
  ap.add_argument("--entity-href", default="",
                  help="URL for Entity Menu button (e.g. 'index.html#entity-distro')")
  ap.add_argument("--home-href", default="",
                  help="URL for Home button (e.g. 'index.html#welcome')")

  args = ap.parse_args()

  # This is the path the browser will fetch, not your filesystem path.
  story_path = args.story

  subs = {
      "TITLE": args.title,
      "STORY_PATH": story_path,
      "IMAGE_WIDTH": args.image_width,
      "SHOW_BREADCRUMB": "false" if args.no_breadcrumb else "true",
      "SHOW_DETAILS": "false" if args.mode == "prod" else "true",
      "EXIT_HREF": json.dumps(args.exit or None),
      "ENTITY_NAME": args.entity_name,
      "ENTITY_HREF": json.dumps(args.entity_href or None),
      "HOME_HREF": json.dumps(args.home_href or None),
  }

  html = TEMPLATE
  for key, value in subs.items():
    html = html.replace(f"__{key}__", value)

  out_dir = os.path.dirname(args.out)
  if out_dir:
    os.makedirs(out_dir, exist_ok=True)
  with open(args.out, "w", encoding="utf-8") as f:
    f.write(html)
  print("Wrote", args.out)

if __name__ == "__main__":
  main()
