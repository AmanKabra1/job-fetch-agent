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
import re
import json
import base64
import logging
import datetime as dt

def _quiet_jobspy():
    """Silence python-jobspy's noisy per-board logs. It names each board logger
    'JobSpy:<Board>' with its own handler + propagate=False, and resets their
    level on every scrape_jobs() call — so setLevel() doesn't stick. Disabling
    them does (jobspy never re-enables), and the blocked-board ERRORs (ZipRecruiter
    /Naukri/Bayt/Glassdoor 403/recaptcha from a home IP) are expected & handled.
    We also pre-disable lower/upper-case board name variants because jobspy
    creates a fresh 'JobSpy:<site>' logger at call time for its 'finished
    scraping' INFO line."""
    names = {n for n in logging.root.manager.loggerDict if n.startswith("JobSpy:")}
    for site in ("LinkedIn", "Linkedin", "linkedin", "Indeed", "indeed", "Google",
                 "google", "Glassdoor", "glassdoor", "ZipRecruiter", "zip_recruiter",
                 "Naukri", "naukri", "Bayt", "bayt", "BDJobs", "bdjobs"):
        names.add(f"JobSpy:{site}")
    for name in names:
        logging.getLogger(name).disabled = True

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from starlette.concurrency import run_in_threadpool

import resume_tailor as RT
import resume_builder as RB
import extra_sources as ES


def _slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(text or "")).strip("-")
    return text or "resume"

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

# Live-scrape defaults.
# Every board python-jobspy supports. Some (zip_recruiter is US/Canada only,
# bayt is Middle East) may return little for India — that's fine, they're tried
# resiliently and a board returning nothing never aborts the run.
SITES = ["linkedin", "indeed", "google", "glassdoor", "zip_recruiter", "naukri", "bayt"]
LOCATION = "India"
COUNTRY_INDEED = "India"
DEFAULT_HOURS_OLD = 24
DEFAULT_LIMIT = 50
RESULTS_PER_TERM = 20

# Generic last-resort search terms when the user gives no position and we can't
# infer a role from their resume. Kept deliberately broad.
DEFAULT_SEARCH_TERMS = ["software developer", "software engineer"]

# Role phrases we look for in a resume (or position box) to build search terms.
_ROLE_HINTS = [
    ("backend", "Backend Developer"), ("back-end", "Backend Developer"),
    ("back end", "Backend Developer"), ("frontend", "Frontend Developer"),
    ("front-end", "Frontend Developer"), ("front end", "Frontend Developer"),
    ("full stack", "Full Stack Developer"), ("fullstack", "Full Stack Developer"),
    ("data engineer", "Data Engineer"), ("data scien", "Data Scientist"),
    ("data analyst", "Data Analyst"), ("devops", "DevOps Engineer"),
    ("machine learning", "Machine Learning Engineer"), ("ml engineer", "Machine Learning Engineer"),
    ("android", "Android Developer"), ("ios ", "iOS Developer"),
    ("mobile", "Mobile Developer"), ("qa ", "QA Engineer"),
    ("test engineer", "QA Engineer"), ("cloud engineer", "Cloud Engineer"),
    ("site reliability", "SRE"), ("software engineer", "Software Engineer"),
    ("software developer", "Software Developer"),
]
# Fallback: a dominant language -> a sensible search term.
_LANG_HINTS = [
    ("nestjs", "Node.js Developer"), ("node", "Node.js Developer"),
    ("django", "Python Developer"), ("fastapi", "Python Developer"),
    ("python", "Python Developer"), ("spring", "Java Developer"),
    ("java", "Java Developer"), ("react", "React Developer"),
    ("angular", "Angular Developer"), ("golang", "Go Developer"),
    (".net", ".NET Developer"), ("php", "PHP Developer"),
]

# Google Sheet (sheet mode)
SHEET_NAME = os.environ.get("SHEET_NAME", "Job Listings")
WORKSHEET_NAME = os.environ.get("WORKSHEET_NAME", "jobs")

app = FastAPI(title="Job Finder & Resume Tailor")


# --------------------------------------------------------------------------- #
# JOB SOURCES
# --------------------------------------------------------------------------- #
def _employees_min(raw) -> int:
    """Best-effort: smallest headcount from a jobspy 'company_num_employees'
    string like '201-500', '5,001-10,000', '10000+'. 0 if unknown."""
    s = str(raw or "").replace(",", "")
    nums = re.findall(r"\d+", s)
    return int(nums[0]) if nums else 0


