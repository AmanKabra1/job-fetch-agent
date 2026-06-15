"""
Job dashboard + resume builder (web UI).
========================================

ONE FastAPI app, two run modes:

  * Local  (JOBS_SOURCE=live, the default): a "Fetch today's jobs" button
    scrapes LinkedIn/Indeed/Google via python-jobspy, scores every job against
    your resume, and shows the top matches. Works because it runs on your IP.

  * Vercel (JOBS_SOURCE=sheet): the same UI, but jobs are read from your Google
    Sheet (filled daily by the GitHub Actions cron). No live scrape - Vercel's
    datacenter IPs get blocked by the boards and serverless functions time out.

Either way you can click a job and download a tailored resume (PDF / Word).

Run locally:
    pip install -r requirements.txt
    python app.py
    # open http://localhost:8000
"""

import os
import io
import json
import datetime as dt

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

import resume_profile as P
import resume_builder as RB
import job_matching as JM

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))

# Vercel's filesystem is read-only except /tmp, and serverless instances don't
# share files, so on Vercel we only use /tmp (ephemeral) and never rely on a
# generated file persisting between requests.
ON_VERCEL = os.environ.get("VERCEL") == "1"
RESUME_DIR = "/tmp/resume" if ON_VERCEL else os.path.join(HERE, "resume")
DATA_DIR = "/tmp/data" if ON_VERCEL else os.path.join(HERE, "data")
JOBS_CACHE = os.path.join(DATA_DIR, "jobs_latest.json")

JOBS_SOURCE = os.environ.get("JOBS_SOURCE", "live").lower()  # "live" | "sheet"

# Live-scrape defaults
SITES = ["linkedin", "indeed", "google"]
LOCATION = "India"
COUNTRY_INDEED = "India"
DEFAULT_HOURS_OLD = 24
DEFAULT_LIMIT = 50
RESULTS_PER_TERM = 20

# Google Sheet (sheet mode)
SHEET_NAME = os.environ.get("SHEET_NAME", "Job Listings")
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "jobs")

app = FastAPI(title="Aman Kabra - Job & Resume Dashboard")


# --------------------------------------------------------------------------- #
# JOB SOURCES
# --------------------------------------------------------------------------- #
def _score_and_rank(rows, limit):
    """rows: list of dicts with title/company/location/site/date_posted/job_url/description."""
    scored = []
    for r in rows:
        title = str(r.get("title") or "")
        desc = str(r.get("description") or "")
        score, matched = JM.score_job(title, desc)
        scored.append({
            "score": score,
            "matched": matched,
            "title": title,
            "company": str(r.get("company") or ""),
            "location": str(r.get("location") or ""),
            "site": str(r.get("site") or ""),
            "date_posted": str(r.get("date_posted") or ""),
            "is_remote": bool(r.get("is_remote")),
            "job_url": str(r.get("job_url") or ""),
            "description": desc,
        })
    scored = [s for s in scored if s["job_url"]]
    # dedupe by url
    seen, unique = set(), []
    for s in scored:
        if s["job_url"] in seen:
            continue
        seen.add(s["job_url"])
        unique.append(s)
    unique.sort(key=lambda s: s["score"], reverse=True)
    return unique[:limit]


def fetch_live(hours_old: int, limit: int):
    """Scrape the boards (local only). jobspy is imported lazily."""
    from jobspy import scrape_jobs  # heavy import, only when actually fetching
    import pandas as pd

    frames = []
    for term in JM.SEARCH_TERMS:
        try:
            df = scrape_jobs(
                site_name=SITES,
                search_term=term,
                google_search_term=f"{term} jobs near {LOCATION} since yesterday",
                location=LOCATION,
                results_wanted=RESULTS_PER_TERM,
                hours_old=hours_old,
                country_indeed=COUNTRY_INDEED,
                linkedin_fetch_description=True,
            )
        except Exception as e:
            print(f"  ! {term!r} failed: {e}", flush=True)
            continue
        if df is not None and not df.empty:
            frames.append(df)

    if not frames:
        return []
    combined = pd.concat(frames, ignore_index=True).fillna("")
    rows = combined.to_dict("records")
    return _score_and_rank(rows, limit)


def fetch_from_sheet(limit: int):
    """Read jobs from the Google Sheet (Vercel mode)."""
    import gspread
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        gc = gspread.service_account_from_dict(json.loads(creds_json))
    else:
        gc = gspread.service_account(filename="service_account.json")
    ws = gc.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
    rows = ws.get_all_records()
    return _score_and_rank(rows, limit)


def load_cache():
    if os.path.exists(JOBS_CACHE):
        with open(JOBS_CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"fetched_at": None, "jobs": []}


