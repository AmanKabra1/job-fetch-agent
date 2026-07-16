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
import time
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
import resume_profile as P
import extra_sources as ES


def _slugify(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(text or "")).strip("-")
    return text or "resume"


def _load_dotenv():
    """Load KEY=VALUE lines from a local .env (if present) into the environment,
    so secrets like TAVILY_API_KEY / GOOGLE_CREDENTIALS are set ONCE in a file
    instead of re-typed each run. Real environment variables take precedence."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception as e:
        print(f"  ! could not read .env: {e}", flush=True)


_load_dotenv()

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

# The daily feed committed to the repo by the GitHub Actions cron. It ships
# inside the deployment bundle, so it's readable on Vercel (only WRITES are
# restricted there) with no external service — no Google Sheet, no credentials.
JOBS_FEED = os.path.join(HERE, "data", "jobs.json")

# The hosted app reads the LIVE feed from a dedicated 'feed' branch at runtime
# (via raw.githubusercontent.com) so the GitHub Actions cron can refresh jobs
# WITHOUT committing to main or triggering a Vercel redeploy. It's cached briefly
# in-process and falls back to the bundled data/jobs.json above if the fetch fails
# or no URL is set. Override the URL/branch with the FEED_URL env var.
FEED_URL = os.environ.get(
    "FEED_URL",
    "https://raw.githubusercontent.com/AmanKabra1/job-fetch-agent/feed/data/jobs.json",
)
_FEED_TTL = 300                       # seconds to cache a fetched feed in-process
_FEED_CACHE = {"at": 0.0, "data": None}

# "live"  -> scrape on demand (local).
# "feed"  -> read the committed data/jobs.json (Vercel). "sheet" kept as an alias
#            for older deployments whose env still says JOBS_SOURCE=sheet.
JOBS_SOURCE = os.environ.get("JOBS_SOURCE", "live").lower()

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
    ("sde 1", "Software Engineer"), ("sde-1", "Software Engineer"),
    ("sde i", "Software Engineer"), ("sde1", "Software Engineer"),
    ("langchain", "AI/ML Engineer"), ("langgraph", "AI/ML Engineer"),
    ("agentic", "AI/ML Engineer"), ("ai engineer", "AI/ML Engineer"),
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

# Industry/domain detection for the matching PROFILE. label -> trigger words.
_DOMAIN_HINTS = {
    "fintech": ["fintech", "payments", "banking", "trading", "lending", "insurance", "insurtech", "wealth"],
    "healthcare": ["healthcare", "health care", "medical", "clinical", "hospital", "pharma", "healthtech", "biotech"],
    "e-commerce": ["e-commerce", "ecommerce", "retail", "marketplace", "shopping", "d2c"],
    "edtech": ["edtech", "e-learning", "learning platform", "education technology"],
    "logistics": ["logistics", "supply chain", "delivery", "shipping", "fleet", "mobility"],
    "gaming": ["gaming", "game development", "gamedev", "game studio"],
    "social": ["social media", "social network", "content platform", "creator"],
    "travel": ["travel", "hospitality", "booking", "tourism", "airline"],
    "saas": ["saas", "b2b", "enterprise software"],
    "cybersecurity": ["cybersecurity", "infosec", "security operations", "threat"],
    "ai/ml": ["ai platform", "ml platform", "computer vision", "nlp", "generative ai"],
}
# Degree detection for the PROFILE.education field.
_DEGREE_RE = re.compile(
    r"\b(b\.?tech|b\.?e\.?|bachelor|b\.?sc|b\.?c\.?a|m\.?tech|m\.?sc|m\.?c\.?a|"
    r"master|mba|ph\.?d|b\.?com|diploma)\b", re.I)
_CERT_RE = re.compile(r"\b(certif|certificate|certification|certified)\b", re.I)
# Title words too generic to drive a title-relevance match on their own.
_TITLE_STOP = {"developer", "engineer", "senior", "junior", "sr", "jr", "lead",
               "staff", "principal", "i", "ii", "iii", "the", "a", "of"}
_TITLE_FAMILY = {"developer", "engineer", "programmer", "sde", "architect", "dev"}

# Skill-match gate. A job is kept only if at least MIN_SKILL_RATIO of the skills
# it asks for are skills the PROFILE actually has. If the strict pass leaves too
# few jobs we re-run at RELAX_SKILL_RATIO (and tell the user we relaxed) so the
# page is never empty.
MIN_SKILL_RATIO = 0.6        # >= 60% of a job's required skills must be in profile
RELAX_SKILL_RATIO = 0.30
MIN_KEEP_BEFORE_RELAX = 8

# --------------------------------------------------------------------------- #
# RANKING PREFERENCES
#   Soft signals that nudge jobs up the list — never hard filters.
# --------------------------------------------------------------------------- #
# Big employers (MNCs + large/well-funded startups). Substring match on company.
BIG_COMPANIES = {
    "google", "microsoft", "amazon", "meta", "facebook", "apple", "netflix",
    "adobe", "salesforce", "oracle", "ibm", "sap", "intel", "nvidia", "cisco",
    "vmware", "uber", "airbnb", "atlassian", "stripe", "shopify", "paypal",
    "walmart", "accenture", "deloitte", "pwc", "kpmg", "ey", "tcs", "infosys",
    "wipro", "cognizant", "capgemini", "hcl", "tech mahindra", "mindtree",
    "thoughtworks", "publicis sapient", "epam", "globallogic", "persistent",
    "flipkart", "zomato", "swiggy", "paytm", "razorpay", "cred", "phonepe",
    "zerodha", "freshworks", "zoho", "postman", "browserstack", "groww",
    "meesho", "ola", "oyo", "byju", "unacademy", "dream11", "sharechat",
    "nykaa", "delhivery", "myntra", "makemytrip", "navi", "slice", "upstox",
    "jupiter", "gojek", "grab", "servicenow", "databricks", "snowflake",
    "mongodb", "gitlab", "github", "twilio", "intuit", "expedia", "booking",
    "goldman sachs", "jp morgan", "jpmorgan", "morgan stanley", "barclays",
    "hsbc", "wells fargo", "american express", "mastercard", "visa", "optum",
    "jio", "reliance", "samsung", "qualcomm", "dell", "hp ", "sony", "uber",
    "walmart global", "target", "lowe", "mastercard", "rakuten", "agoda",
}

_SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|architect|manager|head\s+of|"
    r"director|vp|vice\s+president|distinguished|fellow|chief|expert|"
    r"sde\s*(?:3|iii)|sde-?3)\b", re.I)
# Junior/mid markers — exempt a role from the senior reject and give it a boost,
# so initial/mid positions (incl. SDE-1) rank first for a junior/mid candidate.
_JUNIOR_RE = re.compile(
    r"\b(junior|jr\.?|entry[- ]?level|entry|graduate|trainee|fresher|intern|"
    r"sde\s*(?:1|i)\b|sde-?1)\b", re.I)
_YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:years|yrs|yr)\b", re.I)

# India-location detection — you apply from India, so India-based roles
# (onsite / hybrid / WFH-in-India) are the most actionable and rank highest;
# global remote-anywhere roles are still kept but ranked a little lower.
_INDIA_CITIES = (
    "india", "bengaluru", "bangalore", "mumbai", "delhi", "noida", "gurgaon",
    "gurugram", "hyderabad", "pune", "chennai", "kolkata", "ahmedabad", "jaipur",
    "indore", "chandigarh", "kochi", "coimbatore", "nagpur", "surat", "lucknow",
    "thiruvananthapuram", "vadodara", "mysuru", "mysore", "gurgaon/gurugram",
)
_HYBRID_RE = re.compile(
    r"\b(hybrid|work[\s-]?from[\s-]?office|wfo|on[\s-]?site|in[\s-]?office)\b", re.I)


def _india_location(text: str) -> bool:
    """True if the text names India or a major Indian city."""
    t = (text or "").lower()
    return any(c in t for c in _INDIA_CITIES)


def _required_years(text: str) -> int:
    """Largest 'N years' mentioned in a JD (rough seniority signal). 0 if none."""
    yrs = [int(m) for m in _YEARS_RE.findall(text or "") if int(m) <= 20]
    return max(yrs) if yrs else 0


def _min_required_years(text: str) -> int:
    """Smallest 'N years' a JD asks for — the MINIMUM experience floor. 0 if none.
    e.g. '3+ years' -> 3, '2-4 years' -> 4 (the regex only matches the number
    directly before 'years'). Used to reject roles needing many more years than
    the candidate has."""
    yrs = [int(m) for m in _YEARS_RE.findall(text or "") if int(m) <= 20]
    return min(yrs) if yrs else 0


def _infer_years(resume_text: str) -> int:
    """Guess the candidate's years of experience from their resume text."""
    m = re.search(r"(\d{1,2})\s*\+?\s*years?\b", resume_text or "", re.I)
    return int(m.group(1)) if m else 0


def _is_big_company(name: str) -> bool:
    n = " " + (name or "").lower() + " "
    return any(b in n for b in BIG_COMPANIES)


def _salary_lpa(r) -> float:
    """Best-effort annual salary in lakhs (INR). Returns 0 when unknown/ambiguous
    (most boards don't publish salary, especially in India)."""
    amt = r.get("max_amount") or r.get("min_amount")
    try:
        amt = float(amt)
    except (TypeError, ValueError):
        return 0.0
    if amt <= 0:
        return 0.0
    interval = str(r.get("interval") or "").lower()
    if "month" in interval:
        amt *= 12
    elif "hour" in interval or "day" in interval or "week" in interval:
        return 0.0  # too noisy to annualise reliably
    # Heuristic: large rupee figures -> lakhs; ignore small (likely USD/hourly).
    return amt / 100000.0 if amt >= 100000 else 0.0


# Your current pay (LPA). Jobs that explicitly pay MORE than this are boosted so
# they float to the top — but jobs with unknown salary are never hidden (most
# boards don't publish pay). Override with the CURRENT_LPA env var.
try:
    CURRENT_LPA = float(os.environ.get("CURRENT_LPA", "6.3"))
except ValueError:
    CURRENT_LPA = 6.3


def _salary_boost(lpa: float) -> int:
    """Rank-up jobs paying above your current salary; 0 for unknown/at-or-below
    (we never penalise or hide unknown-salary jobs)."""
    if not lpa or lpa <= CURRENT_LPA:
        return 0
    return min(15, round((lpa - CURRENT_LPA) * 2))


def _days_old(date_posted) -> float:
    """How many days ago a job was posted (best-effort). Returns a large number
    when the date is missing/unparseable so unknown-date jobs don't rank as fresh.
    Accepts a string ('YYYY-MM-DD'), a datetime.date, or a datetime.datetime —
    jobspy and the career-page sources return any of these."""
    if isinstance(date_posted, dt.datetime):
        date_posted = date_posted.date()
    if isinstance(date_posted, dt.date):
        return max(0.0, (dt.date.today() - date_posted).days)
    s = (str(date_posted or "")).strip()[:10]
    if not s:
        return 9999.0
    try:
        d = dt.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return 9999.0
    return max(0.0, (dt.date.today() - d).days)


def _recency_boost(date_posted: str) -> int:
    """Boost the freshest postings so latest openings sort to the top."""
    d = _days_old(date_posted)
    if d <= 1:
        return 12
    if d <= 3:
        return 8
    if d <= 7:
        return 4
    if d <= 14:
        return 1
    return 0


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


def _ordered_labels(text: str) -> list:
    """Skill labels recognised in `text`, ordered by where they FIRST appear (so
    the leading skills in a resume rank as the candidate's primary stack — unlike
    _labels_in() which returns an unordered set)."""
    if not text or not text.strip():
        return []
    tl = " " + text.lower() + " "
    hits = []
    for label, aliases in RT.SKILL_LEXICON.items():
        positions = [tl.find(a.strip().lower()) for a in aliases]
        positions = [p for p in positions if p >= 0]
        if positions and any(RT._word_in(a, tl) for a in aliases):
            hits.append((min(positions), RT._clean_label(label)))
    hits.sort()
    out, seen = [], set()
    for _, lab in hits:
        if lab not in seen:
            seen.add(lab)
            out.append(lab)
    return out


def _experience_level(years: int) -> str:
    """Map total years -> level band."""
    if years <= 2:
        return "JUNIOR"
    if years <= 5:
        return "MID"
    if years <= 8:
        return "SENIOR"
    return "LEAD"


def _infer_titles(text: str) -> list:
    """Ordered, de-duplicated job titles inferred from resume/position text."""
    low = (text or "").lower()
    out, seen = [], set()
    for needle, role in _ROLE_HINTS:
        if needle in low and role not in seen:
            seen.add(role)
            out.append(role)
    if not out:
        for needle, role in _LANG_HINTS:
            if needle in low and role not in seen:
                seen.add(role)
                out.append(role)
    return out


def _infer_domains(text: str) -> list:
    """Industries the candidate has worked in, detected from resume text."""
    low = (text or "").lower()
    return [d for d, kws in _DOMAIN_HINTS.items() if any(k in low for k in kws)]


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s\-()]{7,}\d)(?!\d)")
# Strong company suffixes only (generic words like "Software"/"Solutions" appear
# in job titles & section headers, so they're excluded to avoid false matches).
# Applied PER LINE so a match never spans line breaks.
_COMPANY_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.'\-]+(?:[ ][A-Z][A-Za-z0-9&.'\-]+){0,3})[ ]+"
    r"(?:Inc|LLC|Ltd|Pvt\.?(?:[ ]Ltd)?|Limited|Technologies|Labs|Corp|"
    r"Consulting|GmbH|Systems)\b")


def _label_alias_map():
    """cleaned skill label -> all aliases (so we can count/locate a skill in text
    even though _ordered_labels returns the cleaned display name)."""
    m = {}
    for label, aliases in RT.SKILL_LEXICON.items():
        m.setdefault(RT._clean_label(label), []).extend(aliases)
    return m


_LABEL_ALIASES = _label_alias_map()