def _labels_in(text: str) -> set:
    """Skill labels (from the shared lexicon) recognised in a blob of text."""
    if not text or not text.strip():
        return set()
    tl = " " + text.lower() + " "
    return {RT._clean_label(label) for label, aliases in RT.SKILL_LEXICON.items()
            if any(RT._word_in(a, tl) for a in aliases)}


def _derive_search_terms(position: str = "", resume_text: str = ""):
    """Build the board search terms generically (no hardcoded profile):
       1. explicit position(s) the user typed (comma/newline separated), else
       2. roles inferred from the uploaded resume, else
       3. a dominant language in the resume -> a role, else
       4. a broad generic default."""
    if position and position.strip():
        terms = [t.strip() for t in re.split(r"[,\n;]+", position) if t.strip()]
        if terms:
            return terms[:6]

    text = (resume_text or "").lower()
    if text.strip():
        roles, seen = [], set()
        for needle, role in _ROLE_HINTS:
            if needle in text and role not in seen:
                seen.add(role)
                roles.append(role)
        if not roles:
            for needle, role in _LANG_HINTS:
                if needle in text and role not in seen:
                    seen.add(role)
                    roles.append(role)
        if roles:
            return roles[:6]

    return list(DEFAULT_SEARCH_TERMS)


def _score_and_rank(rows, limit, target_text=None):
    """Rank jobs generically. If target_text (the user's resume / JD / skills)
    names any skills, rank by overlap with THOSE; otherwise rank by how many
    recognised tech skills each posting mentions (a generic relevance signal)."""
    targets = _labels_in(target_text or "")
    scored = []
    for r in rows:
        title = str(r.get("title") or "")
        desc = str(r.get("description") or "")
        job_labels = _labels_in(f"{title} {desc}")
        if targets:
            overlap = targets & job_labels
            score = round(100 * len(overlap) / len(targets))
            matched = sorted(overlap)
        else:
            matched = sorted(job_labels)
            score = min(100, len(job_labels) * 12)

        # Company size is only exposed by a few boards (mostly LinkedIn) and is
        # usually blank. When present, gently prefer established companies
        # (>=150 employees) — a soft boost, never a hard filter, so jobs with
        # unknown size are NEVER dropped.
        employees = _employees_min(r.get("company_num_employees"))
        if employees >= 150:
            score = score + 5
        score = max(0, min(100, score))

        scored.append({
            "score": score,
            "matched": matched,
            "title": title,
            "company": str(r.get("company") or ""),
            "location": str(r.get("location") or ""),
            "site": str(r.get("site") or ""),
            "date_posted": str(r.get("date_posted") or ""),
            "is_remote": bool(r.get("is_remote")),
            "employees": employees,
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


def fetch_live(hours_old: int, limit: int, remote_only: bool = False,
               target_text=None, search_terms=None):
    """Scrape every board (local only). jobspy is imported lazily.

    search_terms drive the board queries (derived from the user's position /
    resume). jobspy isolates per-board failures internally, so passing the full
    SITES list in one call means a board that returns nothing (or errors) never
    aborts the run — the other boards still come back.
    """
    from jobspy import scrape_jobs  # heavy import, only when actually fetching
    import pandas as pd
    _quiet_jobspy()

    terms = list(search_terms) if search_terms else list(DEFAULT_SEARCH_TERMS)
    location = "Remote" if remote_only else LOCATION
    frames = []
    for term in terms:
        gst = f"{term} jobs" + (" remote" if remote_only else f" near {LOCATION} since yesterday")
        try:
            df = scrape_jobs(
                site_name=SITES,
                search_term=(term + " remote") if remote_only else term,
                google_search_term=gst,
                location=location,
                results_wanted=RESULTS_PER_TERM,
                hours_old=hours_old,
                country_indeed=COUNTRY_INDEED,
                is_remote=bool(remote_only),
                linkedin_fetch_description=True,
            )
        except Exception as e:
            print(f"  ! {term!r} failed: {e}", flush=True)
            continue
        if df is not None and not df.empty:
            frames.append(df)

    rows = []
    if frames:
        combined = pd.concat(frames, ignore_index=True).fillna("")
        rows = combined.to_dict("records")

    # Add real remote roles from free APIs (Remotive + RemoteOK) — startups and
    # established companies that the jobspy boards miss. All remote by nature.
    try:
        rows += ES.fetch_extra(terms, per_term=15, max_age_hours=hours_old)
    except Exception as e:
        print(f"  ! extra sources failed: {e}", flush=True)

    if not rows:
        return []
    ranked = _score_and_rank(rows, limit * 3 if remote_only else limit, target_text)
    if remote_only:
        ranked = [j for j in ranked if j.get("is_remote")][:limit]
    return ranked


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
async def api_fetch(
    hours_old: int = DEFAULT_HOURS_OLD,
    limit: int = DEFAULT_LIMIT,
    remote: bool = False,
    position: str = Form(""),
    file: UploadFile = File(None),
    jd: str = Form(""),
    skills: str = Form(""),
):
    """Live-scrape jobs, score them, cache and return the top matches.

    All inputs are optional. A resume file, JD and/or skills guide the *ranking*
    (jobs ranked by how well they match the combined text). The position box —
    or, if blank, roles inferred from the uploaded resume — drives *what we
    search the boards for*. With nothing provided, a broad default is used.
    """
    if JOBS_SOURCE == "sheet":
        raise HTTPException(400, "Live fetch is disabled in sheet mode (Vercel). "
                                 "Jobs are read from the Google Sheet.")

    # Build the ranking target + read the resume once (used for both ranking and
    # role inference when no explicit position is given).
    resume_text = ""
    if file is not None and file.filename:
        try:
            data = await file.read()
            if data:
                resume_text = RT.extract_text(file.filename, data)
        except Exception as e:
            print(f"  ! could not read uploaded resume: {e}", flush=True)

    parts = [p for p in (jd, skills, resume_text) if p and p.strip()]
    target_text = "\n".join(parts)
    search_terms = _derive_search_terms(position, resume_text)

    # fetch_live is blocking and slow (scraping) -> threadpool.
    jobs = await run_in_threadpool(
        fetch_live, hours_old, limit, remote, target_text, search_terms)
    payload = save_cache(jobs)
    payload["source"] = "live"
    payload["remote_only"] = remote
    payload["guided"] = bool(target_text.strip())
    payload["search_terms"] = search_terms
    return payload


def _save_resume_copy(fname: str, data: bytes):
    """Keep a local copy so generated files show up in the 'Generated resumes'
    panel. No-op on Vercel (read-only filesystem)."""
    if ON_VERCEL:
        return
    os.makedirs(RESUME_DIR, exist_ok=True)
    with open(os.path.join(RESUME_DIR, os.path.basename(fname)), "wb") as f:
        f.write(data)


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@app.post("/api/resume/build")
def api_resume_build(payload: dict):
    """Generate the saved resume (resume_profile.py) in its one-page format,
    tailored to a pasted JD: matched skills are reordered to the front of their
    category and bolded, and the summary leads with the matching stack. Returns
    PDF and/or Word as base64. This is the user's OWN template — separate from
    the generic 'Find jobs' section.
    """
    description = (payload.get("description") or "").strip()
    title = (payload.get("title") or "").strip() or "Resume"
    company = (payload.get("company") or "").strip() or "Target"
    fmt = (payload.get("format") or "both").lower()
    if fmt not in ("pdf", "docx", "both"):
        raise HTTPException(400, "format must be 'pdf', 'docx', or 'both'")

    matched = RB.find_matched_skills(description)
    skills = RB.tailor_skills(matched)
    summary = RB.build_summary(matched)
    base = RB.base_filename(company, title)

    out_files = []
    if fmt in ("pdf", "both"):
        buf = io.BytesIO()
        RB.render_pdf(buf, summary, skills, matched, title, company)
        data = buf.getvalue()
        name = base + ".pdf"
        _save_resume_copy(name, data)
        out_files.append({"name": name, "mime": "application/pdf",
                          "b64": base64.b64encode(data).decode()})
    if fmt in ("docx", "both"):
        buf = io.BytesIO()
        RB.render_docx(buf, summary, skills, matched, title, company)
        data = buf.getvalue()
        name = base + ".docx"
        _save_resume_copy(name, data)
        out_files.append({"name": name, "mime": _DOCX_MIME,
                          "b64": base64.b64encode(data).decode()})

    return {"files": out_files, "emphasized": sorted(matched)}


@app.post("/api/resume/tailor")
async def api_resume_tailor(
    file: UploadFile = File(...),
    jd: str = Form(""),
    skills: str = Form(""),
    fmt: str = Form("both"),
):
    """Tailor an UPLOADED resume to a JD / skills WITHOUT changing its style.

    Multipart form: file (.docx|.pdf, required), jd (optional), skills (optional),
    fmt = pdf | docx | both. Returns JSON with the tailored file(s) base64-encoded
    plus an analysis (skills highlighted, skills added, and suggestions the JD
    asked for that the resume lacks — never silently added).
    """
    fmt = (fmt or "both").lower()
    if fmt not in ("pdf", "docx", "both"):
        raise HTTPException(400, "fmt must be 'pdf', 'docx', or 'both'")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Uploaded file is empty.")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 10 MB).")

    want_pdf = fmt in ("pdf", "both")
    want_docx = fmt in ("docx", "both")

    # tailor_upload is blocking (parses files, launches Word for PDF) -> threadpool.
    try:
        result = await run_in_threadpool(
            RT.tailor_upload, file.filename or "resume", data,
            jd or "", skills or "", want_pdf, want_docx,
        )
    except ValueError as e:                      # bad/empty/unsupported upload
        raise HTTPException(400, str(e))
    except Exception as e:                        # unexpected
        raise HTTPException(500, f"Tailoring failed: {e}")

    base = _slugify(os.path.splitext(os.path.basename(file.filename or "resume"))[0])
    base = (base or "resume") + "_tailored"

    out_files = []
    if result.get("docx"):
        name = base + ".docx"
        _save_resume_copy(name, result["docx"])
        out_files.append({
            "name": name,
            "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "b64": base64.b64encode(result["docx"]).decode(),
        })
    if result.get("pdf"):
        name = base + ".pdf"
        _save_resume_copy(name, result["pdf"])
        out_files.append({
            "name": name,
            "mime": "application/pdf",
            "b64": base64.b64encode(result["pdf"]).decode(),
        })

    return {
        "analysis": result["analysis"],
        "layout_preserved": result["layout_preserved"],
        "pdf_note": result.get("pdf_note"),
        "files": out_files,
    }


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
<title>Job Finder & Resume Tailor</title>
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
  input, select, textarea { background:#0e1726; color:var(--ink); border:1px solid var(--line); border-radius:7px; padding:7px 9px; font-size:13px; font-family:inherit; }
  textarea { width:100%; resize:vertical; min-height:74px; }
  .note { color:var(--mut); font-size:12px; }
  .field { margin-bottom:10px; }
  .field label { display:block; color:var(--mut); font-size:12px; margin-bottom:4px; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  @media (max-width:760px){ .grid2 { grid-template-columns:1fr; } }
  .tagrow { display:flex; gap:5px; flex-wrap:wrap; margin-top:6px; }
  .tag { font-size:11px; border-radius:10px; padding:2px 8px; border:1px solid var(--line); }
  .tag.have { background:var(--good); color:var(--goodt); }
  .tag.add { background:#1b2c3f; color:#9bc7ff; }
  .tag.miss { background:var(--amb); color:var(--ambt); }
  .switch { display:inline-flex; align-items:center; gap:6px; cursor:pointer; }
  section { margin-bottom:34px; }
  .sec-title { font-size:15px; margin:0 0 4px; display:flex; align-items:center; gap:8px; }
  .sec-num { background:var(--accent); color:#fff; border-radius:6px; font-size:12px; padding:1px 8px; }
  .card { border:1px solid var(--line); background:#0e172680; border-radius:10px; padding:14px 16px; margin:12px 0 16px; }
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
  <h1>Job Finder &amp; Resume Tailor</h1>
  <span class="pill" id="modePill">mode</span>
  <span class="sub" id="status"></span>
</header>
<main>

  <!-- ============ SECTION 1 — FIND JOBS ============ -->
  <section id="findJobs">
    <h2 class="sec-title"><span class="sec-num">1</span> Find jobs</h2>
    <p class="note">Everything below is <b>optional</b>. Upload your resume and we infer the roles to search and rank jobs to it; type a position to search exactly that; add a JD or skills to sharpen the ranking. Give nothing and a broad default search runs. This section only finds jobs.</p>
    <div class="card">
      <div class="grid2">
        <div class="field">
          <label>Resume <span style="opacity:.7">(optional, .docx/.pdf — infers roles &amp; ranks to it)</span></label>
          <input type="file" id="jfFile" accept=".docx,.pdf"/>
        </div>
        <div class="field">
          <label>Position / role to search <span style="opacity:.7">(optional — e.g. "Backend Developer, DevOps")</span></label>
          <input type="text" id="jfPosition" placeholder="Leave blank to infer from your resume" style="width:100%"/>
        </div>
      </div>
      <div class="grid2">
        <div class="field">
          <label>Skills to target <span style="opacity:.7">(optional, comma-separated)</span></label>
          <textarea id="jfSkills" placeholder="e.g. Node.js, AWS, Kafka" style="min-height:46px"></textarea>
        </div>
        <div class="field">
          <label>Target job description <span style="opacity:.7">(optional — finds similar jobs)</span></label>
          <textarea id="jfJD" placeholder="Paste a job description to find jobs like it…" style="min-height:46px"></textarea>
        </div>
      </div>
      <div class="bar" style="margin-bottom:0">
        <button id="fetchBtn">Fetch jobs</button>
        <label class="note">Posted within
          <select id="hours"><option value="24">24h</option><option value="48">48h</option><option value="72">72h</option><option value="168">7d</option></select>
        </label>
        <label class="note">Top <input id="limit" type="number" value="50" min="5" max="100" style="width:60px"/></label>
        <label class="switch note" title="Only return jobs marked remote"><input type="checkbox" id="remoteOnly"/> Remote only</label>
        <button class="secondary" id="reloadBtn">Reload cached</button>
        <span class="note" id="count"></span>
      </div>
    </div>
    <p class="note" style="margin:-4px 0 12px">Boards: LinkedIn · Indeed · Google · Glassdoor · ZipRecruiter · Naukri · Bayt · Remotive · RemoteOK — all real, directly-posted listings (MNCs, startups &amp; remote). Company size shows when the board reports it.</p>

    <table id="jobsTable">
      <thead><tr>
        <th>#</th><th>Match</th><th>Job</th><th>Company</th><th>Size</th><th>Location</th>
        <th>Site</th><th>Posted</th><th>Apply</th><th>Tailor</th>
      </tr></thead>
      <tbody id="jobsBody"><tr><td colspan="10" class="empty">No jobs yet — click "Fetch jobs".</td></tr></tbody>
    </table>
  </section>

  <!-- ============ SECTION 2 — CREATE A RESUME ============ -->
  <section id="createResume" class="panel">
    <h2 class="sec-title"><span class="sec-num">2</span> Create a resume</h2>
    <p class="note">Two ways to build a one-page resume (PDF &amp; Word). This section only builds resumes — it does not search jobs.</p>

    <!-- 2A: generate from the saved profile in the user's own format -->
    <div class="card">
      <div class="bar" style="margin-bottom:8px"><strong>A · From your saved resume (your format)</strong>
        <span class="note">Paste a job description — your one-page resume is generated in your format with the matching skills emphasized.</span>
      </div>
      <div class="grid2">
        <div class="field">
          <label>Target title <span style="opacity:.7">(optional)</span></label>
          <input type="text" id="genTitle" placeholder="e.g. Backend Developer" style="width:100%"/>
        </div>
        <div class="field">
          <label>Company <span style="opacity:.7">(optional)</span></label>
          <input type="text" id="genCompany" placeholder="e.g. Acme" style="width:100%"/>
        </div>
      </div>
      <div class="field">
        <label>Job description <span style="opacity:.7">(optional — paste to tailor the emphasis)</span></label>
        <textarea id="genJD" placeholder="Paste the full job description here…"></textarea>
      </div>
      <div class="bar" style="margin-bottom:0">
        <label class="note">Format
          <select id="genFmt"><option value="both">PDF+Word</option><option value="pdf">PDF</option><option value="docx">Word</option></select>
        </label>
        <button id="genBtn">Generate resume</button>
        <span class="note" id="genResult"></span>
      </div>
    </div>

    <!-- 2B: tailor an uploaded resume, preserving its format -->
    <div class="card">
      <div class="bar" style="margin-bottom:8px"><strong>B · Tailor a resume you upload</strong>
        <span class="note">Keeps your uploaded file's exact format and only works the matching requirements in.</span>
      </div>
      <div class="grid2">
        <div>
          <div class="field">
            <label>Your resume <span style="opacity:.7">(.docx keeps your exact layout · .pdf is rebuilt)</span></label>
            <input type="file" id="tailorFile" accept=".docx,.pdf"/>
          </div>
          <div class="field">
            <label>Job description <span style="opacity:.7">(optional)</span></label>
            <textarea id="tailorJD" placeholder="Paste the full job description here…"></textarea>
          </div>
          <div class="field">
            <label>Skills to emphasize <span style="opacity:.7">(optional, comma-separated)</span></label>
            <textarea id="tailorSkills" placeholder="e.g. GraphQL, Kubernetes, Kafka" style="min-height:46px"></textarea>
          </div>
          <div class="bar" style="margin-bottom:0">
            <label class="note">Format
              <select id="tailorFmt"><option value="both">PDF+Word</option><option value="docx">Word</option><option value="pdf">PDF</option></select>
            </label>
            <button id="tailorBtn">Create resume</button>
          </div>
        </div>
        <div id="tailorResult" class="note">Your tailored-resume summary will appear here.</div>
      </div>
    </div>

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
  </section>
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
  if(!jobs.length){ b.innerHTML='<tr><td colspan="10" class="empty">No jobs.</td></tr>'; return; }
  b.innerHTML = jobs.map((j,i)=>{
    const chips=(j.matched||[]).slice(0,6).map(m=>'<span class="chip">'+esc(m.split(' (')[0])+'</span>').join('');
    const size=j.employees>=150?(j.employees>=1000?(Math.floor(j.employees/1000)+'k+'):(j.employees+'+')):'';
    return `<tr>
      <td>${i+1}</td>
      <td><span class="score ${scoreClass(j.score)}">${j.score}</span></td>
      <td><strong>${esc(j.title)}</strong>${j.is_remote?' <span class="chip">remote</span>':''}<div class="chips">${chips}</div></td>
      <td>${esc(j.company)}</td>
      <td class="note">${size}</td>
      <td>${esc(j.location)}</td>
      <td>${esc(j.site)}</td>
      <td>${esc(j.date_posted)}</td>
      <td>${j.job_url?'<a href="'+esc(j.job_url)+'" target="_blank" rel="noopener">Open</a>':''}</td>
      <td><button class="secondary" onclick="useInTailor(${i})">Tailor to this &#8595;</button></td>
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
  btn.innerHTML='<span class="spin"></span> Searching (can take ~1 min)…';
  try{
    const remote=$('#remoteOnly').checked?'&remote=true':'';
    const fd=new FormData();
    const f=$('#jfFile').files[0]; if(f) fd.append('file', f);
    fd.append('position', $('#jfPosition').value||'');
    fd.append('jd', $('#jfJD').value||'');
    fd.append('skills', $('#jfSkills').value||'');
    const r=await fetch('/api/fetch?hours_old='+$('#hours').value+'&limit='+($('#limit').value||50)+remote,
                        {method:'POST', body:fd});
    const d=await r.json();
    if(!r.ok){ toast('Fetch failed: '+(d.detail||r.status)); }
    else { jobs=d.jobs||[]; $('#count').textContent=jobs.length+' jobs · fetched '+d.fetched_at; renderJobs();
           toast(jobs.length+(d.guided?' jobs ranked to your resume/JD/skills.':' jobs ranked by tech relevance.')+(d.search_terms?' Searched: '+d.search_terms.join(', '):'')); }
  }catch(e){ toast('Fetch error: '+e); }
  finally{ btn.disabled=false; btn.textContent=old; }
}

function useInTailor(i){
  const j=jobs[i];
  const jd = j.description || (j.title+' at '+j.company);
  $('#genJD').value = jd; $('#tailorJD').value = jd;
  $('#genTitle').value = j.title||''; $('#genCompany').value = j.company||'';
  document.getElementById('createResume').scrollIntoView({behavior:'smooth'});
  toast('Job sent to §2 — generate from your saved resume (A) or tailor an upload (B).');
}

async function generateResume(){
  const btn=$('#genBtn'); btn.disabled=true; const old=btn.textContent;
  btn.innerHTML='<span class="spin"></span> Generating…';
  $('#genResult').textContent='';
  try{
    const r=await fetch('/api/resume/build',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title:$('#genTitle').value||'', company:$('#genCompany').value||'',
                           description:$('#genJD').value||'', format:$('#genFmt').value})});
    const d=await r.json();
    if(!r.ok){ $('#genResult').textContent='Failed: '+(d.detail||r.status); toast('Generate failed.'); return; }
    (d.files||[]).forEach(f=>b64Download(f.name, f.b64, f.mime));
    const emph=(d.emphasized||[]).length;
    $('#genResult').textContent='Downloaded '+(d.files||[]).map(f=>f.name).join(', ')+(emph?(' · emphasized '+emph+' skills'):'');
    toast('Resume generated in your format.');
    loadResumes();
  }catch(e){ $('#genResult').textContent='Error: '+e; }
  finally{ btn.disabled=false; btn.textContent=old; }
}

function b64Download(name, b64, mime){
  const bytes=atob(b64); const arr=new Uint8Array(bytes.length);
  for(let i=0;i<bytes.length;i++) arr[i]=bytes.charCodeAt(i);
  const blob=new Blob([arr],{type:mime}); const url=URL.createObjectURL(blob);
  const a=document.createElement('a'); a.href=url; a.download=name; document.body.appendChild(a);
  a.click(); a.remove(); URL.revokeObjectURL(url);
}
function tags(list, cls){ return (list||[]).map(s=>'<span class="tag '+cls+'">'+esc(s)+'</span>').join(''); }

async function tailorResume(){
  const f=$('#tailorFile').files[0];
  if(!f){ toast('Pick a resume file (.docx or .pdf) first.'); return; }
  const fd=new FormData();
  fd.append('file', f);
  fd.append('jd', $('#tailorJD').value||'');
  fd.append('skills', $('#tailorSkills').value||'');
  fd.append('fmt', $('#tailorFmt').value);
  const btn=$('#tailorBtn'); btn.disabled=true; const old=btn.textContent;
  btn.innerHTML='<span class="spin"></span> Tailoring…';
  $('#tailorResult').innerHTML='Working — building your resume'+($('#tailorFmt').value!=='docx'?' (PDF via Word can take a few seconds)':'')+'…';
  try{
    const r=await fetch('/api/resume/tailor',{method:'POST',body:fd});
    const d=await r.json();
    if(!r.ok){ $('#tailorResult').textContent='Failed: '+(d.detail||r.status); toast('Tailoring failed.'); return; }
    (d.files||[]).forEach(file=>b64Download(file.name, file.b64, file.mime));
    const a=d.analysis||{};
    let html='';
    html+= d.layout_preserved ? '<div class="note">&#10003; Your original Word layout &amp; style were preserved.</div>'
                              : '<div class="note">&#9888; PDF upload: text was extracted and rebuilt into a clean document (a PDF cannot be edited in place without losing its layout).</div>';
    if(d.pdf_note) html+='<div class="note" style="color:var(--ambt)">PDF note: '+esc(d.pdf_note)+'</div>';
    if((a.present||[]).length) html+='<div class="field" style="margin-top:10px"><label>Highlighted (you already have, JD wants)</label><div class="tagrow">'+tags(a.present,'have')+'</div></div>';
    if((a.typed||[]).length) html+='<div class="field"><label>Added from your skills box</label><div class="tagrow">'+tags(a.typed,'add')+'</div></div>';
    if((a.suggestions||[]).length) html+='<div class="field"><label>JD asks for these — not in your resume (consider adding)</label><div class="tagrow">'+tags(a.suggestions,'miss')+'</div></div>';
    if(!a.had_request) html+='<div class="note" style="margin-top:8px">No JD or skills given — returned your resume unchanged in the chosen format(s).</div>';
    html+='<div class="note" style="margin-top:10px">Downloaded: '+(d.files||[]).map(f=>esc(f.name)).join(', ')+'</div>';
    $('#tailorResult').innerHTML=html;
    toast('Tailored resume downloaded.');
    loadResumes();
  }catch(e){ $('#tailorResult').textContent='Error: '+e; }
  finally{ btn.disabled=false; btn.textContent=old; }
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
$('#genBtn').onclick=generateResume;
$('#tailorBtn').onclick=tailorResume;
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