def save_cache(jobs):
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {"fetched_at": dt.datetime.now().isoformat(timespec="seconds"), "jobs": jobs}
    with open(JOBS_CACHE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return payload


def _find_cached_job(job_url: str):
    for j in load_cache().get("jobs", []):
        if j.get("job_url") == job_url:
            return j
    return None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/jobs")
def api_jobs(limit: int = DEFAULT_LIMIT):
    """Return the most recently fetched jobs (cached locally, or from the sheet on Vercel)."""
    if JOBS_SOURCE == "sheet":
        jobs = fetch_from_sheet(limit)
        return {"fetched_at": "from Google Sheet", "jobs": jobs, "source": "sheet"}
    cache = load_cache()
    cache["source"] = "live-cache"
    return cache


@app.post("/api/fetch")
def api_fetch(hours_old: int = DEFAULT_HOURS_OLD, limit: int = DEFAULT_LIMIT):
    """Live-scrape today's jobs, score them, cache and return the top matches."""
    if JOBS_SOURCE == "sheet":
        raise HTTPException(400, "Live fetch is disabled in sheet mode (Vercel). "
                                 "Jobs are read from the Google Sheet.")
    jobs = fetch_live(hours_old, limit)
    payload = save_cache(jobs)
    payload["source"] = "live"
    return payload


@app.post("/api/resume/build")
def api_resume_build(payload: dict):
    """Generate ONE tailored resume and stream it back in the same request.

    Body: {title, company, job_url?, description?, format: 'pdf'|'docx'}.
    Rendering happens in memory, so this works identically on local and Vercel
    (no reliance on the file persisting to disk between requests). When running
    locally we also drop a copy in ./resume so the panel + folder stay useful.
    """
    title = (payload.get("title") or "").strip()
    company = (payload.get("company") or "").strip()
    fmt = (payload.get("format") or "pdf").lower()
    if not title or not company:
        raise HTTPException(400, "title and company are required")
    if fmt not in ("pdf", "docx"):
        raise HTTPException(400, "format must be 'pdf' or 'docx' (one per request)")

    # Prefer an explicit description; else pull it from the cached job by URL.
    description = payload.get("description") or ""
    if not description and payload.get("job_url"):
        cached = _find_cached_job(payload["job_url"])
        if cached:
            description = cached.get("description", "")

    matched = RB.find_matched_skills(description)
    skills = RB.tailor_skills(matched)
    summary = RB.build_summary(matched)
    base = RB.base_filename(company, title)
    fname = f"{base}.{fmt}"

    buf = io.BytesIO()
    if fmt == "pdf":
        RB.render_pdf(buf, summary, skills, matched, title, company)
        media = "application/pdf"
    else:
        RB.render_docx(buf, summary, skills, matched, title, company)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    data = buf.getvalue()

    # Local convenience: keep a copy on disk for the "Generated resumes" panel.
    if not ON_VERCEL:
        os.makedirs(RESUME_DIR, exist_ok=True)
        with open(os.path.join(RESUME_DIR, fname), "wb") as f:
            f.write(data)

    from fastapi import Response
    return Response(
        content=data, media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "X-Emphasized": str(len(matched)),
        },
    )


@app.get("/api/resumes")
def api_list_resumes():
    if not os.path.isdir(RESUME_DIR):
        return {"resumes": []}
    out = []
    for f in sorted(os.listdir(RESUME_DIR)):
        if f.endswith((".pdf", ".docx")):
            out.append({"name": f, "kb": round(os.path.getsize(os.path.join(RESUME_DIR, f)) / 1024)})
    return {"resumes": out}