def _extract_name(resume_text: str) -> str:
    """Best-effort: a resume's first non-empty line is almost always the name."""
    for ln in (resume_text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if "@" in s or "http" in s.lower() or any(c.isdigit() for c in s):
            return ""
        words = s.split()
        if 1 <= len(words) <= 4 and len(s) <= 40 and \
           all(w[:1].isupper() for w in words if w[:1].isalpha()):
            return s
        return ""
    return ""


def _split_resume_skills(resume_text: str):
    """Split resume skills into PRIMARY (core) vs SECONDARY (mentioned in passing).

    Biased HARD toward primary — wrongly demoting a real skill makes us reject good
    jobs, which is worse than keeping a weak one (the user can delete it in the
    editable profile). So a skill is secondary ONLY if it appears exactly once AND
    its sole mention is in the trailing 20% of the resume. Short resumes (where
    position is meaningless) keep everything primary."""
    tl = " " + (resume_text or "").lower() + " "
    n = max(1, len(tl))
    labels = _ordered_labels(resume_text)
    if n < 400:                                   # too short to judge position
        return labels, []
    primary, secondary = [], []
    for lab in labels:
        aliases = _LABEL_ALIASES.get(lab, [lab.lower()])
        al = [a.strip().lower() for a in aliases if a.strip()]
        positions = [tl.find(a) for a in al if tl.find(a) >= 0]
        count = sum(tl.count(a) for a in al)
        first = min(positions) if positions else n
        if count == 1 and first >= 0.80 * n:      # single, trailing mention only
            secondary.append(lab)
        else:
            primary.append(lab)
    return primary, secondary


def build_search_queries(profile: dict) -> list:
    """Targeted board queries built FROM the profile (not 'software engineer').

      1. current title + top 3 primary skills   -> "Backend Developer NestJS Node.js TypeScript"
      2. each alternative title + top 2 skills
      3. skills-only (niche roles)               -> "NestJS Node.js TypeScript Python"
      4. current title + user-added skills        -> "Backend Developer Kafka GraphQL"
    """
    prim = list(profile.get("primary_skills") or [])
    added = list(profile.get("user_added_skills") or [])
    titles = [t for t in (profile.get("target_titles")
                          or profile.get("job_titles") or []) if t]
    cur = (profile.get("current_title") or (titles[0] if titles else "")).strip()

    queries, seen = [], set()

    def add(q):
        q = " ".join((q or "").split()).strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)

    if cur:
        add(f"{cur} {' '.join(prim[:3])}")
    for t in titles[:2]:
        add(f"{t} {' '.join(prim[:2])}")
    if prim:
        add(" ".join(prim[:4]))
    if added:
        add(f"{cur} {' '.join(added[:3])}")
    if not queries:
        for t in DEFAULT_SEARCH_TERMS:
            add(t)
    return queries[:6]


def extract_profile_from_resume(resume_text: str = "", skills_text: str = "",
                                position: str = "", years: int = 0,
                                location: str = "", remote: bool = False,
                                preferred_companies: str = "",
                                min_salary: int = 0) -> dict:
    """Analyze the resume (+ typed inputs) into a structured PROFILE used for job
    matching. Runs BEFORE fetching — so we know WHAT to search for and can show
    (and let the user edit) the profile before any API call.

    Skill tiers:
      primary_skills    core resume skills (drive the search)
      secondary_skills  resume skills only mentioned in passing (NOT matched on)
      user_added_skills skills typed in the skills box (ADDITIONAL)
      all_searchable_skills = primary + user_added  (what jobs are matched against)
    """
    resume_text = resume_text or ""
    primary, secondary = _split_resume_skills(resume_text)

    # User-typed skills: lexicon labels + raw tokens (respected even if off-lexicon).
    user_added = _ordered_labels(skills_text)
    for t in re.split(r"[,\n;|]+", skills_text or ""):
        t = t.strip()
        if t and t not in user_added and not any(t.lower() == u.lower() for u in user_added):
            user_added.append(t)

    searchable, seen = [], set()
    for s in primary + user_added:                  # NOT secondary
        if s.lower() not in seen:
            seen.add(s.lower())
            searchable.append(s)

    yrs = int(years) if years else _infer_years(resume_text)
    titles = _infer_titles(position + "\n" + resume_text)
    current_title = (position.split(",")[0].strip() if position.strip()
                     else (titles[0] if titles else ""))

    education = ""
    for ln in resume_text.splitlines():
        if _DEGREE_RE.search(ln):
            education = ln.strip()[:160]
            break

    certs = [s.strip() for ln in resume_text.splitlines()
             for s in [ln.strip()] if s and _CERT_RE.search(s) and len(s) <= 120]

    companies, cseen = [], set()
    for ln in resume_text.splitlines():               # per-line: never span breaks
        m = _COMPANY_RE.search(ln)
        if not m:
            continue
        c = m.group(0).strip()                        # full "Name Suffix"
        if c.lower() not in cseen and len(c) > 3:
            cseen.add(c.lower())
            companies.append(c)

    email_m = _EMAIL_RE.search(resume_text)
    phone_m = _PHONE_RE.search(resume_text)
    pref_co = [c.strip() for c in re.split(r"[,\n;]+", preferred_companies or "") if c.strip()]

    profile = {
        "name": _extract_name(resume_text),
        "email": email_m.group(0) if email_m else "",
        "phone": phone_m.group(1).strip() if phone_m else "",
        "current_title": current_title,
        "target_titles": titles,
        "job_titles": titles,                       # alias (search/scoring helpers)
        "experience_years": yrs,
        "experience_level": _experience_level(yrs),
        "max_experience_to_search": yrs + 1,
        "primary_skills": primary,
        "secondary_skills": secondary,
        "user_added_skills": user_added,
        "all_searchable_skills": searchable,
        "keywords": searchable,
        "education": education,
        "certifications": certs[:6],
        "domains": _infer_domains(resume_text),
        "companies_worked_at": companies[:6],
        "preferred_companies": pref_co,
        "location": (location or "").strip() or LOCATION,
        "location_preference": (location or "").strip() or LOCATION,
        "remote_preference": "remote" if remote else "any",
        "min_salary": int(min_salary or 0),
        "search_queries": [],
    }
    profile["search_queries"] = build_search_queries(profile)
    return profile


def _normalize_profile(edited: dict) -> dict:
    """Take a (possibly user-edited / partial) profile and re-derive the dependent
    fields so the invariants hold no matter what the UI sent."""
    p = dict(edited or {})

    def _clean(lst):
        out, seen = [], set()
        for s in (lst or []):
            s = str(s).strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
        return out

    p["primary_skills"] = _clean(p.get("primary_skills"))
    p["secondary_skills"] = _clean(p.get("secondary_skills"))
    p["user_added_skills"] = _clean(p.get("user_added_skills"))
    p["all_searchable_skills"] = _clean(p["primary_skills"] + p["user_added_skills"])
    p["keywords"] = p["all_searchable_skills"]
    try:
        yrs = int(p.get("experience_years") or 0)
    except (TypeError, ValueError):
        yrs = 0
    p["experience_years"] = yrs
    p["experience_level"] = _experience_level(yrs)
    p["max_experience_to_search"] = yrs + 1
    tt = _clean(p.get("target_titles") or p.get("job_titles"))
    p["target_titles"] = tt
    p["job_titles"] = tt
    if not (p.get("current_title") or "").strip():
        p["current_title"] = tt[0] if tt else ""
    p.setdefault("domains", [])
    p.setdefault("companies_worked_at", [])
    p.setdefault("preferred_companies", [])
    loc = (p.get("location") or p.get("location_preference") or LOCATION)
    p["location"] = loc
    p["location_preference"] = loc
    p.setdefault("remote_preference", "any")
    p.setdefault("name", "")
    p.setdefault("email", "")
    p.setdefault("phone", "")
    p.setdefault("education", "")
    p.setdefault("certifications", [])
    try:
        p["min_salary"] = int(p.get("min_salary") or 0)
    except (TypeError, ValueError):
        p["min_salary"] = 0
    p["search_queries"] = build_search_queries(p)
    return p


def build_saved_profile() -> dict:
    """The app owner's matching PROFILE, derived from the committed resume_profile.py.

    The daily GitHub-Actions cron uses this to GATE & RANK the feed to YOUR resume
    (skills, experience, target titles) — so data/jobs.json ships already matched to
    you and the hosted page (no upload) shows jobs that fit your profile.
    The live 'Fetch jobs' button is unaffected: it still builds its profile from the
    resume you upload. Falls back to a minimal profile if resume_profile is missing.
    """
    try:
        import resume_profile as RP
    except Exception:
        return extract_profile_from_resume()

    # --- Skills: clean every entry from every category -----------------------
    skills, seen = [], set()
    for items in getattr(RP, "SKILLS", {}).values():
        for s in items:
            c = re.sub(r"\s*\(.*?\)\s*", " ", s or "").strip()
            if c and c.lower() not in seen:
                seen.add(c.lower())
                skills.append(c)

    exp = getattr(RP, "EXPERIENCE", []) or []

    # --- Titles: all distinct titles from every experience entry -------------
    all_titles = list(dict.fromkeys(j.get("title", "") for j in exp if j.get("title")))
    position = ", ".join(all_titles)  # e.g. "Software Developer, Full Stack Engineer, ..."

    # --- Resume text: include dates + title headers so inference is richer ---
    summary = getattr(RP, "SUMMARY_TEMPLATE", "").replace(
        "{stack}", ", ".join(getattr(RP, "DEFAULT_STACK", [])))

    # --- Experience years ----------------------------------------------------
    # Prefer the years explicitly STATED in the resume summary (your source of
    # truth, e.g. "2 years") — stable, and you control it by editing the resume.
    # Only if none is stated, fall back to computing from the earliest role's
    # start date, FLOORED (int) so a partly-elapsed year never rounds you up.
    import datetime as _dt
    _MON = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
            "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    experience_years = _infer_years(summary)          # "N years" in the summary
    if not experience_years:
        earliest = None
        for j in exp:
            m = re.match(r"([A-Za-z]+)\s+(\d{4})", j.get("dates", ""))
            if m:
                mon = _MON.get(m.group(1).lower()[:3])
                if mon:
                    d = _dt.date(int(m.group(2)), mon, 1)
                    if earliest is None or d < earliest:
                        earliest = d
        today = _dt.date.today()
        experience_years = max(1, int((today - earliest).days / 365)) if earliest else 2
    exp_lines = []
    for j in exp:
        exp_lines.append(f"{j.get('dates','')} — {j.get('title','')} at {j.get('company','')}")
        exp_lines.extend(j.get("bullets", []))
    resume_text = "\n".join([getattr(RP, "NAME", ""), summary] + exp_lines)

    return extract_profile_from_resume(
        resume_text=resume_text,
        skills_text=", ".join(skills),
        position=position,
        years=experience_years,   # explicit: bypasses fragile text inference
    )


def _api_search_terms(profile: dict, position: str = "") -> list:
    """Short, single-concept queries for the free APIs (Remotive/Jobicy/etc.),
    which return nothing for long multi-word board queries. Titles + top skills,
    each on its own."""
    out = []
    candidates = []
    if position and position.strip():
        candidates += [t.strip() for t in re.split(r"[,\n;]+", position) if t.strip()]
    candidates += list(profile.get("job_titles") or [])[:2]
    candidates += list(profile.get("primary_skills") or [])[:4]
    for t in candidates:
        t = (t or "").strip()
        if t and t.lower() not in {o.lower() for o in out}:
            out.append(t)
    return out[:6] or list(DEFAULT_SEARCH_TERMS)


def _score_and_rank(rows, limit, target_text=None, cand_years=0):
    """Rank jobs. Base = skill/ATS match (vs the user's resume/JD/skills, or
    generic tech relevance). Then nudge by PREFERENCES — remote, big employers,
    500+ size, salary >= 7 LPA — and penalise roles that need many more years
    than the candidate. All soft signals; nothing is hard-filtered out."""
    targets = _labels_in(target_text or "")
    scored = []
    for r in rows:
        title = str(r.get("title") or "")
        desc = str(r.get("description") or "")
        company = str(r.get("company") or "")
        job_labels = _labels_in(f"{title} {desc}")
        if targets:
            overlap = targets & job_labels
            # Match level: how many of YOUR skills this job hits. Cap the
            # denominator so a job matching ~8 of your skills already reads as a
            # strong 100% — otherwise resumes with many skills make every % look
            # low. More overlap -> higher % -> sorts to the top.
            denom = max(1, min(len(targets), 8))
            score = round(100 * min(len(overlap), denom) / denom)
            matched = sorted(overlap)
        else:
            matched = sorted(job_labels)
            score = min(100, len(job_labels) * 12)
        base = score

        # --- experience fit (a PRIMARY signal) ---
        # Strongly prefer roles that match the candidate's years; strongly push
        # down roles that need many more years, and senior-titled roles.
        req_years = _required_years(f"{title} {desc}")
        exp_fit = True
        if cand_years and req_years:
            if req_years <= cand_years + 1:
                score += 10                       # fits your experience
            else:
                score -= min(45, (req_years - cand_years) * 8)
                exp_fit = False
        if _SENIOR_RE.search(title):
            score -= 20
            exp_fit = False

        # --- preferences (soft boosts) ---
        is_remote = bool(r.get("is_remote"))
        employees = _employees_min(r.get("company_num_employees"))
        big = _is_big_company(company)
        lpa = _salary_lpa(r)
        if is_remote:
            score += 8
        if employees >= 500:
            score += 12
        elif employees >= 150:
            score += 6
        if big:
            score += 10
        score += _salary_boost(lpa)              # pay above your current salary
        score += _recency_boost(r.get("date_posted"))   # freshest first

        score = max(0, min(100, score))

        scored.append({
            "score": score,
            "base": max(0, min(100, base)),
            "matched": matched,
            "title": title,
            "company": company,
            "location": str(r.get("location") or ""),
            "site": str(r.get("site") or ""),
            "date_posted": str(r.get("date_posted") or ""),
            "is_remote": is_remote,
            "employees": employees,
            "big": big,
            "exp_fit": exp_fit,
            "salary_lpa": round(lpa, 1) if lpa else 0,
            "job_url": str(r.get("job_url") or ""),
            "description": desc,
        })
    # Relevance gate. When guided by your resume/skills/JD, only keep jobs that
    # actually match your profile — at least 2 of your skills, or one very strong
    # match. Jobs whose skills/keywords don't match are dropped, not shown. If
    # that's too strict and leaves too few, relax to >=1 match so the page isn't
    # empty. Without any guidance, just drop near-zero noise.
    def _relevant(s, min_match):
        return s["job_url"] and (len(s["matched"]) >= min_match or s["base"] >= 60)

    if targets:
        scored2 = [s for s in scored if _relevant(s, 2)]
        if len(scored2) < 5:
            scored2 = [s for s in scored if _relevant(s, 1)]
        scored = scored2
    else:
        scored = [s for s in scored if s["job_url"] and s["score"] >= 10]
    seen, unique = set(), []
    for s in scored:
        if s["job_url"] in seen:
            continue
        seen.add(s["job_url"])
        unique.append(s)
    # Highest match first; for equal scores, the fresher posting wins.
    unique.sort(key=lambda s: (s["score"], -_days_old(s.get("date_posted"))),
                reverse=True)
    return unique[:limit]


