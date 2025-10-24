#!/usr/bin/env python3
import argparse, os, json

TEMPLATE = r"""<!doctype html><meta charset="utf-8" />
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root{{ --bg:#f7f7fb; --card:#fff; --text:#111; --muted:#6b7280; --line:#e5e7eb; --brand:#0b5fff; --brand-ink:#fff; --radius:14px; --shadow:0 6px 24px rgba(0,0,0,.06); --maxw:1100px; }}
  html,body{{height:100%}} body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.45 system-ui,Segoe UI,Arial}}
  header.sticky{{position:fixed;top:0;left:0;right:0;background:rgba(255,255,255,.9);backdrop-filter:saturate(140%) blur(8px);border-bottom:1px solid var(--line);z-index:10}}
  .bar{{max-width:var(--maxw);margin:0 auto;padding:12px 18px;display:flex;gap:10px;align-items:center;justify-content:center;flex-wrap:wrap;text-align:center}}
  .wrap{{max-width:var(--maxw);margin:112px auto 48px;padding:0 18px}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:18px}}
  .center{{text-align:center}}
  .crumbs{{color:var(--muted);font-size:14px;margin:-6px 0 12px 0}}
  .crumbs a{{color:var(--muted);text-decoration:none}} .crumbs a:hover{{text-decoration:underline}}
  input[type=text]{{min-width:360px;max-width:90vw;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;text-align:center}}
  button,.btn{{padding:6px 10px;border-radius:12px;border:1px solid var(--line);background:#fff;cursor:pointer}}
  button.primary{{background:var(--brand);color:var(--brand-ink);border-color:var(--brand)}}
  button:disabled{{opacity:.5;cursor:not-allowed}}
  a.btn{{text-decoration:none;color:inherit;display:inline-flex;align-items:center;gap:6px}}
  .imgbox{{display:flex;justify-content:center}}
  .imgbox img{{width:{image_width}%;max-width:100%;height:auto;border-radius:12px;display:block}}
  @media (max-width:720px){{ .imgbox img{{width:100%}} }}
  .toolbar, .choices, .bottomnav{{display:flex;gap:10px;flex-wrap:wrap;justify-content:center;margin:14px 0}}
  .narr{{white-space:pre-wrap;background:#fafafa;border:1px solid var(--line);padding:16px 40px 12px 12px;border-radius:10px;position:relative;max-width:800px;margin:0 auto;text-align:left}}
  .narr .closeX{{position:absolute;top:6px;right:8px;border:0;background:transparent;font-size:20px;line-height:1;cursor:pointer}}
  details{{margin-top:10px;max-width:800px;margin-left:auto;margin-right:auto}}
</style>

<header class="sticky">
  <div class="bar">
    <button id="backTop" onclick="back()" title="Go back one step">Back</button>
    <button onclick="restart()" title="Restart from start">Menu</button>
    <input id="story" type="text" value="{story_path}" aria-label="Story JSON path"/>
    <button class="primary" onclick="load()">Load</button>
    <a id="exitBtn" class="btn" href="#" target="_blank" rel="noopener" style="display:none">Exit</a>
  </div>
</header>

<div class="wrap">
  <div class="card">
    <div id="crumbs" class="crumbs center"></div>
    <div id="view"></div>
    <div class="bottomnav">
      <button id="backBottom" onclick="back()" title="Go back one step">Back</button>
      <button onclick="restart()" title="Restart from start">Menu</button>
    </div>
  </div>
</div>

<script>
const CONFIG = {{
  showBreadcrumb: {show_breadcrumb},
  showDetails: {show_details},
  exitHref: {exit_href_json}
}};

// Project-aware absolute path helper:
// Pages serves under /<repo>/..., while local dev is at /...
function toAbsolute(p){{
  const root = location.pathname.replace(/\/site\/BUILD\/.*$/, "");
  return p.startsWith("/") ? (root + p) : (root + "/" + p);
}}

let data=null, byCode={{}}, historyStack=[], speaking=false;

function stopTTS(){{ try{{ speechSynthesis.cancel(); speaking=false; }}catch(e){{}} }}
function speak(text){{ try{{ stopTTS(); if(!text) return; const u=new SpeechSynthesisUtterance(text); u.rate=1.0; u.pitch=1.0; u.onend=()=>{{ speaking=false; }}; speaking=true; speechSynthesis.speak(u); }} catch(e){{ speaking=false; }} }}
function escapeHTML(s){{ return (s||'').replace(/[&<>"]/g, m=>({{"&":"&amp;","<":"&lt;"," >":"&gt;","\"":"&quot;"}}[m])); }}
function escapeJS(s){{ return (s||'').replace(/`/g,"\\`").replace(/\\/g,"\\\\"); }}
function setExit(){{ const a=document.getElementById('exitBtn'); if(CONFIG.exitHref){{ a.href=CONFIG.exitHref; a.style.display='inline-flex'; }} }}

async function load(){{
  stopTTS();
  let path=document.getElementById('story').value.trim()||'{story_path}';
  // keep whatever was provided (relative or absolute)
  const res=await fetch(path); if(!res.ok){{ alert('Failed '+path+' ('+res.status+')'); return; }}
  data=await res.json(); byCode={{}}; (data.frames||[]).forEach(f=>byCode[f.frame_code]=f);
  const start=data.start_code || (data.frames[0]&&data.frames[0].frame_code);
  historyStack=[start]; render(start); setExit(); updateBackState();
}}

function updateBackState(){{
  const canBack = historyStack.length > 1;
  const b1=document.getElementById('backTop'), b2=document.getElementById('backBottom');
  if(b1) b1.disabled = !canBack;
  if(b2) b2.disabled = !canBack;
}}

function render(code){{
  stopTTS();
  const f=byCode[code]; if(!f){{ document.getElementById('view').innerHTML='<p class="center">Missing frame <code>'+code+'</code></p>'; updateBackState(); return; }}

  // breadcrumbs
  const crumbsEl=document.getElementById('crumbs');
  if(CONFIG.showBreadcrumb){{
    const crumbs=historyStack.map(c=>`<a href="#" onclick="goto('${{c}}')">${{c}}</a>`).join(' › ');
    crumbsEl.innerHTML = crumbs; crumbsEl.style.display='block';
  }} else {{
    crumbsEl.style.display='none';
  }}

  const img = f.image ? toAbsolute(f.image) : '';
  const q=f.decision_question||'';
  const choices=Array.isArray(f.choices)?f.choices:[];
  const n1=(f.narr1||'').trim(), n2=(f.narr2||'').trim(), n3=(f.narr3||'').trim();
  const uapUrl=(f.uap_url||'').trim();

  const hearMeBtn   = n1 ? `<button aria-label="Hear me (Narration 1)" onclick="speak(\`${{escapeJS(n1)}}\`)">Hear me</button><button aria-label="Stop audio" onclick="stopTTS()">Stop</button>` : '';
  const readMeBtn   = n1 ? `<button aria-label="Read me (Narration 1)" onclick="openRead('read1')">Read me</button>` : '';
  const readMoreBtn = n2 ? `<button aria-label="Read more (Narration 2)" onclick="openRead('read2')">Read more</button>` : '';
  const hearMoreBtn = n3 ? `<button aria-label="Hear more (Narration 3)" onclick="speak(\`${{escapeJS(n3)}}\`)">Hear more</button><button aria-label="Stop audio" onclick="stopTTS()">Stop</button>` : '';
  const uapBtn      = uapUrl ? `<a class="btn" href="${{uapUrl}}" target="_blank" rel="noopener">To learn the steps, click here</a>` : '';
  const toolbar = [hearMeBtn, readMeBtn, readMoreBtn, hearMoreBtn, uapBtn].filter(Boolean).join('\n');

  document.getElementById('view').innerHTML = `
    <div class="center">
      <div class="imgbox">${{img?`<img src="${{img}}" alt="">`:''}}</div>
      <div class="toolbar">${{toolbar}}</div>
      ${{n1?panel('read1', n1, 'Close read'):''}}
      ${{n2?panel('read2', n2, 'Close read'):''}}
      ${{q?`<p><strong>${{q}}</strong></p>`:''}}
    </div>
    <div class="choices center">
      ${{choices.map(ch=>`<button class="primary" onclick="choose('${{ch.to}}')">${{ch.label||ch.to}}</button>`).join('')}}
    </div>
    ${{CONFIG.showDetails ? `<details><summary>Details</summary><pre>${{JSON.stringify(f, null, 2)}}</pre></details>` : ''}}
  `;

  document.addEventListener("click", outsideCloser, {{ once: true }});
  updateBackState();
}}

function panel(id, text, closeLabel){{
  return `<div id="${{id}}" class="narr" style="display:none">
            <button class="closeX" onclick="closeRead('${{id}}')" aria-label="Close read panel">×</button>
            ${{escapeHTML(text)}}
            <div style="margin-top:8px;text-align:right"><button onclick="closeRead('${{id}}')">${{closeLabel}}</button></div>
          </div>`;
}}
function openRead(id){{ ['read1','read2'].forEach(x=>{{ const el=document.getElementById(x); if(el) el.style.display = (x===id?'block':'none'); }}); }}
function closeRead(id){{ const el=document.getElementById(id); if(el) el.style.display='none'; }}
function outsideCloser(e){{ const p1=document.getElementById("read1"), p2=document.getElementById("read2"); const inside = (el)=> el && (el===e.target || el.contains(e.target)); if(!inside(p1) && !inside(p2)){{ if(p1) p1.style.display="none"; if(p2) p2.style.display="none"; }} }}
function choose(nextCode){{ if(!nextCode) return; historyStack.push(nextCode); render(nextCode); }}
function goto(code){{ const idx=historyStack.indexOf(code); if(idx>=0){{ historyStack=historyStack.slice(0,idx+1); }} render(code); }}
function back(){{ if(historyStack.length>1){{ historyStack.pop(); render(historyStack[historyStack.length-1]); }} }}
function restart(){{ if(!data) return; stopTTS(); const s=data.start_code||(data.frames[0]&&data.frames[0].frame_code); historyStack=[s]; render(s); }}
document.addEventListener('keydown', (e)=>{{ if(e.key==='Escape'){{ closeRead('read1'); closeRead('read2'); }} }});
load();
</script>
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--story", required=True, help="Path to story.json as it should appear on the page (keep relative if your page is under /site/BUILD/).")
    ap.add_argument("--out",   required=True, help="Output HTML path (e.g., site/BUILD/techmobile_player.html)")
    ap.add_argument("--title", default="SOP Player – Interactive")
    ap.add_argument("--mode",  choices=["dev","prod"], default="prod", help="dev shows Details; prod hides Details")
    ap.add_argument("--image-width", type=int, default=65, help="Image width percent")
    ap.add_argument("--exit", default="", help="Exit URL (optional, may be relative like index.html)")
    ap.add_argument("--no-breadcrumb", action="store_true", help="Hide breadcrumb row")
    args = ap.parse_args()

    story_path = args.story  # preserve exactly as given (relative/absolute)

    html = TEMPLATE.format(
        title=args.title,
        image_width=args.image_width,
        story_path=story_path,
        show_breadcrumb=("false" if args.no_breadcrumb else "true"),
        show_details=("false" if args.mode=="prod" else "true"),
        exit_href_json=json.dumps(args.exit)
    )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)
    print("Wrote", args.out)

if __name__ == "__main__":
    main()