@app.get("/api/resume/file/{name}")
def api_download(name: str):
    name = os.path.basename(name)  # prevent path traversal
    path = os.path.join(RESUME_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(404, "not found")
    media = ("application/pdf" if name.endswith(".pdf")
             else "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    return FileResponse(path, media_type=media, filename=name)


@app.delete("/api/resume/file/{name}")
def api_delete(name: str):
    name = os.path.basename(name)
    path = os.path.join(RESUME_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(404, "not found")
    os.remove(path)
    return {"deleted": name}


# --------------------------------------------------------------------------- #
# UI  (single self-contained page - no build step, works on Vercel too)
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def index():
    live = JOBS_SOURCE != "sheet"
    return HTMLResponse(INDEX_HTML.replace("__LIVE__", "true" if live else "false"))


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Aman Kabra - Jobs & Resume</title>
<style>
  :root { --bg:#0f1623; --card:#16203140; --line:#27364d; --ink:#e7eef9; --mut:#8aa0bd;
          --accent:#3b82f6; --good:#16331a; --goodt:#9be7a4; --amb:#3a3417; --ambt:#f0d98a;
          --bad:#3a1f1f; --badt:#f0a0a0; }
  * { box-sizing:border-box; }
  body { margin:0; background:#0b111c; color:var(--ink); font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif; }
  header { padding:18px 24px; border-bottom:1px solid var(--line); display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
  header h1 { font-size:18px; margin:0; }
  header .sub { color:var(--mut); font-size:12px; }
  main { padding:20px 24px; max-width:1200px; margin:0 auto; }
  .bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:16px; }
  button { background:var(--accent); color:#fff; border:0; padding:8px 14px; border-radius:8px; cursor:pointer; font-size:13px; }
  button.secondary { background:#1e293b; color:var(--ink); border:1px solid var(--line); }
  button:disabled { opacity:.5; cursor:default; }
  input, select { background:#0e1726; color:var(--ink); border:1px solid var(--line); border-radius:7px; padding:7px 9px; font-size:13px; }
  .note { color:var(--mut); font-size:12px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--mut); font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
  tr:hover td { background:#10192880; }
  .score { font-weight:700; padding:2px 8px; border-radius:6px; display:inline-block; min-width:34px; text-align:center; }
  .s-hi { background:var(--good); color:var(--goodt); }
  .s-md { background:var(--amb); color:var(--ambt); }
  .s-lo { background:var(--bad); color:var(--badt); }
  a { color:#7db0ff; text-decoration:none; } a:hover { text-decoration:underline; }
  .chips { display:flex; gap:4px; flex-wrap:wrap; margin-top:4px; }
  .chip { font-size:10px; color:var(--mut); border:1px solid var(--line); border-radius:10px; padding:1px 7px; }
  .row-actions { display:flex; gap:6px; align-items:center; }
  .panel { margin-top:30px; border-top:1px solid var(--line); padding-top:16px; }
  .pill { font-size:11px; padding:2px 8px; border:1px solid var(--line); border-radius:20px; color:var(--mut); }
  .empty { color:var(--mut); padding:30px 0; text-align:center; }
  .toast { position:fixed; right:18px; bottom:18px; background:#1e293b; border:1px solid var(--line);
           padding:10px 14px; border-radius:8px; max-width:360px; font-size:13px; }
  .spin { display:inline-block; width:14px; height:14px; border:2px solid #fff5; border-top-color:#fff;
          border-radius:50%; animation:r .8s linear infinite; vertical-align:-2px; }
  @keyframes r { to { transform:rotate(360deg); } }
</style>
</head>
<body>
<header>
  <h1>Aman Kabra - Jobs & Resume</h1>
  <span class="pill" id="modePill">mode</span>
  <span class="sub" id="status"></span>
</header>
<main>
  <div class="bar">
    <button id="fetchBtn">Fetch today's jobs</button>
    <label class="note">Posted within
      <select id="hours"><option value="24">24h</option><option value="48">48h</option><option value="72">72h</option><option value="168">7d</option></select>
    </label>
    <label class="note">Top <input id="limit" type="number" value="50" min="5" max="100" style="width:60px"/></label>
    <button class="secondary" id="reloadBtn">Reload cached</button>
    <span class="note" id="count"></span>
  </div>

  <table id="jobsTable">
    <thead><tr>
      <th>#</th><th>Match</th><th>Job</th><th>Company</th><th>Location</th>
      <th>Site</th><th>Posted</th><th>Apply</th><th>Resume</th>
    </tr></thead>
    <tbody id="jobsBody"><tr><td colspan="9" class="empty">No jobs yet - click "Fetch today's jobs".</td></tr></tbody>
  </table>

  <div class="panel">
    <div class="bar">
      <strong>Generated resumes</strong>
      <button class="secondary" id="refreshResumes">Refresh</button>
    </div>
    <table>
      <thead><tr><th>File</th><th>Size</th><th>Actions</th></tr></thead>
      <tbody id="resumesBody"><tr><td colspan="3" class="empty">None yet.</td></tr></tbody>
    </table>
  </div>
</main>
<div id="toast"></div>

<script>
const LIVE = __LIVE__;
const $ = s => document.querySelector(s);
let jobs = [];

function toast(msg, ms=3500){ const t=$('#toast'); t.innerHTML='<div class="toast">'+msg+'</div>';
  clearTimeout(window._tt); window._tt=setTimeout(()=>t.innerHTML='',ms); }
function scoreClass(s){ return s>=65?'s-hi':s>=45?'s-md':'s-lo'; }
function esc(s){ return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

function renderJobs(){
  const b=$('#jobsBody');
  if(!jobs.length){ b.innerHTML='<tr><td colspan="9" class="empty">No jobs.</td></tr>'; return; }
  b.innerHTML = jobs.map((j,i)=>{
    const chips=(j.matched||[]).slice(0,6).map(m=>'<span class="chip">'+esc(m.split(' (')[0])+'</span>').join('');
    return `<tr>
      <td>${i+1}</td>
      <td><span class="score ${scoreClass(j.score)}">${j.score}</span></td>
      <td><strong>${esc(j.title)}</strong>${j.is_remote?' <span class="chip">remote</span>':''}<div class="chips">${chips}</div></td>
      <td>${esc(j.company)}</td>
      <td>${esc(j.location)}</td>
      <td>${esc(j.site)}</td>
      <td>${esc(j.date_posted)}</td>
      <td>${j.job_url?'<a href="'+esc(j.job_url)+'" target="_blank" rel="noopener">Open</a>':''}</td>
      <td><div class="row-actions">
        <select id="fmt${i}"><option value="both">PDF+Word</option><option value="pdf">PDF</option><option value="docx">Word</option></select>
        <button class="secondary" onclick="makeResume(${i})">Generate</button>
      </div></td>
    </tr>`;
  }).join('');
}

async function loadJobs(){
  const r = await fetch('/api/jobs?limit='+($('#limit').value||50));
  const d = await r.json();
  jobs = d.jobs||[];
  $('#count').textContent = jobs.length+' jobs'+(d.fetched_at?(' · fetched '+d.fetched_at):'');
  renderJobs();
}

async function fetchJobs(){
  if(!LIVE){ toast('Live fetch is off in Vercel mode - showing Google Sheet jobs.'); return loadJobs(); }
  const btn=$('#fetchBtn'); btn.disabled=true; const old=btn.textContent;
  btn.innerHTML='<span class="spin"></span> Scraping (can take ~1 min)…';
  try{
    const r=await fetch('/api/fetch?hours_old='+$('#hours').value+'&limit='+($('#limit').value||50),{method:'POST'});
    const d=await r.json();
    if(!r.ok){ toast('Fetch failed: '+(d.detail||r.status)); }
    else { jobs=d.jobs||[]; $('#count').textContent=jobs.length+' jobs · fetched '+d.fetched_at; renderJobs();
           toast(jobs.length+' jobs scored against your resume.'); }
  }catch(e){ toast('Fetch error: '+e); }
  finally{ btn.disabled=false; btn.textContent=old; }
}

async function makeResume(i){
  const j=jobs[i]; const sel=$('#fmt'+i).value;
  const fmts = sel==='both' ? ['pdf','docx'] : [sel];
  toast('Building resume for '+esc(j.title)+'…');
  for(const f of fmts){ await downloadResume(j,f); }
  loadResumes();
}
async function downloadResume(j,fmt){
  const r=await fetch('/api/resume/build',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title:j.title,company:j.company,job_url:j.job_url,description:j.description,format:fmt})});
  if(!r.ok){ const d=await r.json().catch(()=>({})); toast('Resume failed: '+(d.detail||r.status)); return; }
  const blob=await r.blob();
  const cd=r.headers.get('Content-Disposition')||'';
  const m=cd.match(/filename="?([^";]+)"?/);
  const name=(m&&m[1])||('resume.'+fmt);
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=name; document.body.appendChild(a);
  a.click(); a.remove(); URL.revokeObjectURL(url);
  toast('Downloaded '+name+' · emphasized '+(r.headers.get('X-Emphasized')||0)+' skills');
}

async function loadResumes(){
  const r=await fetch('/api/resumes'); const d=await r.json();
  const b=$('#resumesBody');
  if(!d.resumes.length){ b.innerHTML='<tr><td colspan="3" class="empty">None yet.</td></tr>'; return; }
  b.innerHTML=d.resumes.map(f=>`<tr>
    <td>${esc(f.name)}</td><td>${f.kb} KB</td>
    <td class="row-actions">
      <a href="/api/resume/file/${encodeURIComponent(f.name)}">Download</a>
      <button class="secondary" onclick="delResume('${esc(f.name)}')">Delete</button>
    </td></tr>`).join('');
}
async function delResume(name){
  if(!confirm('Delete '+name+'?')) return;
  await fetch('/api/resume/file/'+encodeURIComponent(name),{method:'DELETE'});
  toast('Deleted '+name); loadResumes();
}

$('#fetchBtn').onclick=fetchJobs;
$('#reloadBtn').onclick=loadJobs;
$('#refreshResumes').onclick=loadResumes;
$('#modePill').textContent = LIVE ? 'LOCAL · live scrape' : 'VERCEL · Google Sheet';
if(!LIVE){ $('#fetchBtn').textContent='Load jobs from Sheet'; $('#hours').style.display='none'; }
loadJobs(); loadResumes();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    print(f"Job & Resume dashboard -> http://localhost:{port}  (mode: {JOBS_SOURCE})")
    uvicorn.run(app, host="127.0.0.1", port=port)