def _job_in_domains(text: str, domains) -> bool:
    low = (text or "").lower()
    return any(any(k in low for k in _DOMAIN_HINTS.get(d, [])) for d in (domains or []))


def _title_relevance(job_title: str, profile_titles) -> float:
    """0..1 — how related a job title is to the candidate's titles. 1.0 = same
    specialty (e.g. 'Backend Engineer' vs 'Backend Developer'); 0.3 = same family
    (dev/engineer) but different specialty; 0.0 = unrelated (e.g. 'Sales Manager')."""
    jt = set(re.findall(r"[a-z+#.]+", (job_title or "").lower()))
    if not profile_titles:
        return 0.5                                   # no titles to compare -> neutral
    family = bool(jt & _TITLE_FAMILY)
    best = 0.0
    for role in profile_titles:
        rt = set(re.findall(r"[a-z+#.]+", role.lower())) - _TITLE_STOP
        if not rt:
            best = max(best, 0.5 if family else 0.0)
            continue
        inter = len(rt & jt) / len(rt)
        if inter == 0 and family:
            inter = 0.3                              # same family, different specialty
        best = max(best, inter)
    return min(1.0, best)


def calculate_match_score(r: dict, profile: dict, min_ratio: float) -> dict:
    """Score ONE job against the PROFILE (0-100) and decide whether to keep it.

    Returns {"reject": True, "reason": str, ...summary} when the job fails a hard
    filter (too few matching skills / too senior / unrelated title), else
    {"reject": False, "job": {...full row with match reasoning...}}.

    Breakdown (per the spec): skills 50, experience 20, title 15, domain 10,
    location 5; small preference nudges (remote / big company / size / salary) on
    top, then clamped to 0-100.
    """
    title = str(r.get("title") or "")
    desc = str(r.get("description") or "")
    company = str(r.get("company") or "")
    blob = f"{title} {desc}"
    # Match against searchable skills = primary + user-added (NOT secondary).
    pskills = set((profile.get("all_searchable_skills")
                   or profile.get("primary_skills") or [])) if profile else set()
    job_req = _labels_in(blob)
    matched = sorted(job_req & pskills) if pskills else sorted(job_req)
    missing = sorted(job_req - pskills) if pskills else []
    cy = int(profile.get("experience_years") or 0) if profile else 0

    def _summary(extra=None):
        s = {"title": title, "company": company, "site": str(r.get("site") or ""),
             "matched": matched, "missing": missing}
        if extra:
            s.update(extra)
        return s

    score = 0.0
    reasons = []

    # 1. SKILL MATCH (50) + hard gate ------------------------------------------
    skill_ratio = (len(job_req & pskills) / len(job_req)) if (job_req and pskills) else None
    if skill_ratio is not None:
        score += skill_ratio * 50
        if skill_ratio < min_ratio:
            return {"reject": True, "reason":
                    (f"skill match {round(skill_ratio * 100)}% < {round(min_ratio * 100)}% "
                     f"(have: {', '.join(matched) or 'none'}; lacks: {', '.join(missing[:5])})"),
                    **_summary({"skill_pct": round(skill_ratio * 100)})}
    elif not job_req:
        reasons.append("no recognisable skills in posting")     # thin/3rd-party listing
        score += 14 if not pskills else 6
    else:                                                        # no profile skills (sheet mode)
        score += min(50, len(job_req) * 8)

    # 2. EXPERIENCE (20) + hard gate -------------------------------------------
    req_floor = _min_required_years(blob)
    exp_fit = True
    if req_floor and cy:
        if req_floor <= cy + 1:
            score += 20
        elif req_floor <= cy + 2:
            score += 10
            reasons.append("slight experience stretch")
        else:
            return {"reject": True, "reason":
                    f"needs {req_floor}+ yrs, you have {cy} (cap {cy + 1})",
                    **_summary({"req_years": req_floor})}
    elif req_floor and not cy:
        score += 10                                             # unknown candidate years
    else:
        score += 12                                             # no requirement stated
    # For a junior/mid candidate (< 5 yrs) a clearly senior-titled role — Senior/
    # Sr/Staff/Principal/Lead/Manager/Director/Distinguished/SDE-3 — is a poor fit,
    # so REJECT it (don't just demote) and keep the feed on initial/mid positions.
    # A junior/entry/SDE-1 title in the same string exempts it.
    senior_title = bool(_SENIOR_RE.search(title))
    junior_title = bool(_JUNIOR_RE.search(title))
    if senior_title and not junior_title and cy and cy < 5:
        return {"reject": True, "reason":
                f"senior-level title '{title}' — you have {cy} yrs (targeting junior/mid)",
                **_summary({"req_years": req_floor})}
    if junior_title:                                     # initial/mid role — boost
        score += 8
        reasons.append("junior/mid-level fit")

    exp_label = (f"Your {cy}yr · needs {req_floor}+yr" if (cy and req_floor)
                 else (f"Your {cy}yr · no req stated" if cy
                       else (f"needs {req_floor}+yr" if req_floor else "no exp info")))

    # 3. TITLE RELEVANCE (15) + unrelated-role gate ----------------------------
    # The role you searched for is your top preference, so a strong title match
    # gets an extra boost on top of the base 15 — it sorts clearly above
    # loosely-related roles.
    trel = _title_relevance(title, profile.get("job_titles") if profile else [])
    score += trel * 15
    if trel >= 0.8:
        score += 10
        reasons.append("matches your target role")
    if profile and profile.get("job_titles") and trel == 0:
        return {"reject": True, "reason":
                f"title '{title}' unrelated to your roles "
                f"({', '.join(profile['job_titles'][:2])})",
                **_summary()}

    # 4. DOMAIN (10) -----------------------------------------------------------
    if profile and _job_in_domains(blob, profile.get("domains")):
        score += 10
        reasons.append("domain match")

    # 5. LOCATION / WORK-MODE --------------------------------------------------
    # You apply from India, so India-based roles (onsite / hybrid / WFH-in-India)
    # are the most actionable and get the biggest boost; global remote-anywhere is
    # still welcome but ranked a bit lower.
    is_remote = bool(r.get("is_remote"))
    loc = str(r.get("location") or "")
    in_india = _india_location(loc) or _india_location(blob)
    if in_india:
        score += 10
        reasons.append("India-based (apply-ready)")
        if _HYBRID_RE.search(blob):
            score += 3
            reasons.append("hybrid / on-site")
    elif is_remote:
        score += 3
        reasons.append("remote (global)")

    # --- soft preference nudges (kept from the product spec) ------------------
    employees = _employees_min(r.get("company_num_employees"))
    big = _is_big_company(company)
    lpa = _salary_lpa(r)
    if employees >= 500:
        score += 6
    elif employees >= 150:
        score += 3
    if big:
        score += 6
    score += _salary_boost(lpa)                       # pay above your current salary
    score += _recency_boost(r.get("date_posted"))     # freshest postings first
    if lpa and lpa > CURRENT_LPA:
        reasons.append(f"pays ~{round(lpa, 1)} LPA (> your {CURRENT_LPA})")

    score = max(0, min(100, round(score)))
    return {"reject": False, "job": {
        "score": score,
        "matched": matched,
        "missing": missing[:6],
        "skill_pct": round(skill_ratio * 100) if skill_ratio is not None else None,
        "title": title,
        "company": company,
        "location": loc,
        "site": str(r.get("site") or ""),
        "date_posted": str(r.get("date_posted") or ""),
        "is_remote": is_remote,
        "employees": employees,
        "big": big,
        "exp_fit": exp_fit,
        "exp_label": exp_label,
        "salary_lpa": round(lpa, 1) if lpa else 0,
        "why": reasons,
        "job_url": str(r.get("job_url") or ""),
        "description": desc,
    }}


def _rank_jobs(rows, limit, profile, min_ratio, min_score=0):
    """Score every row, drop the ones that fail the hard filters (collecting WHY
    for the debug panel) or fall below min_score, de-dup by URL, sort best-match
    first. Returns (kept_jobs, rejected_reasons)."""
    kept, rejected, seen = [], [], set()
    for r in rows:
        url = str(r.get("job_url") or "")
        if not url:
            continue
        res = calculate_match_score(r, profile, min_ratio)
        if res.get("reject"):
            rejected.append({"title": res.get("title", ""), "company": res.get("company", ""),
                             "site": res.get("site", ""), "reason": res.get("reason", "")})
            continue
        job = res["job"]
        if job["score"] < min_score:
            rejected.append({"title": job["title"], "company": job["company"],
                             "site": job["site"],
                             "reason": f"match {job['score']}% < {min_score}% minimum"})
            continue
        if url in seen:
            continue
        seen.add(url)
        kept.append(job)
    # Best match first; for ties, the fresher posting wins.
    kept.sort(key=lambda s: (s["score"], -_days_old(s.get("date_posted"))),
              reverse=True)
    return kept[:limit], rejected


def fetch_live(hours_old: int, limit: int, remote_only: bool = False,
               profile=None, search_terms=None, api_terms=None, career=False,
               api_only: bool = False):
    """Fetch and rank jobs against the PROFILE.

    api_only=True  → skip jobspy board scraping (LinkedIn/Indeed/Google etc.) and
                     use only the free REST APIs (Remotive, RemoteOK, Jobicy,
                     Arbeitnow, Greenhouse/Lever/Ashby ATS). This is the Vercel
                     path: those boards block datacenter IPs, but the free APIs
                     work everywhere and return results in seconds.
    api_only=False → run the full jobspy scrape first, then add the extra APIs on
                     top (local/server path).

    search_terms drive jobspy/Google queries; api_terms are short single-concept
    queries for the free APIs. Returns (jobs, debug).
    """
    terms = list(search_terms) if search_terms else list(DEFAULT_SEARCH_TERMS)
    api_q = list(api_terms) if api_terms else terms
    location = "Remote" if remote_only else LOCATION
    rows = []

    if not api_only:
        from jobspy import scrape_jobs  # heavy import, only when actually fetching
        import pandas as pd
        _quiet_jobspy()

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

        if frames:
            import pandas as pd
            combined = pd.concat(frames, ignore_index=True).fillna("")
            rows = combined.to_dict("records")

    # Add real remote roles from free APIs (Remotive + RemoteOK) — startups and
    # established companies that the jobspy boards miss. When `career` is on, also
    # scrape direct company career pages (Greenhouse/Lever/Ashby ATS) + HN/WWR.
    # On Vercel (api_only) the boards are skipped, so the APIs are the ONLY source —
    # pull more per term there so enough candidates survive ranking to fill `limit`.
    api_per_term = 60 if api_only else 30
    try:
        rows += ES.fetch_extra(
            api_q, per_term=api_per_term, max_age_hours=hours_old,
            include_career=career,
            experience_level=(profile or {}).get("experience_level"),
            location=location,
        )
    except Exception as e:
        print(f"  ! extra sources failed: {e}", flush=True)

    # Fallback: if the boards/APIs returned little, use Tavily AI web-search
    # (only runs when TAVILY_API_KEY is set — saves free credits).
    if len(rows) < limit:
        try:
            tav = ES.fetch_tavily(api_q, max_results=6, max_age_hours=hours_old)
            if tav:
                rows += tav
                print(f"    -> {len(tav)} rows (Tavily fallback)", flush=True)
        except Exception as e:
            print(f"  ! tavily fallback failed: {e}", flush=True)

    total = len(rows)
    if not rows:
        return [], {"fetched": 0, "kept": 0, "rejected_count": 0, "rejected": [],
                    "relaxed": False, "min_ratio": MIN_SKILL_RATIO}

    # Strict pass: keep only jobs that fit the profile (hard skill/exp/title
    # filters) AND score >= 50%. If that leaves too few, relax the skill threshold
    # and the min score once so the page isn't empty — and flag that we relaxed.
    ranked, rejected = _rank_jobs(rows, limit * 4, profile, MIN_SKILL_RATIO, min_score=50)
    relaxed = False
    used_ratio = MIN_SKILL_RATIO
    if len(ranked) < min(MIN_KEEP_BEFORE_RELAX, limit):
        ranked, rejected = _rank_jobs(rows, limit * 4, profile, RELAX_SKILL_RATIO, min_score=0)
        relaxed = True
        used_ratio = RELAX_SKILL_RATIO

    jobs = _diversify_by_site(ranked, limit)
    debug = {
        "fetched": total,
        "kept": len(jobs),
        "rejected_count": len(rejected),
        "rejected": rejected[:40],          # cap what we ship to the UI
        "relaxed": relaxed,
        "min_ratio": used_ratio,
    }
    return jobs, debug


def _diversify_by_site(ranked, limit):
    """Keep strict descending-% order, but round-robin sources inside each equal-%
    tier so the list reads 100%->0% without one board clustering."""
    from collections import OrderedDict
    out, i, n = [], 0, len(ranked)
    while i < n and len(out) < limit:
        score = ranked[i]["score"]
        tier = []
        while i < n and ranked[i]["score"] == score:
            tier.append(ranked[i])
            i += 1
        by_site = OrderedDict()
        for j in tier:
            by_site.setdefault(j.get("site") or "?", []).append(j)
        while any(by_site.values()) and len(out) < limit:
            for lst in by_site.values():
                if lst:
                    out.append(lst.pop(0))
                    if len(out) >= limit:
                        break
    return out[:limit]


def _is_feed_mode() -> bool:
    """Vercel/hosted mode: jobs come from the committed feed, not a live scrape."""
    return JOBS_SOURCE in ("feed", "sheet")


def _fetch_feed_payload():
    """The feed JSON from the remote 'feed' branch (FEED_URL), cached for _FEED_TTL
    seconds so the hosted app refreshes without a redeploy. Returns None on failure
    (the caller then falls back to the bundled data/jobs.json)."""
    if not FEED_URL:
        return None
    now = time.time()
    if _FEED_CACHE["data"] is not None and (now - _FEED_CACHE["at"]) < _FEED_TTL:
        return _FEED_CACHE["data"]
    try:
        import urllib.request
        with urllib.request.urlopen(FEED_URL, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        _FEED_CACHE["data"] = payload
        _FEED_CACHE["at"] = now
        return payload
    except Exception as e:
        print(f"  ! live feed fetch failed ({e}); using bundled feed", flush=True)
        return _FEED_CACHE["data"]            # last good cache if any, else None


def _read_feed():
    """Return (raw_rows, fetched_at). Prefer the live 'feed' branch (FEED_URL); fall
    back to the bundled data/jobs.json when the fetch fails or no URL is configured."""
    payload = _fetch_feed_payload()
    if payload is None and os.path.exists(JOBS_FEED):
        with open(JOBS_FEED, "r", encoding="utf-8") as f:
            payload = json.load(f)
    if payload is None:
        return [], None
    if isinstance(payload, dict):
        return payload.get("jobs", []), payload.get("fetched_at")
    return payload, None                      # tolerate a bare list of job rows


def fetch_from_feed(limit: int):
    """Read + generically rank jobs from the committed daily feed (data/jobs.json),
    refreshed by the GitHub Actions cron. No external service or credentials."""
    rows, fetched_at = _read_feed()
    return _score_and_rank(rows, limit), fetched_at


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
    """Return the most recently fetched jobs (cached locally, or from the daily feed on Vercel)."""
    if _is_feed_mode():
        jobs, fetched_at = fetch_from_feed(limit)
        return {"fetched_at": fetched_at or "daily feed", "jobs": jobs, "source": "feed"}
    cache = load_cache()
    cache["source"] = "live-cache"
    return cache


@app.post("/api/fetch")
async def api_fetch(
    hours_old: int = DEFAULT_HOURS_OLD,
    limit: int = DEFAULT_LIMIT,
    remote: bool = False,
    position: str = Form(""),
    years: str = Form(""),
    file: UploadFile = File(None),
    jd: str = Form(""),
    skills: str = Form(""),
    career: bool = Form(True),
    profile_json: str = Form(""),
):
    """Build the matching PROFILE from the resume + inputs (or use the user-edited
    profile sent as profile_json), search the boards FROM that profile, then keep
    only jobs that fit it. Cache and return the top matches plus the profile and a
    debug breakdown of what was filtered out.
    """
    # NOTE: live scraping is allowed everywhere now (including hosted/feed mode), so
    # the "Fetch live jobs" button works on Vercel too. Boards like LinkedIn/Indeed
    # may block serverless IPs and functions can time out, so results can be few or
    # slow on Vercel — "Load latest jobs" (/api/feed/match) stays the reliable path.

    # If the user previewed & edited their profile, trust those edits; otherwise
    # build the profile fresh from the resume + inputs.
    profile = None
    if profile_json and profile_json.strip():
        try:
            profile = _normalize_profile(json.loads(profile_json))
        except Exception as e:
            print(f"  ! bad profile_json, re-deriving: {e}", flush=True)
            profile = None

    if profile is None:
        resume_text = ""
        if file is not None and file.filename:
            try:
                data = await file.read()
                if data:
                    resume_text = RT.extract_text(file.filename, data)
            except Exception as e:
                print(f"  ! could not read uploaded resume: {e}", flush=True)
        try:
            cand_years = int(re.search(r"\d+", years).group()) if years.strip() else 0
        except (AttributeError, ValueError):
            cand_years = 0
        # Fold the pasted JD's skills into the profile too (sharpens search+match).
        skills_blob = skills
        if jd and jd.strip():
            skills_blob = (skills + "\n" + jd) if skills.strip() else jd
        profile = extract_profile_from_resume(
            resume_text=resume_text, skills_text=skills_blob,
            position=position, years=cand_years, remote=remote,
            location="Remote" if remote else LOCATION,
        )

    search_terms = profile.get("search_queries") or build_search_queries(profile)
    api_terms = _api_search_terms(profile, position)

    # fetch_live is blocking (scraping) -> run in threadpool.
    # On Vercel (feed/hosted mode) use api_only=True: skip jobspy which is blocked
    # by those boards on datacenter IPs; only the free REST APIs (Remotive etc.) work.
    jobs, debug = await run_in_threadpool(
        fetch_live, hours_old, limit, remote, profile, search_terms, api_terms, career,
        _is_feed_mode())
    payload = save_cache(jobs)
    payload["source"] = "live"
    payload["remote_only"] = remote
    payload["guided"] = bool(profile["primary_skills"] or profile["job_titles"])
    payload["search_terms"] = search_terms
    payload["cand_years"] = profile["experience_years"]
    payload["profile"] = profile
    payload["debug"] = debug
    return payload


@app.post("/api/feed/match")
async def api_feed_match(
    limit: int = DEFAULT_LIMIT,
    remote: bool = False,
    position: str = Form(""),
    years: str = Form(""),
    file: UploadFile = File(None),
    jd: str = Form(""),
    skills: str = Form(""),
    profile_json: str = Form(""),
):
    """Hosted (feed) mode can't scrape, but it CAN match: build a PROFILE from the
    uploaded resume + inputs and rank the EXISTING daily feed against it (same
    personalised scorer the live fetch uses). Returns the jobs that fit your
    resume, best-first — no scraping, so it works on Vercel."""
    rows, fetched_at = _read_feed()
    if not rows:
        return {"jobs": [], "fetched_at": fetched_at or "daily feed",
                "source": "feed-match", "guided": False,
                "profile": None, "debug": {"fetched": 0, "kept": 0}}

    profile = None
    if profile_json and profile_json.strip():
        try:
            profile = _normalize_profile(json.loads(profile_json))
        except Exception as e:
            print(f"  ! bad profile_json, re-deriving: {e}", flush=True)
            profile = None
    if profile is None:
        resume_text = ""
        if file is not None and file.filename:
            try:
                data = await file.read()
                if data:
                    resume_text = RT.extract_text(file.filename, data)
            except Exception as e:
                print(f"  ! could not read uploaded resume: {e}", flush=True)
        try:
            cand_years = int(re.search(r"\d+", years).group()) if years.strip() else 0
        except (AttributeError, ValueError):
            cand_years = 0
        skills_blob = (skills + "\n" + jd) if (skills.strip() and jd.strip()) else (skills or jd)
        profile = extract_profile_from_resume(
            resume_text=resume_text, skills_text=skills_blob,
            position=position, years=cand_years, remote=remote,
            location="Remote" if remote else LOCATION,
        )

    if remote:                                   # honour the remote-only toggle
        rows = [r for r in rows if r.get("is_remote") in (True, "True", "true", 1)]

    # Rank the feed against the profile. Relax the skill gate once if too strict.
    kept, rejected = _rank_jobs(rows, limit, profile, MIN_SKILL_RATIO, min_score=0)
    relaxed = False
    if len(kept) < 5:
        kept, rejected = _rank_jobs(rows, limit, profile, max(0.3, MIN_SKILL_RATIO - 0.3))
        relaxed = True

    return {
        "jobs": kept,
        "fetched_at": fetched_at or "daily feed",
        "source": "feed-match",
        "guided": bool(profile["primary_skills"] or profile["job_titles"]),
        "search_terms": profile.get("search_queries") or build_search_queries(profile),
        "cand_years": profile["experience_years"],
        "profile": profile,
        "debug": {"fetched": len(rows), "kept": len(kept),
                  "rejected_count": len(rejected), "rejected": rejected[:40],
                  "relaxed": relaxed, "min_ratio": MIN_SKILL_RATIO},
    }


@app.post("/api/profile")
async def api_profile(
    position: str = Form(""),
    years: str = Form(""),
    file: UploadFile = File(None),
    jd: str = Form(""),
    skills: str = Form(""),
    remote: bool = Form(False),
):
    """Parse the resume + inputs into the matching PROFILE WITHOUT fetching — so
    the user can verify (and adjust the fields) before running a search."""
    resume_text = ""
    if file is not None and file.filename:
        try:
            data = await file.read()
            if data:
                resume_text = RT.extract_text(file.filename, data)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:
            raise HTTPException(400, f"Could not read resume: {e}")
    try:
        cand_years = int(re.search(r"\d+", years).group()) if years.strip() else 0
    except (AttributeError, ValueError):
        cand_years = 0
    skills_blob = (skills + "\n" + jd) if (skills.strip() and jd.strip()) else (skills or jd)
    profile = extract_profile_from_resume(
        resume_text=resume_text, skills_text=skills_blob,
        position=position, years=cand_years, remote=remote,
        location="Remote" if remote else LOCATION,
    )
    return {"profile": profile,
            "search_terms": profile["search_queries"],
            "api_terms": _api_search_terms(profile, position)}


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

    # ATS: add only the JD keywords NOT already in the profile (the ones you have
    # already appear in Technical Skills) to a short "Core Competencies" line, so
    # total keyword coverage is ~100% without duplicating or overflowing the page.
    ats_keywords = None
    if description:
        profile_blob = " ".join(
            [P.SUMMARY_TEMPLATE] +
            [s for items in P.SKILLS.values() for s in items] +
            [b for j in P.EXPERIENCE for b in j["bullets"]]
        )
        have = _labels_in(profile_blob)
        ats_keywords = sorted(_labels_in(description) - have) or None

    out_files = []
    if fmt in ("pdf", "both"):
        buf = io.BytesIO()
        RB.render_pdf(buf, summary, skills, matched, title, company, ats_keywords)
        data = buf.getvalue()
        name = base + ".pdf"
        _save_resume_copy(name, data)
        out_files.append({"name": name, "mime": "application/pdf",
                          "b64": base64.b64encode(data).decode()})
    if fmt in ("docx", "both"):
        buf = io.BytesIO()
        RB.render_docx(buf, summary, skills, matched, title, company, ats_keywords)
        data = buf.getvalue()
        name = base + ".docx"
        _save_resume_copy(name, data)
        out_files.append({"name": name, "mime": _DOCX_MIME,
                          "b64": base64.b64encode(data).decode()})

    return {"files": out_files, "emphasized": sorted(matched),
            "ats_keywords": ats_keywords or []}


def _build_cover_note(title: str, company: str, matched) -> str:
    """A short, honest cover note for one job, from the saved profile + the skills
    that matched this job's description. Template-based (no paid LLM) so it's free
    and instant; you edit it before sending."""
    import resume_profile as P
    try:
        yrs = build_saved_profile().get("experience_years") or 2
    except Exception:
        yrs = 2
    top = ", ".join(list(matched)[:5]) if matched else "backend and API development"
    role = (title or "this role").strip()
    comp = (company or "your team").strip()
    name = getattr(P, "NAME", ""); email = getattr(P, "EMAIL", ""); phone = getattr(P, "PHONE", "")
    return (
        f"Dear Hiring Team at {comp},\n\n"
        f"I'm excited to apply for the {role} position. I'm a backend-focused software "
        f"developer with {yrs} years of experience building scalable microservices and "
        f"REST APIs, with hands-on strengths in {top}. In my current role I've shipped "
        f"production services with an emphasis on clean architecture, performance, and "
        f"reliability.\n\n"
        f"I'd welcome the chance to bring this to {comp}; my tailored resume is attached. "
        f"Thank you for your time and consideration.\n\n"
        f"Best regards,\n{name}\n{email} | {phone}"
    )


@app.post("/api/apply/kit")
def api_apply_kit(payload: dict):
    """Semi-auto APPLY ASSISTANT for one job: builds a resume tailored to this job's
    description (reusing /api/resume/build), drafts a matching cover note, and echoes
    the apply link. You review and submit yourself — nothing is sent automatically."""
    title = (payload.get("title") or "").strip()
    company = (payload.get("company") or "").strip()
    description = (payload.get("description") or "").strip()
    job_url = (payload.get("job_url") or "").strip()
    fmt = (payload.get("format") or "pdf").lower()
    if fmt not in ("pdf", "docx", "both"):
        fmt = "pdf"
    built = api_resume_build({"title": title or "Role", "company": company or "Company",
                              "description": description, "format": fmt})
    matched = built.get("emphasized") or []
    return {
        "files": built.get("files", []),
        "emphasized": matched,
        "ats_keywords": built.get("ats_keywords", []),
        "cover_note": _build_cover_note(title, company, matched),
        "job_url": job_url, "title": title, "company": company,
    }


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

    base = _slugify(os.path.splitext(os.path.basename(file.filename or "resume"))[0])
    base = base or "resume"

    # Build TWO versions from the same upload (tailor_upload is blocking — parses
    # files and launches Word for PDF — so run each off the event loop):
    #   A = Standard  (ats=False): only skills you genuinely have + skills you typed
    #   B = ATS-boost (ats=True):  A + the JD's remaining important keywords appended
    #                              for maximum ATS keyword coverage / higher ATS score
    variants = [
        ("A_standard", False),
        ("B_ats", True),
    ]

    out_files = []
    analysis = None
    layout_preserved = None
    pdf_note = None
    ats_added = 0
    try:
        for suffix, ats in variants:
            result = await run_in_threadpool(
                RT.tailor_upload, file.filename or "resume", data,
                jd or "", skills or "", want_pdf, want_docx, ats,
            )
            # The analysis (present/typed/suggestions) is identical for both; keep one.
            analysis = result["analysis"]
            layout_preserved = result["layout_preserved"]
            if result.get("pdf_note"):
                pdf_note = result["pdf_note"]
            if ats:
                ats_added = result.get("ats_added", 0)

            vbase = f"{base}_tailored_{suffix}"
            if result.get("docx"):
                name = vbase + ".docx"
                _save_resume_copy(name, result["docx"])
                out_files.append({
                    "name": name,
                    "version": suffix,
                    "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "b64": base64.b64encode(result["docx"]).decode(),
                })
            if result.get("pdf"):
                name = vbase + ".pdf"
                _save_resume_copy(name, result["pdf"])
                out_files.append({
                    "name": name,
                    "version": suffix,
                    "mime": "application/pdf",
                    "b64": base64.b64encode(result["pdf"]).decode(),
                })
    except ValueError as e:                      # bad/empty/unsupported upload
        raise HTTPException(400, str(e))
    except Exception as e:                        # unexpected
        raise HTTPException(500, f"Tailoring failed: {e}")

    return {
        "analysis": analysis,
        "layout_preserved": layout_preserved,
        "pdf_note": pdf_note,
        "ats_added": ats_added,
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
# Browsers auto-request /favicon.ico; without a route it logs a 404 every load.
# Serve a tiny inline SVG (briefcase glyph on the app's dark card colour).
_FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="12" fill="#16203a"/>'
    '<text x="32" y="44" font-size="38" text-anchor="middle">\U0001F4BC</text>'
    '</svg>'
).encode("utf-8")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi import Response
    return Response(content=_FAVICON_SVG, media_type="image/svg+xml")


# ---- PWA: installable "app" on mobile/desktop (manifest + icons + SW) -------
def _png(b64s):
    from fastapi import Response
    return Response(content=base64.b64decode(b64s), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/icon-192.png", include_in_schema=False)
def icon_192():
    import pwa_assets
    return _png(pwa_assets.ICON_192_B64)


@app.get("/icon-512.png", include_in_schema=False)
def icon_512():
    import pwa_assets
    return _png(pwa_assets.ICON_512_B64)


@app.get("/apple-touch-icon.png", include_in_schema=False)
def apple_icon():
    import pwa_assets
    return _png(pwa_assets.APPLE_ICON_B64)


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return JSONResponse({
        "name": "Job Finder & Resume Tailor",
        "short_name": "Job Finder",
        "description": "Fresh jobs matched to your resume, with one-click tailored apply.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#0b111c",
        "theme_color": "#0b111c",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png",
             "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "any maskable"},
        ],
    }, media_type="application/manifest+json")


# Network-first service worker: always try the live feed; fall back to the cached
# app shell when offline. Served at root scope so it controls the whole origin.
_SERVICE_WORKER = """
const CACHE = 'jobfinder-v1';
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;               // don't cache POST (fetch/match)
  e.respondWith(
    fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(req).then(m => m || caches.match('/')))
  );
});
"""


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    from fastapi import Response
    return Response(content=_SERVICE_WORKER, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})


@app.get("/", response_class=HTMLResponse)
def index():
    live = not _is_feed_mode()
    html = INDEX_HTML.replace("__LIVE__", "true" if live else "false")
    html = html.replace("__CURRENT_LPA__", str(CURRENT_LPA))
    return HTMLResponse(html)


# --------------------------------------------------------------------------- #
# COMPANY DISCOVERY — every business in a city/locality/sector/pincode.
# Free data only: OpenStreetMap (Overpass + Nominatim) + on-demand website enrich.
# --------------------------------------------------------------------------- #
@app.get("/api/companies")
async def api_companies(area: str, limit: int = 500):
    """Discover every named business inside `area` (city/locality/sector/pincode)
    from OpenStreetMap. Blocking network work -> threadpool."""
    import company_discovery as CD
    if not area or not area.strip():
        raise HTTPException(400, "Provide an area, e.g. 'Noida Sector 62'.")
    return await run_in_threadpool(CD.discover, area.strip(), limit)


@app.post("/api/company/enrich")
async def api_company_enrich(payload: dict):
    """On-demand: fetch a company's website and detect tech stack / emails /
    socials / careers page. Free, best-effort."""
    import company_discovery as CD
    url = (payload or {}).get("url", "")
    if not url:
        raise HTTPException(400, "Provide a website url.")
    return await run_in_threadpool(CD.enrich_website, url)


@app.get("/companies", response_class=HTMLResponse)
def companies_page():
    return HTMLResponse(COMPANIES_HTML)


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>Job Finder & Resume Tailor</title>
<link rel="icon" href="/favicon.ico" type="image/svg+xml"/>
<!-- PWA: installable app on mobile/desktop -->
<link rel="manifest" href="/manifest.webmanifest"/>
<meta name="theme-color" content="#0b111c"/>
<meta name="mobile-web-app-capable" content="yes"/>
<meta name="apple-mobile-web-app-capable" content="yes"/>
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"/>
<meta name="apple-mobile-web-app-title" content="Job Finder"/>
<link rel="apple-touch-icon" href="/apple-touch-icon.png"/>
<style>
  :root { --bg:#0f1623; --card:#16203140; --line:#27364d; --ink:#e7eef9; --mut:#8aa0bd;
          --accent:#3b82f6; --good:#16331a; --goodt:#9be7a4; --amb:#3a3417; --ambt:#f0d98a;
          --bad:#3a1f1f; --badt:#f0a0a0; }
  * { box-sizing:border-box; }
  body { margin:0; background:#0b111c; color:var(--ink); font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;
         overflow-x:hidden; -webkit-text-size-adjust:100%; }
  header { padding:18px 24px; border-bottom:1px solid var(--line); display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
  header h1 { font-size:18px; margin:0; }
  header .sub { color:var(--mut); font-size:12px; }
  main { padding:20px 24px; max-width:1200px; margin:0 auto; }
  .bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:16px; }
  button { background:var(--accent); color:#fff; border:0; padding:8px 14px; border-radius:8px; cursor:pointer; font-size:13px; }
  button.secondary { background:#1e293b; color:var(--ink); border:1px solid var(--line); }
  button:disabled { opacity:.5; cursor:default; }
  input:disabled, select:disabled, textarea:disabled { opacity:.55; cursor:not-allowed; }
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
  .tabs { display:flex; gap:8px; margin-bottom:22px; }
  .tab { background:#111c2e; color:var(--mut); border:1px solid var(--line); padding:10px 18px; border-radius:9px; font-size:14px; font-weight:600; }
  .tab.active { background:var(--accent); color:#fff; border-color:var(--accent); }
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
  .modal-bg { position:fixed; inset:0; background:#000a; display:flex; align-items:center;
              justify-content:center; z-index:60; padding:16px; }
  .modal { background:#0e1726; border:1px solid var(--line); border-radius:12px;
           max-width:640px; width:100%; max-height:90vh; overflow:auto; padding:18px 20px; }
  .table-wrap { overflow-x:auto; -webkit-overflow-scrolling:touch; }
  /* Respect phone notches / rounded corners (viewport-fit=cover) */
  header { padding-left:max(24px, env(safe-area-inset-left)); padding-right:max(24px, env(safe-area-inset-right)); }
  @media (max-width:680px){
    header { padding:12px 14px; gap:8px; }
    header h1 { font-size:16px; }
    header .sub { width:100%; }
    main { padding:14px 12px; }
    .bar { gap:7px; }
    button { padding:9px 12px; font-size:13px; min-height:40px; }   /* comfy tap target */
    .tabs { gap:6px; margin-bottom:16px; }
    .tab { flex:1; text-align:center; padding:10px 8px; font-size:13px; }
    .grid2 { grid-template-columns:1fr; }
    textarea, input, select { font-size:16px; }   /* >=16px stops iOS auto-zoom on focus */
    /* Keep the small inline controls compact despite the 16px bump */
    #years, #limit { width:64px; }
    .card { padding:12px 13px; }
    /* Convert jobs table to stacked cards */
    .table-wrap { overflow-x:unset; }
    #jobsTable thead { display:none; }
    #jobsTable, #jobsTable tbody { display:block; width:100%; }
    #jobsTable tr { display:block; background:#0e172680; border:1px solid var(--line);
                    border-radius:10px; margin-bottom:10px; padding:12px 14px; }
    #jobsTable td { display:block; border:none; padding:2px 0; font-size:13px; }
    /* Hide: row-number, Size, Site columns */
    #jobsTable td:nth-child(1),
    #jobsTable td:nth-child(5),
    #jobsTable td:nth-child(7) { display:none; }
    /* Match score inline before job title */
    #jobsTable td:nth-child(2) { display:inline-block; margin-right:8px; vertical-align:middle; }
    #jobsTable td:nth-child(3) { display:inline-block; vertical-align:middle; max-width:calc(100% - 70px); }
    /* Company + Location on one line */
    #jobsTable td:nth-child(4) { color:var(--mut); font-size:12px; }
    #jobsTable td:nth-child(6) { display:inline; color:var(--mut); font-size:12px; }
    #jobsTable td:nth-child(6)::before { content:" · "; }
    /* Posted date small */
    #jobsTable td:nth-child(8) { color:var(--mut); font-size:11px; }
    /* Apply + Tailor: full-width, easy to tap */
    #jobsTable td:nth-child(9), #jobsTable td:nth-child(10) { display:block; margin-top:8px; }
    #jobsTable td:nth-child(9) a, #jobsTable td:nth-child(9) button,
    #jobsTable td:nth-child(10) button { display:block; width:100%; text-align:center; }
    #jobsTable td:nth-child(10) br { display:none; }
    #jobsTable td:nth-child(10) button { margin-bottom:6px; }
    /* Apply-kit modal fills the small screen comfortably + clears the notch */
    .modal-bg { padding:10px; padding-bottom:max(10px, env(safe-area-inset-bottom)); }
    .modal { padding:16px 14px; max-height:92vh; }
  }
</style>
</head>
<body>
<header>
  <h1>Job Finder &amp; Resume Tailor</h1>
  <span class="pill" id="modePill">mode</span>
  <a href="/companies" style="color:#7db0ff;text-decoration:none;font-size:13px">🏢 Company Discovery →</a>
  <span class="sub" id="status"></span>
</header>
<main>

  <div class="tabs">
    <button id="tabFind" class="tab active">&#9312; Find jobs</button>
    <button id="tabCreate" class="tab">&#9313; Create resume</button>
  </div>

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
        <button id="fetchBtn">Fetch live jobs</button>
        <button id="matchBtn">Load latest jobs</button>
        <button class="secondary" id="previewBtn">Preview my profile</button>
        <label class="note">Your experience
          <input id="years" type="number" value="" min="0" max="30" placeholder="auto" style="width:60px"/> yrs
        </label>
        <label class="note">Posted within
          <select id="hours"><option value="24">24h</option><option value="48">48h</option><option value="72">72h</option><option value="168">7d</option></select>
        </label>
        <label class="note">Top <input id="limit" type="number" value="50" min="5" max="100" style="width:60px"/></label>
        <label class="switch note" title="Greenhouse/Lever/Ashby ATS APIs + Hacker News + We Work Remotely"><input type="checkbox" id="jfCareer" checked/> Search company career pages directly</label>
        <span class="note" id="count"></span>
      </div>
    </div>

    <!-- Matching profile preview (filled by "Preview my profile" / after fetch) -->
    <div class="card" id="profilePanel" style="display:none"></div>
    <p class="note" style="margin:-4px 0 12px">Boards: LinkedIn · Indeed · Google · Glassdoor · ZipRecruiter · Naukri · Bayt · Remotive · RemoteOK · Jobicy · Arbeitnow — all real, directly-posted listings. Ranked by skill/ATS match and your <b>target role</b>, then preference for <b>remote</b>, <b>big companies / 500+ employees</b>, roles that fit your experience, <b>pay above your current salary</b>, and the <b>freshest postings</b>. Remote jobs are always included. <i>Experience auto-detected from your resume if left blank.</i></p>
    <p class="note" id="feedHint" style="margin:-4px 0 12px;display:none">Hosted mode reads the daily job feed. Upload your resume (and/or type a role/skills) above and click <b>Load latest jobs</b> to rank the feed to your resume — or click it with nothing filled in to see the whole ranked feed.</p>

    <div class="table-wrap">
    <table id="jobsTable">
      <thead><tr>
        <th>#</th><th>Match</th><th>Job</th><th>Company</th><th>Size</th><th>Location</th>
        <th>Site</th><th>Posted</th><th>Apply</th><th>Tailor</th>
      </tr></thead>
      <tbody id="jobsBody"><tr><td colspan="10" class="empty">No jobs yet. Optionally upload your resume (and/or type a role) above, then click <b>Fetch live jobs</b> or <b>Load latest jobs</b> — results are ranked to your skills, best match first.</td></tr></tbody>
    </table>
    </div>
    <div id="loadMoreWrap" style="text-align:center;margin-top:12px;display:none">
      <button class="secondary" id="loadMoreBtn">Load more</button>
    </div>
    <div id="debugPanel" class="note" style="margin-top:10px"></div>
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
<div id="applyModal"></div>

<script>
const LIVE = __LIVE__;
const CURRENT_LPA = __CURRENT_LPA__;
const $ = s => document.querySelector(s);
let jobs = [];
const PAGE = 50;           // show 50 first, then "Load more" reveals 50 at a time
let shown = PAGE;

function toast(msg, ms=3500){ const t=$('#toast'); t.innerHTML='<div class="toast">'+msg+'</div>';
  clearTimeout(window._tt); window._tt=setTimeout(()=>t.innerHTML='',ms); }
function scoreClass(s){ return s>=65?'s-hi':s>=45?'s-md':'s-lo'; }
function esc(s){ return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
// While an action runs, lock every input/select/textarea/button in its card so
// fields can't be edited mid-process; unlock when done.
function setBusy(btn, busy){
  const scope = (btn && btn.closest && btn.closest('.card')) || document;
  scope.querySelectorAll('input, select, textarea, button').forEach(el=>{ el.disabled = busy; });
}

// Live elapsed-time counter. Calls onTick(label) every second with the real
// elapsed time as m:ss (e.g. "0:05", "0:32", "1:12"); returns a stop() function.
// Used instead of a hardcoded "~1 min" so the user sees the actual time taken.
function startTimer(onTick){
  const t0 = Date.now();
  const label = ()=>{ const s=Math.floor((Date.now()-t0)/1000);
                      return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); };
  onTick(label());
  const id = setInterval(()=>onTick(label()), 1000);
  return ()=>clearInterval(id);
}

function showMore(){ shown += PAGE; renderJobs(); }

function renderJobs(){
  const b=$('#jobsBody');
  const wrap=$('#loadMoreWrap');
  if(!jobs.length){ b.innerHTML='<tr><td colspan="10" class="empty">No matching jobs found. Try a different role/position, widen the posting age, or upload a resume to guide the search.</td></tr>'; if(wrap) wrap.style.display='none'; return; }
  const visible = jobs.slice(0, shown);
  $('#count').textContent = 'showing '+visible.length+' of '+jobs.length+' jobs'
                            +(window._fetchedAt?(' · '+window._fetchedAt):'');
  // "Load more" shows up whenever there are more jobs than currently displayed.
  if(wrap){
    const more = jobs.length - visible.length;
    wrap.style.display = more>0 ? '' : 'none';
    const btn=$('#loadMoreBtn'); if(btn) btn.textContent='Load more ('+more+' more)';
  }
  b.innerHTML = visible.map((j,i)=>{
    const matched=(j.matched||[]).slice(0,6).map(m=>'<span class="tag have" style="font-size:10px">'+esc(m.split(' (')[0])+'</span>').join('');
    const missing=(j.missing||[]).slice(0,4).map(m=>'<span class="tag miss" style="font-size:10px">'+esc(m.split(' (')[0])+'</span>').join('');
    const matchLine = matched ? ('<div class="chips">&#9989; '+matched+'</div>') : '';
    const missLine = missing ? ('<div class="chips" style="margin-top:2px">&#9888; could learn: '+missing+'</div>') : '';
    const size=j.employees>=150?(j.employees>=1000?(Math.floor(j.employees/1000)+'k+'):(j.employees+'+')):'';
    const exp=j.exp_label?('<span class="chip" title="experience comparison">'+esc(j.exp_label)+(j.exp_fit?' &#9989;':'')+'</span>'):'';
    return `<tr>
      <td>${i+1}</td>
      <td><span class="score ${scoreClass(j.score)}">${j.score}%</span>${j.skill_pct!=null?('<div class="note" style="font-size:10px;margin-top:2px">skills '+j.skill_pct+'%</div>'):''}</td>
      <td><strong>${esc(j.title)}</strong>${j.is_remote?' <span class="chip">remote</span>':''}${exp}${j.big?' <span class="tag add" style="font-size:10px">big co</span>':''}${j.salary_lpa>0?(' <span class="chip"'+(j.salary_lpa>CURRENT_LPA?' style="background:#1c7c3f;color:#fff" title="above your current pay"':'')+'>'+j.salary_lpa+' LPA'+(j.salary_lpa>CURRENT_LPA?' ↑':'')+'</span>'):''}${matchLine}${missLine}</td>
      <td>${esc(j.company)}</td>
      <td class="note">${size}</td>
      <td>${esc(j.location)}</td>
      <td class="note">${j.site?('via '+esc(j.site)):''}</td>
      <td>${esc(j.date_posted)}</td>
      <td>${j.job_url?'<a href="'+esc(j.job_url)+'" target="_blank" rel="noopener">Open</a>':''}</td>
      <td><button onclick="applyKit(${i})" style="margin-bottom:4px">Apply</button><br><button class="secondary" onclick="useInTailor(${i})">Tailor &#8595;</button></td>
    </tr>`;
  }).join('');
}

function chiplist(list, cls){ return (list||[]).map(s=>'<span class="tag '+cls+'">'+esc((s+'').split(' (')[0])+'</span>').join(''); }

// Render the EDITABLE matching PROFILE we extracted from your resume + inputs.
// You can correct titles/skills/experience here before fetching; the edits are
// what jobs get matched against. Stored in window._profile.
function renderProfile(p, terms){
  const el=$('#profilePanel'); if(!p){ el.style.display='none'; window._profile=null; return; }
  window._profile = p;
  el.style.display='';
  const csv = a => (a||[]).join(', ');
  const ro=(label,val)=> val ? ('<div class="field" style="margin-bottom:6px"><label>'+label+'</label><div class="note">'+esc(val)+'</div></div>') : '';
  const rotags=(label,list,cls)=> (list&&list.length) ? ('<div class="field" style="margin-bottom:6px"><label>'+label+'</label><div class="tagrow">'+chiplist(list,cls)+'</div></div>') : '';
  el.innerHTML =
    '<div class="bar" style="margin-bottom:8px"><strong>We analyzed your resume — here\'s what we found</strong>'
    + '<span class="note">Correct anything below, then click <b>Fetch jobs</b>. Jobs are matched against this.</span></div>'
    + '<div class="grid2">'
    +   '<div>'
    +     '<div class="field" style="margin-bottom:8px"><label>Target titles (comma-separated)</label>'
    +       '<textarea id="pf_titles" style="min-height:40px">'+esc(csv(p.target_titles||p.job_titles))+'</textarea></div>'
    +     '<div class="field" style="margin-bottom:8px"><label>Primary skills — searched &amp; matched (comma-separated)</label>'
    +       '<textarea id="pf_skills" style="min-height:52px">'+esc(csv(p.primary_skills))+'</textarea></div>'
    +     '<div class="field" style="margin-bottom:8px"><label>Extra skills you added (comma-separated)</label>'
    +       '<textarea id="pf_added" style="min-height:40px">'+esc(csv(p.user_added_skills))+'</textarea></div>'
    +     '<div class="bar" style="margin-bottom:0">'
    +       '<label class="note">Experience <input id="pf_years" type="number" min="0" max="40" value="'+esc(''+(p.experience_years||0))+'" style="width:60px"/> yrs <span class="pill">'+esc(p.experience_level||'')+'</span></label>'
    +       '<label class="note">Work mode <select id="pf_remote"><option value="any"'+(p.remote_preference!=='remote'?' selected':'')+'>any</option><option value="remote"'+(p.remote_preference==='remote'?' selected':'')+'>remote</option></select></label>'
    +     '</div>'
    +     '<div class="note" style="margin-top:4px">Will reject jobs needing more than <b>'+esc(''+((p.experience_years||0)+1))+' yrs</b>.</div>'
    +   '</div>'
    +   '<div>'
    +     ro('Name', p.name) + ro('Email', p.email) + ro('Phone', p.phone)
    +     ro('Education', p.education)
    +     rotags('Secondary skills (mentioned, not matched on)', p.secondary_skills, 'miss')
    +     rotags('Domains', p.domains, 'add')
    +     rotags('Companies worked at', p.companies_worked_at, 'add')
    +     rotags('Certifications', p.certifications, 'add')
    +   '</div>'
    + '</div>'
    + (terms&&terms.length?('<div class="note" style="margin-top:8px">Will search: <b>'+terms.map(esc).join('</b> · <b>')+'</b></div>'):'');
}

// Merge the user's edits from the profile panel back into window._profile so the
// fetch matches against the corrected profile. Returns null if never previewed.
function collectProfileEdits(){
  const p = window._profile; if(!p) return null;
  const e = Object.assign({}, p);
  const csv = id => { const el=$('#'+id); return el ? el.value.split(',').map(s=>s.trim()).filter(Boolean) : undefined; };
  const tt=csv('pf_titles'); if(tt){ e.target_titles=tt; e.job_titles=tt; }
  const ps=csv('pf_skills'); if(ps) e.primary_skills=ps;
  const ua=csv('pf_added'); if(ua) e.user_added_skills=ua;
  const ye=$('#pf_years'); if(ye) e.experience_years=parseInt(ye.value||'0')||0;
  const rm=$('#pf_remote'); if(rm) e.remote_preference=rm.value;
  return e;
}
// Changing the source inputs invalidates a previewed profile — force a re-preview.
function invalidateProfile(){ window._profile=null; const el=$('#profilePanel'); if(el){ el.style.display='none'; el.innerHTML=''; } }

// Show why jobs were filtered OUT (the strict skill/experience/title gates), and
// whether we had to relax the skill threshold to fill the page.
function renderDebug(dbg){
  const el=$('#debugPanel'); if(!dbg){ el.innerHTML=''; return; }
  let html='Fetched <b>'+dbg.fetched+'</b> · kept <b>'+dbg.kept+'</b> · filtered out <b>'+dbg.rejected_count+'</b> '
         + '(skill threshold '+Math.round((dbg.min_ratio||0)*100)+'%).';
  if(dbg.relaxed) html+=' <span style="color:var(--ambt)">&#9888; Few strict matches — relaxed the skill threshold so the page isn\'t empty.</span>';
  if((dbg.rejected||[]).length){
    const rows=dbg.rejected.map(x=>'<li>'+esc(x.title||'(untitled)')+(x.company?(' — '+esc(x.company)):'')+(x.site?(' ['+esc(x.site)+']'):'')+': <span class="note">'+esc(x.reason)+'</span></li>').join('');
    html+='<details style="margin-top:6px"><summary style="cursor:pointer">Show filtered-out jobs ('+dbg.rejected.length+')</summary>'
        + '<ul style="margin:6px 0 0;padding-left:18px;max-height:240px;overflow:auto">'+rows+'</ul></details>';
  }
  el.innerHTML=html;
}

async function previewProfile(){
  const btn=$('#previewBtn'); const old=btn.textContent; btn.disabled=true; btn.textContent='Analyzing…';
  try{
    const fd=new FormData();
    const f=$('#jfFile').files[0]; if(f) fd.append('file', f);
    fd.append('position', $('#jfPosition').value||'');
    fd.append('years', $('#years').value||'');
    fd.append('jd', $('#jfJD').value||'');
    fd.append('skills', $('#jfSkills').value||'');
    const r=await fetch('/api/profile',{method:'POST', body:fd});
    const d=await r.json();
    if(!r.ok){ toast('Profile failed: '+(d.detail||r.status)); return; }
    renderProfile(d.profile, d.search_terms);
    toast('Profile extracted — verify it, then Fetch jobs.');
  }catch(e){ toast('Profile error: '+e); }
  finally{ btn.disabled=false; btn.textContent=old; }
}

async function loadJobs(){
  // Pull the whole ranked feed, then page through it 50 at a time on the client.
  // Shows the same busy button + live timer as matchFeed/fetchJobs, so a click
  // never looks like it did nothing while the request is in flight.
  const btn=$('#matchBtn'); const old=btn?btn.textContent:''; if(btn) setBusy(btn,true);
  jobs=[]; $('#count').textContent='';
  $('#jobsBody').innerHTML='<tr><td colspan="10" class="empty"><span class="spin"></span> <span id="loadStatus">Loading the daily feed…</span></td></tr>';
  const stopTimer=startTimer(t=>{
    if(btn) btn.innerHTML='<span class="spin"></span> Loading… '+t;
    const cell=document.getElementById('loadStatus');
    if(cell) cell.textContent='Loading the daily feed… '+t;
  });
  try{
    const r = await fetch('/api/jobs?limit=1000');
    const d = await r.json();
    jobs = d.jobs||[];
    window._fetchedAt = d.fetched_at?('fetched '+d.fetched_at):'';
    shown = PAGE;
    renderJobs();
  }catch(e){ toast('Load error: '+e); }
  finally{ stopTimer(); if(btn){ setBusy(btn,false); btn.textContent=old; } }
}

// Hosted (feed) mode: rank the daily feed against an uploaded resume / profile —
// no scraping, so it works on Vercel. Falls back to the generic feed if nothing
// was provided to match against.
async function matchFeed(){
  const f=$('#jfFile').files[0];
  const edited=collectProfileEdits();
  const hasInput = f || $('#jfPosition').value.trim() || $('#jfSkills').value.trim()
                   || $('#jfJD').value.trim() || edited;
  if(!hasInput){ return loadJobs(); }
  const btn=$('#matchBtn'); const old=btn.textContent; setBusy(btn,true);
  jobs=[]; $('#count').textContent='';
  $('#jobsBody').innerHTML='<tr><td colspan="10" class="empty"><span class="spin"></span> <span id="matchStatus">Matching the daily feed to your resume…</span></td></tr>';
  const stopTimer=startTimer(t=>{
    btn.innerHTML='<span class="spin"></span> Matching… '+t;
    const cell=document.getElementById('matchStatus');
    if(cell) cell.textContent='Matching the daily feed to your resume… '+t;
  });
  try{
    const fd=new FormData();
    if(f) fd.append('file', f);
    fd.append('position', $('#jfPosition').value||'');
    fd.append('years', $('#years').value||'');
    fd.append('jd', $('#jfJD').value||'');
    fd.append('skills', $('#jfSkills').value||'');
    if(edited) fd.append('profile_json', JSON.stringify(edited));
    const r=await fetch('/api/feed/match?limit=1000',{method:'POST',body:fd});
    const d=await r.json();
    if(!r.ok){ toast('Match failed: '+(d.detail||r.status)); }
    else{ jobs=d.jobs||[]; window._fetchedAt=d.fetched_at?('feed '+d.fetched_at):''; shown=PAGE;
          renderJobs(); renderProfile(d.profile, d.search_terms); renderDebug(d.debug);
          toast(jobs.length+(d.guided?' jobs from the feed matched to your resume.':' jobs from the feed.')); }
  }catch(e){ toast('Match error: '+e); }
  finally{ stopTimer(); setBusy(btn,false); btn.textContent=old; }
}

async function fetchJobs(){
  // Live fetch in BOTH modes. Local scrapes every board (LinkedIn/Indeed/Google…)
  // from your un-blocked home IP. Vercel can't reach those boards (datacenter IPs
  // are blocked), so the backend automatically switches to a LIVE query of the free
  // REST APIs (Remotive/RemoteOK/Jobicy/Arbeitnow + career pages) — genuinely live,
  // just narrower coverage. Either way it's ranked to your uploaded resume/profile.
  const btn=$('#fetchBtn'); const old=btn.textContent; setBusy(btn,true);
  // Lock the (separate-card) profile panel too, so prefilled data can't be edited mid-fetch.
  $('#profilePanel').querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=true);
  // Clear the previous results immediately so stale jobs don't linger.
  jobs=[]; $('#count').textContent='';
  const what = LIVE ? 'Searching all boards for fresh jobs'
                    : 'Searching live job APIs (Remotive, RemoteOK, career pages…)';
  $('#jobsBody').innerHTML='<tr><td colspan="10" class="empty"><span class="spin"></span> <span id="fetchStatus">'+what+'…</span></td></tr>';
  const stopTimer=startTimer(t=>{
    btn.innerHTML='<span class="spin"></span> Searching… '+t;
    const cell=document.getElementById('fetchStatus');
    if(cell) cell.textContent=what+'… '+t;
  });
  try{
    const fd=new FormData();
    const f=$('#jfFile').files[0]; if(f) fd.append('file', f);
    fd.append('position', $('#jfPosition').value||'');
    fd.append('years', $('#years').value||'');
    fd.append('jd', $('#jfJD').value||'');
    fd.append('skills', $('#jfSkills').value||'');
    fd.append('career', $('#jfCareer').checked?'true':'false');
    // If you previewed & edited your profile, send those edits to match against.
    const edited=collectProfileEdits(); if(edited) fd.append('profile_json', JSON.stringify(edited));
    const r=await fetch('/api/fetch?hours_old='+$('#hours').value+'&limit='+($('#limit').value||50),
                        {method:'POST', body:fd});
    const d=await r.json();
    if(!r.ok){ toast('Fetch failed: '+(d.detail||r.status)); }
    else { jobs=d.jobs||[]; window._fetchedAt=d.fetched_at?('fetched '+d.fetched_at):''; shown=PAGE; renderJobs();
           renderProfile(d.profile, d.search_terms); renderDebug(d.debug);
           toast(jobs.length+(d.guided?' jobs matched to your profile.':' jobs ranked by tech relevance.')+(d.search_terms?' Searched: '+d.search_terms.join(', '):'')); }
  }catch(e){ toast('Fetch error: '+e); }
  finally{ stopTimer(); setBusy(btn,false); btn.textContent=old;
           $('#profilePanel').querySelectorAll('input,select,textarea,button').forEach(el=>el.disabled=false); }
}

function showTab(which){
  const find = which==='find';
  document.getElementById('findJobs').style.display = find?'':'none';
  document.getElementById('createResume').style.display = find?'none':'';
  $('#tabFind').classList.toggle('active', find);
  $('#tabCreate').classList.toggle('active', !find);
}

function useInTailor(i){
  const j=jobs[i];
  const jd = j.description || (j.title+' at '+j.company);
  $('#genJD').value = jd; $('#tailorJD').value = jd;
  $('#genTitle').value = j.title||''; $('#genCompany').value = j.company||'';
  showTab('create');
  toast('Job sent to Create resume — generate from your saved resume (A) or tailor an upload (B).');
}

// Semi-auto APPLY ASSISTANT: for one job, tailor the resume to it, draft a cover
// note, and open the apply link — you review and submit yourself. No auto-submit.
async function applyKit(i){
  const j=jobs[i]; if(!j) return;
  toast('Preparing your apply kit — tailoring resume to this job…');
  try{
    const r=await fetch('/api/apply/kit',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title:j.title||'', company:j.company||'',
                           description:j.description||'', job_url:j.job_url||'', format:'pdf'})});
    const d=await r.json();
    if(!r.ok){ toast('Apply kit failed: '+(d.detail||r.status)); return; }
    window._applyKit=d; showApplyModal(j, d);
  }catch(e){ toast('Apply kit error: '+e); }
}
function showApplyModal(j, d){
  const files=d.files||[];
  const emph=(d.emphasized||[]).slice(0,12).map(s=>'<span class="tag have" style="font-size:10px">'+esc(s)+'</span>').join('');
  const dl=files.map((f,k)=>'<button onclick="dlKitFile('+k+')">Download '+esc(f.name)+'</button>').join(' ');
  $('#applyModal').innerHTML=
    '<div class="modal-bg" onclick="if(event.target===this)closeApply()"><div class="modal">'
    +'<div class="bar" style="justify-content:space-between"><strong>Apply kit — '+esc(j.title||'')+'</strong>'
    +'<button class="secondary" onclick="closeApply()">Close</button></div>'
    +'<div class="note" style="margin:-4px 0 14px">'+esc(j.company||'')+(j.location?(' · '+esc(j.location)):'')+'</div>'
    +'<div class="field"><label>1 · Resume tailored to this job</label>'
    +'<div class="bar">'+(dl||'<span class="note">No file.</span>')+'</div>'
    +(emph?('<div class="tagrow" style="margin-top:6px">'+emph+'</div>'):'')+'</div>'
    +'<div class="field" style="margin-top:12px"><label>2 · Cover note (edit, then copy)</label>'
    +'<textarea id="coverBox" style="min-height:180px">'+esc(d.cover_note||'')+'</textarea>'
    +'<div class="bar" style="margin-top:6px"><button class="secondary" onclick="copyCover()">Copy cover note</button></div></div>'
    +'<div class="field" style="margin-top:12px"><label>3 · Apply on the site</label><div>'
    +(j.job_url?('<a href="'+esc(j.job_url)+'" target="_blank" rel="noopener"><button>Open job &amp; apply &#8599;</button></a>')
               :'<span class="note">This listing has no direct apply link.</span>')
    +'</div><div class="note" style="margin-top:6px">Review the resume &amp; note, then submit on the site yourself.</div></div>'
    +'</div></div>';
}
function closeApply(){ $('#applyModal').innerHTML=''; }
function dlKitFile(k){ const f=((window._applyKit||{}).files||[])[k]; if(f) b64Download(f.name, f.b64, f.mime); }
function copyCover(){ const t=$('#coverBox'); if(!t) return; t.select();
  const done=()=>toast('Cover note copied.');
  if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(t.value).then(done,()=>{document.execCommand('copy');done();}); }
  else { document.execCommand('copy'); done(); }
}

async function generateResume(){
  const btn=$('#genBtn'); const old=btn.textContent; setBusy(btn,true);
  const stopTimer=startTimer(t=>{ btn.innerHTML='<span class="spin"></span> Generating… '+t; });
  $('#genResult').textContent='';
  try{
    const r=await fetch('/api/resume/build',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title:$('#genTitle').value||'', company:$('#genCompany').value||'',
                           description:$('#genJD').value||'', format:$('#genFmt').value})});
    const d=await r.json();
    if(!r.ok){ $('#genResult').textContent='Failed: '+(d.detail||r.status); toast('Generate failed.'); return; }
    (d.files||[]).forEach(f=>b64Download(f.name, f.b64, f.mime));
    const emph=(d.emphasized||[]).length, ats=(d.ats_keywords||[]).length;
    $('#genResult').textContent='Downloaded '+(d.files||[]).map(f=>f.name).join(', ')
      +(emph?(' · emphasized '+emph+' skills'):'')
      +(ats?(' · '+ats+' ATS keywords added'):'');
    toast('Resume generated in your format.');
    loadResumes();
  }catch(e){ $('#genResult').textContent='Error: '+e; }
  finally{ stopTimer(); setBusy(btn,false); btn.textContent=old; }
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
  const btn=$('#tailorBtn'); const old=btn.textContent; setBusy(btn,true);
  const stopTimer=startTimer(t=>{ btn.innerHTML='<span class="spin"></span> Tailoring… '+t; });
  $('#tailorResult').innerHTML='Working — building your resume'+($('#tailorFmt').value!=='docx'?' (PDF via Word can take a few seconds)':'')+'…';
  try{
    const r=await fetch('/api/resume/tailor',{method:'POST',body:fd});
    const d=await r.json();
    if(!r.ok){ $('#tailorResult').textContent='Failed: '+(d.detail||r.status); toast('Tailoring failed.'); return; }
    (d.files||[]).forEach(file=>b64Download(file.name, file.b64, file.mime));
    const a=d.analysis||{};
    let html='';
    html+= d.layout_preserved ? '<div class="note">&#10003; Your original Word layout &amp; style were preserved.</div>'
                              : '<div class="note">&#9888; PDF upload: a PDF cannot be edited in place, so it was rebuilt as a structured one-page document (name, contact, section headings &amp; bullets preserved). For an exact match to your original styling, upload the .docx version.</div>';
    if(d.pdf_note) html+='<div class="note" style="color:var(--ambt)">PDF note: '+esc(d.pdf_note)+'</div>';
    if((a.present||[]).length) html+='<div class="field" style="margin-top:10px"><label>Highlighted (you already have, JD wants)</label><div class="tagrow">'+tags(a.present,'have')+'</div></div>';
    if((a.typed||[]).length) html+='<div class="field"><label>Added from your skills box</label><div class="tagrow">'+tags(a.typed,'add')+'</div></div>';
    if(d.ats_added && (a.suggestions||[]).length) html+='<div class="field"><label>Added for ATS keyword coverage — <b>verify these are truthful before sending</b></label><div class="tagrow">'+tags(a.suggestions,'miss')+'</div></div>';
    if(!a.had_request) html+='<div class="note" style="margin-top:8px">No JD or skills given — returned your resume unchanged in the chosen format(s).</div>';
    const aFiles=(d.files||[]).filter(f=>f.version&&f.version[0]==='A').map(f=>esc(f.name));
    const bFiles=(d.files||[]).filter(f=>f.version&&f.version[0]==='B').map(f=>esc(f.name));
    html+='<div class="field" style="margin-top:10px"><label>Two versions downloaded</label>'
         +'<div class="note"><b>A — Standard:</b> only skills you genuinely have. Safe to send anywhere. '+(aFiles.join(', ')||'—')+'</div>'
         +'<div class="note"><b>B — ATS-optimized:</b> A plus the JD\'s remaining keywords for a higher ATS score'
         +(d.ats_added?(' (+'+d.ats_added+' keywords)'):'')+' — <b>verify they\'re truthful before sending.</b> '+(bFiles.join(', ')||'—')+'</div></div>';
    $('#tailorResult').innerHTML=html;
    toast('Tailored resume downloaded.');
    loadResumes();
  }catch(e){ $('#tailorResult').textContent='Error: '+e; }
  finally{ stopTimer(); setBusy(btn,false); btn.textContent=old; }
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

$('#tabFind').onclick=()=>showTab('find');
$('#tabCreate').onclick=()=>showTab('create');
$('#fetchBtn').onclick=fetchJobs;
$('#matchBtn').onclick=matchFeed;
$('#previewBtn').onclick=previewProfile;
// Editing a source input invalidates a previewed profile -> re-preview to refresh.
['jfFile','jfPosition','jfSkills','jfJD','years'].forEach(id=>{
  const el=$('#'+id); if(el) el.addEventListener('change', invalidateProfile);
});
$('#loadMoreBtn').onclick=showMore;
$('#genBtn').onclick=generateResume;
$('#tailorBtn').onclick=tailorResume;
$('#refreshResumes').onclick=loadResumes;
showTab('find');
// SAME all-websites result everywhere:
//   The cron scrapes ALL boards (LinkedIn/Indeed/Google/Glassdoor/ZipRecruiter/
//   Naukri/Bayt) + career pages + free APIs into data/jobs.json, every few hours,
//   from un-blocked IPs. Both local & Vercel rank that same feed to your resume.
//   Local additionally offers a true real-time scrape ("Fetch live jobs").
$('#modePill').textContent = LIVE ? 'LOCAL · live + feed' : 'VERCEL · live APIs + feed';
if(!LIVE){
  // Hosted: "Load latest jobs" ranks the cron feed (already gated to your saved
  // profile); "Fetch live jobs" does a genuinely live query of the free job APIs.
  const fh=$('#feedHint'); if(fh) fh.style.display='';
  $('#jobsBody').innerHTML='<tr><td colspan="10" class="empty"><b>Load latest jobs</b> — instantly ranks the all-boards feed (LinkedIn, Indeed, Google, career pages &amp; more, refreshed every 3h, already matched to your saved resume). <br><b>Fetch live jobs</b> — does a live search of the free job APIs (Remotive, RemoteOK &amp; career pages) right now; upload a resume above to rank it to you. Both work on mobile, no computer needed.</td></tr>';
} else {
  $('#jobsBody').innerHTML='<tr><td colspan="10" class="empty">Optionally upload your resume (and/or type a role) above, then click <b>Fetch live jobs</b> for a fresh real-time scrape of all boards, or <b>Load latest jobs</b> to rank the shared all-boards feed (same result the hosted site shows).</td></tr>';
}
// Open FRESH every time in BOTH modes — don't auto-show jobs. The user clicks a
// button ("Fetch live jobs" / "Load latest jobs") to see them.
loadResumes();

// PWA: register the service worker so the site is installable and works offline.
if('serviceWorker' in navigator){
  window.addEventListener('load', ()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
}
</script>
</body>
</html>
"""


# =========================================================================== #
# COMPANY DISCOVERY PAGE  (/companies) — self-contained: Leaflet map + table +
# filters + export. Uses OpenStreetMap data via our /api/companies (free).
# =========================================================================== #
COMPANIES_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>Company Discovery — every business in an area</title>
<link rel="icon" href="/favicon.ico" type="image/svg+xml"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  :root{ --bg:#0b111c; --card:#0e1726; --line:#27364d; --ink:#e7eef9; --mut:#8aa0bd; --accent:#3b82f6; }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;overflow-x:hidden}
  header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;flex-wrap:wrap}
  header h1{font-size:17px;margin:0}
  a{color:#7db0ff;text-decoration:none} a:hover{text-decoration:underline}
  .pill{font-size:11px;padding:2px 9px;border:1px solid var(--line);border-radius:20px;color:var(--mut)}
  main{padding:16px 20px;max-width:1400px;margin:0 auto}
  .bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
  input,select{background:#0e1726;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:9px 11px;font-size:14px}
  button{background:var(--accent);color:#fff;border:0;padding:9px 15px;border-radius:8px;cursor:pointer;font-size:14px;min-height:40px}
  button.sec{background:#1e293b;color:var(--ink);border:1px solid var(--line)}
  button:disabled{opacity:.5;cursor:default}
  .layout{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  @media(max-width:900px){ .layout{grid-template-columns:1fr} #map{height:340px!important} }
  #map{height:600px;border:1px solid var(--line);border-radius:12px}
  .panel{border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column;max-height:600px}
  .filters{display:flex;gap:7px;flex-wrap:wrap;padding:10px;border-bottom:1px solid var(--line)}
  .filters input,.filters select{padding:6px 8px;font-size:12px}
  .list{overflow:auto;flex:1}
  .co{padding:10px 12px;border-bottom:1px solid var(--line);cursor:pointer}
  .co:hover{background:#10192880}
  .co.active{background:#14233c}
  .co .nm{font-weight:600}
  .co .meta{color:var(--mut);font-size:12px;margin-top:2px}
  .tag{display:inline-block;font-size:10px;border-radius:10px;padding:1px 7px;border:1px solid var(--line);margin-right:4px;color:var(--mut)}
  .conf{float:right;font-size:11px;font-weight:700;padding:1px 7px;border-radius:6px;background:#16331a;color:#9be7a4}
  .conf.lo{background:#3a1f1f;color:#f0a0a0} .conf.md{background:#3a3417;color:#f0d98a}
  .note{color:var(--mut);font-size:12px}
  .count{color:var(--mut);font-size:13px}
  .leaflet-popup-content-wrapper,.leaflet-popup-tip{background:#0e1726;color:var(--ink);border:1px solid var(--line)}
  .leaflet-popup-content{margin:12px 14px;font-size:13px}
  .pp b{color:var(--ink)}
  .spin{display:inline-block;width:14px;height:14px;border:2px solid #fff5;border-top-color:#fff;border-radius:50%;animation:r .8s linear infinite;vertical-align:-2px}
  @keyframes r{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<header>
  <h1>🏢 Company Discovery</h1>
  <span class="pill">free · OpenStreetMap</span>
  <a href="/">← back to Job Finder</a>
  <span class="note" id="status"></span>
</header>
<main>
  <div class="bar">
    <input id="area" placeholder="Area, locality, sector or pincode — e.g. Noida Sector 62" style="flex:1;min-width:240px"/>
    <label class="note">Max <input id="limit" type="number" value="500" min="20" max="2000" style="width:80px"/></label>
    <button id="go">Find companies</button>
    <button class="sec" id="exCsv">CSV</button>
    <button class="sec" id="exJson">JSON</button>
    <button class="sec" id="exGeo">GeoJSON</button>
  </div>
  <p class="note" style="margin-top:-4px">Fetches every named business on the map in that area — offices, IT/software firms, agencies, shops, coworking spaces & more — with location, website, phone & confidence score. Click a company to see it on the map; click <b>Detect tech / contacts</b> in its popup to pull the tech stack, emails, socials & careers page from its website.</p>

  <div class="layout">
    <div class="panel">
      <div class="filters">
        <input id="fSearch" placeholder="search name / industry…" style="flex:1;min-width:120px"/>
        <select id="fType"><option value="">All types</option></select>
        <select id="fIndustry"><option value="">All industries</option></select>
        <label class="note"><input type="checkbox" id="fWeb"/> has website</label>
        <label class="note"><input type="checkbox" id="fCowork"/> coworking</label>
      </div>
      <div class="list" id="list"><div class="co note">Enter an area and click <b>Find companies</b>.</div></div>
    </div>
    <div id="map"></div>
  </div>
</main>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const $=s=>document.querySelector(s);
let ALL=[], VIEW=[], markers=[], map, layer, active=null;

function initMap(){
  map=L.map('map',{scrollWheelZoom:true}).setView([28.61,77.37],12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);
  layer=L.layerGroup().addTo(map);
}
function colorFor(c){
  const t=((c.industry||'')+' '+(c.business_type||'')).toLowerCase();
  if(t.includes('cowork')) return '#a78bfa';
  if(t.includes('it')||t.includes('software')||c.technical_work) return '#3b82f6';
  if(t.includes('financ')||t.includes('insur')||t.includes('account')) return '#22c55e';
  if(t.includes('retail')||t.includes('shop')||t.includes('local')) return '#f59e0b';
  if(t.includes('market')||t.includes('advert')||t.includes('consult')) return '#ec4899';
  return '#94a3b8';
}
function esc(s){return (s||'').toString().replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}

// Lock every input / filter / export control while a search runs, so the
// entered data can't be edited mid-fetch. Unlocked again when it finishes.
const CONTROLS=['area','limit','go','exCsv','exJson','exGeo','fSearch','fType','fIndustry','fWeb','fCowork'];
function lock(on){ CONTROLS.forEach(id=>{const el=$('#'+id); if(el) el.disabled=on;}); }

async function go(){
  const area=$('#area').value.trim(); if(!area){alert('Enter an area');return;}
  const btn=$('#go'), old=btn.textContent; lock(true); btn.innerHTML='<span class="spin"></span> Searching…';
  $('#status').textContent=''; $('#list').innerHTML='<div class="co note"><span class="spin"></span> Querying OpenStreetMap…</div>';
  try{
    const r=await fetch('/api/companies?area='+encodeURIComponent(area)+'&limit='+($('#limit').value||500));
    const d=await r.json();
    if(d.error){ $('#list').innerHTML='<div class="co note">'+esc(d.error)+'</div>'; $('#status').textContent=''; return; }
    ALL=d.companies||[];
    $('#status').textContent=d.resolved? ('📍 '+d.resolved.slice(0,60)+' · '+d.total_found+' found'):'';
    if(d.center) map.setView([d.center.lat,d.center.lon],14);
    buildFilters(); applyFilters();
  }catch(e){ $('#list').innerHTML='<div class="co note">Error: '+esc(e)+'</div>'; }
  finally{ lock(false); btn.textContent=old; }
}

function buildFilters(){
  const types=[...new Set(ALL.map(c=>c.business_type).filter(Boolean))].sort();
  const inds=[...new Set(ALL.map(c=>c.industry).filter(Boolean))].sort();
  $('#fType').innerHTML='<option value="">All types ('+ALL.length+')</option>'+types.map(t=>'<option>'+esc(t)+'</option>').join('');
  $('#fIndustry').innerHTML='<option value="">All industries</option>'+inds.map(t=>'<option>'+esc(t)+'</option>').join('');
}
function applyFilters(){
  const q=$('#fSearch').value.toLowerCase(), ty=$('#fType').value, ind=$('#fIndustry').value,
        web=$('#fWeb').checked, cow=$('#fCowork').checked;
  VIEW=ALL.filter(c=>{
    if(ty && c.business_type!==ty) return false;
    if(ind && c.industry!==ind) return false;
    if(web && !c.website) return false;
    if(cow && !((c.business_type||'').toLowerCase().includes('cowork'))) return false;
    if(q){ const blob=((c.company_name||'')+' '+(c.industry||'')+' '+(c.address||'')).toLowerCase(); if(!blob.includes(q)) return false; }
    return true;
  });
  render();
}
function render(){
  layer.clearLayers(); markers=[];
  $('#list').innerHTML = VIEW.length? '' : '<div class="co note">No companies match the filters.</div>';
  VIEW.forEach((c,i)=>{
    const cc=colorFor(c);
    if(c.latitude&&c.longitude){
      const m=L.circleMarker([c.latitude,c.longitude],{radius:7,color:cc,fillColor:cc,fillOpacity:.8,weight:1});
      m.bindPopup(popupHtml(c,i)); m.addTo(layer); markers[i]=m;
    }
    const conf=c.confidence>=80?'':(c.confidence>=60?'md':'lo');
    const row=document.createElement('div'); row.className='co'; row.dataset.i=i;
    const webOnly=!c.latitude;
    row.innerHTML='<span class="conf '+conf+'">'+c.confidence+'</span><div class="nm">'+esc(c.company_name)+'</div>'
      +'<div class="meta">'+esc(c.industry||'')+(c.address?' · '+esc(c.address.slice(0,50)):'')+'</div>'
      +'<div style="margin-top:3px"><span class="tag" style="border-color:'+cc+';color:'+cc+'">'+esc(c.business_type||'')+'</span>'
      +(c.website?'<span class="tag">🌐 web</span>':'')+(c.phones&&c.phones.length?'<span class="tag">📞</span>':'')
      +(webOnly?'<span class="tag" title="found via web search — no map pin; click opens site">🔗 web-listed</span>':'')+'</div>';
    row.onclick=()=>focusCo(i);
    $('#list').appendChild(row);
  });
  $('#status').textContent=$('#status').textContent.split(' · showing')[0]+' · showing '+VIEW.length;
}
function jobsUrl(c){
  // Recent openings: the company's own careers page if we detected it, else a
  // LinkedIn jobs search for the company, filtered to the past week (India).
  return c.careers || ('https://www.linkedin.com/jobs/search/?keywords='
    + encodeURIComponent(c.company_name) + '&location=India&f_TPR=r604800');
}
function popupHtml(c,i){
  const s=[];
  s.push('<div class="pp"><b>'+esc(c.company_name)+'</b>');
  s.push('<div class="note">'+esc(c.industry||'')+' · '+esc(c.business_type||'')+'</div>');
  if(c.address) s.push('<div>'+esc(c.address)+'</div>');
  if(c.website) s.push('<div>🌐 <a href="'+esc(c.website)+'" target="_blank" rel="noopener">'+esc(c.website.replace(/^https?:\/\//,''))+'</a></div>');
  if(c.phones&&c.phones.length) s.push('<div>📞 '+esc(c.phones.join(', '))+'</div>');
  s.push('<div id="enr'+i+'"></div>');
  // Read-only action buttons (no editable fields in the detail view).
  const a=[];
  if(c.website) a.push('<a href="'+esc(c.website)+'" target="_blank" rel="noopener"><button>🌐 Open website</button></a>');
  a.push('<a href="'+esc(jobsUrl(c))+'" target="_blank" rel="noopener"><button class="sec" id="jobsBtn'+i+'">💼 Recent jobs</button></a>');
  if(c.website) a.push('<button class="sec" onclick="enrich('+i+',this)">Detect tech / contacts</button>');
  if(c.latitude) a.push('<a href="https://www.google.com/maps/dir/?api=1&destination='+c.latitude+','+c.longitude+'" target="_blank"><button class="sec">Directions</button></a>');
  s.push('<div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">'+a.join('')+'</div>');
  s.push('<div class="note" style="margin-top:6px">confidence '+c.confidence+' · '+esc((c.source||[]).join(', '))+'</div></div>');
  return s.join('');
}
function focusCo(i){
  document.querySelectorAll('.co').forEach(r=>r.classList.toggle('active', r.dataset.i==i));
  const c=VIEW[i];
  if(c.latitude&&markers[i]){ map.flyTo([c.latitude,c.longitude],16); markers[i].openPopup(); }
  else if(c.website){ window.open(c.website,'_blank','noopener'); }  // web-only: no pin
}
async function enrich(i, btn){
  const c=VIEW[i]; const box=document.getElementById('enr'+i); if(!box) return;
  if(btn) btn.disabled=true;
  box.innerHTML='<span class="spin"></span> reading website…';
  try{
    const r=await fetch('/api/company/enrich',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:c.website})});
    const d=await r.json();
    if(d.error||d.reachable===false){ box.innerHTML='<div class="note">Website not reachable.</div>'; return; }
    c.technologies=d.technologies||[]; c.emails=d.emails||c.emails; c.careers=d.careers||''; c.hiring=d.hiring;
    // Point the "Recent jobs" button at the real careers page once found.
    if(d.careers){ const jb=document.getElementById('jobsBtn'+i);
      if(jb&&jb.parentElement&&jb.parentElement.tagName==='A') jb.parentElement.href=d.careers; }
    let h='';
    if(d.technologies&&d.technologies.length) h+='<div style="margin-top:4px">🧩 '+d.technologies.map(t=>'<span class="tag">'+esc(t)+'</span>').join('')+'</div>';
    if(d.emails&&d.emails.length) h+='<div style="margin-top:4px">✉️ '+esc(d.emails.slice(0,3).join(', '))+'</div>';
    const soc=Object.entries(d.social_links||{}).map(([k,v])=>'<a href="'+esc(v)+'" target="_blank">'+k+'</a>').join(' · ');
    if(soc) h+='<div style="margin-top:4px">'+soc+'</div>';
    if(d.careers) h+='<div style="margin-top:4px">💼 <a href="'+esc(d.careers)+'" target="_blank">Careers page</a></div>';
    if(d.hiring) h+='<div class="tag" style="margin-top:4px;border-color:#22c55e;color:#22c55e">likely hiring</div>';
    box.innerHTML=h||'<div class="note">No extra data found on site.</div>';
  }catch(e){ box.innerHTML='<div class="note">Enrich error.</div>'; if(btn) btn.disabled=false; }
}

// ---- Export ----
function dl(name,text,mime){const b=new Blob([text],{type:mime});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download=name;a.click();URL.revokeObjectURL(u);}
function exCsv(){
  if(!VIEW.length)return; const cols=['company_name','website','industry','business_type','address','city','pincode','latitude','longitude','phones','emails','confidence','source'];
  const esc2=v=>{v=Array.isArray(v)?v.join('; '):(v==null?'':v);v=(''+v).replace(/"/g,'""');return /[",\n]/.test(v)?'"'+v+'"':v;};
  const rows=[cols.join(',')].concat(VIEW.map(c=>cols.map(k=>esc2(c[k])).join(',')));
  dl('companies.csv',rows.join('\n'),'text/csv');
}
function exJson(){ if(VIEW.length) dl('companies.json',JSON.stringify(VIEW,null,2),'application/json'); }
function exGeo(){
  if(!VIEW.length)return;
  const fc={type:'FeatureCollection',features:VIEW.filter(c=>c.latitude&&c.longitude).map(c=>({
    type:'Feature',geometry:{type:'Point',coordinates:[c.longitude,c.latitude]},
    properties:{name:c.company_name,website:c.website,industry:c.industry,type:c.business_type,address:c.address,confidence:c.confidence}}))};
  dl('companies.geojson',JSON.stringify(fc,null,2),'application/geo+json');
}

initMap();
$('#go').onclick=go;
$('#area').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
['fSearch','fType','fIndustry','fWeb','fCowork'].forEach(id=>$('#'+id).addEventListener('input',applyFilters));
$('#exCsv').onclick=exCsv; $('#exJson').onclick=exJson; $('#exGeo').onclick=exGeo;
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    print(f"Job & Resume dashboard -> http://localhost:{port}  (mode: {JOBS_SOURCE})")
    uvicorn.run(app, host="127.0.0.1", port=port)
