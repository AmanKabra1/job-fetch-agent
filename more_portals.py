"""
"Hard to reach" job portals â€” fetched from their PUBLIC pages (no login, no API key).

These have no documented API, so each fetcher reads what the site itself serves to any
browser, verified live on 2026-10-06:

  * Instahyre          public job_search JSON (skills + years filter) + JobPosting JSON-LD per job
  * Cutshort           public jobs sitemap (with lastmod) + JobPosting JSON-LD per job
  * Remote Rocketship  India job sitemap + the page's embedded job JSON (incl. its own
                       ghost-job score and direct ATS apply link)
  * Wellfound          server-rendered role pages (embedded Apollo state: JD, years, pay)
  * Y Combinator       Work-at-a-Startup role pages + per-job embedded JSON
  * Reddit             r/developersIndia "hiring" search RSS (referral-style posts)

NOT fetched (and why): Hirist â€” its job pages ship no JD (loaded by a private API that
refuses outside callers); startup.jobs â€” returns 403 to every script.

Politeness: â‰¤1 request/second per portal, small per-run caps (env overridable), all
failures return [] and never abort a run. Rows use the shared shape (title / company /
location / site / date_posted / is_remote / job_url / description). Experience, salary
and the portal's own ghost score are written into the description text so jd_screener
reads them exactly like any other JD.
"""

import os
import re
import json
import html
import time
import datetime as dt
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import requests

import jd_screener as JDS
from new_sources import _strip, _DEV, _SENIOR

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
       "Accept-Language": "en"}
_TIMEOUT = 30
_SLEEP = 0.8                                   # seconds between page fetches on one portal
_BAD_TITLE = re.compile(r"\b(senior|sr\.?|lead|staff|principal|architect|manager|head|director|intern|trainee|"
                        r"fresher|devops|sre|qa|sdet|java\b|\.net|php|ios|android|data[- ]analyst|sales|marketing)\b", re.I)
CAPS = {  # pages opened per portal per run
    "instahyre": int(os.environ.get("MP_INSTAHYRE", "40")),
    "cutshort": int(os.environ.get("MP_CUTSHORT", "180")),
    "remoterocketship": int(os.environ.get("MP_RR", "45")),
    "yc": int(os.environ.get("MP_YC", "30")),
}


def _get(url, **kw):
    try:
        r = requests.get(url, headers=_UA, timeout=_TIMEOUT, **kw)
        return r if r.status_code == 200 else None
    except Exception:
        return None


def _window(max_age_hours):
    """These portals refresh slowly (and sitemaps give edit times), so never use a window
    tighter than a week â€” the screener's repost guard handles stale/ghost roles."""
    return max(int(max_age_hours or 0), 168)


def _age_ok(iso, hours):
    s = str(iso or "").strip().replace("Z", "+00:00")
    if not s:
        return True
    try:
        if s.isdigit():
            d = dt.datetime.fromtimestamp(int(s), dt.timezone.utc)
        else:
            d = dt.datetime.fromisoformat(s)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
        return dt.datetime.now(dt.timezone.utc) - d <= dt.timedelta(hours=hours)
    except Exception:
        return True


def _ld_jobposting(text):
    for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', text, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        for x in (d if isinstance(d, list) else [d]):
            if isinstance(x, dict) and x.get("@type") == "JobPosting":
                return x
    return None


def _next_data(text):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
    try:
        return json.loads(m.group(1)) if m else None
    except Exception:
        return None


def _years_line(months=None, lo=None, hi=None):
    if months:
        y = round(float(months) / 12, 1)
        y = int(y) if y == int(y) else y
        return f"Experience: {y}+ years required."
    if lo not in (None, "", "None"):
        return f"Experience: {lo}+ years required." if hi in (None, "", "None") else f"Experience: {lo}-{hi} years."
    return ""


def _ld_salary(jp):
    bs = (jp or {}).get("baseSalary")
    if not isinstance(bs, dict):
        return ""
    v = bs.get("value") or {}
    lo, hi = v.get("minValue"), v.get("maxValue") or v.get("value")
    cur = (bs.get("currency") or "").upper()
    unit = str(v.get("unitText") or "YEAR").upper()
    if not hi:
        return ""
    try:
        hi = float(hi); lo = float(lo or hi)
    except (TypeError, ValueError):
        return ""
    f = 12 if unit.startswith("MONTH") else 1
    hi *= f; lo *= f
    if cur == "INR" and hi >= 100000:
        return f"Salary: {lo / 1e5:.1f}-{hi / 1e5:.1f} LPA."
    if cur in ("USD", "EUR", "GBP") and hi >= 1000:
        return f"Salary: {cur} {int(lo)}-{int(hi)} per year."
    return ""


# --------------------------------------------------------------------------- #
# Instahyre
# --------------------------------------------------------------------------- #
_INSTA_SKILLS = ["python", "node.js", "nestjs", "typescript", "fastapi", "backend", "llm", "generative ai", "langchain"]


def fetch_instahyre(terms, max_age_hours=0, years=2):
    seen, cands = set(), []
    for skill in _INSTA_SKILLS:
        r = _get("https://www.instahyre.com/api/v1/job_search",
                 params={"job_type": 0, "company_size": 0, "skills": skill, "years": years, "limit": 35})
        if r is None:
            continue
        try:
            objs = r.json().get("objects", [])
        except Exception:
            continue
        for o in objs:
            title = o.get("title") or o.get("candidate_title") or ""
            url = o.get("public_url") or ""
            if (not url or url in seen or not _DEV.search(title) or _BAD_TITLE.search(title)):
                continue
            seen.add(url)
            cands.append((o, title, url))
        time.sleep(0.3)
    rows, win = [], max(int(max_age_hours or 0), 24 * 60)   # Instahyre posts live long; 60d cap
    for o, title, url in cands[:CAPS["instahyre"]]:
        page = _get(url)
        time.sleep(_SLEEP)
        jp = _ld_jobposting(page.text) if page is not None else None
        posted = (jp or {}).get("datePosted", "")
        if posted and not _age_ok(posted, win):
            continue
        desc = _strip((jp or {}).get("description")) if jp else ""
        skills = ", ".join(o.get("keywords") or [])
        rows.append({
            "title": title, "company": (o.get("employer") or {}).get("company_name", ""),
            "location": (o.get("locations") or "India").replace(",", ", "), "site": "instahyre",
            "date_posted": str(posted)[:10], "is_remote": "work from home" in str(o.get("locations", "")).lower(),
            "job_url": url,
            "description": (desc + f"\nSkills: {skills}").strip(),
            "company_num_employees": str((o.get("employer") or {}).get("employee_count") or ""),
        })
    return rows


# --------------------------------------------------------------------------- #
# Cutshort
# --------------------------------------------------------------------------- #
def _sitemap_entries(url):
    r = _get(url)
    if r is None:
        return []
    return re.findall(r"<url>\s*<loc>(.*?)</loc>\s*<lastmod>(.*?)</lastmod>", r.text, re.S)


def fetch_cutshort(terms, max_age_hours=0):
    win = _window(max_age_hours)
    ents = _sitemap_entries("https://cutshort-data.s3.amazonaws.com/cloudfront/public/jobs-sitemap.xml")
    pick = [(u, lm) for u, lm in ents
            if _age_ok(lm, win)
            and re.search(r"/job/(?:[^-/]+-){0,4}(?:backend|back|python|node|nest|software|sde|full|ai|llm|ml|developer|engineer|programmer)(?:-|$)", u, re.I)
            and not _BAD_TITLE.search(u.split("/job/")[-1].replace("-", " "))]
    # Cutshort's sitemap lastmod is the last EDIT, not the posting date â€” most listed jobs
    # are years old (checked: 2020-2023 postings at the top). So we must open many pages
    # and keep only those whose JSON-LD datePosted is recent. Frontend-only roles are
    # skipped up front; pages are fetched by a small thread pool (still polite overall).
    pick = [(u, lm) for u, lm in pick
            if not re.search(r"frontend|front-end|react|angular|vue|ui-|ux|wordpress|designer", u.split("/job/")[-1], re.I)]
    pick.sort(key=lambda x: x[1], reverse=True)

    def load(item):
        page = _get(item[0])
        time.sleep(_SLEEP)
        return item[0], (_ld_jobposting(page.text) if page is not None else None)

    with ThreadPoolExecutor(max_workers=6) as ex:
        loaded = list(ex.map(load, pick[:CAPS["cutshort"]]))
    rows = []
    for u, jp in loaded:
        if not jp:
            continue
        title = jp.get("title") or ""
        if not _DEV.search(title) or _BAD_TITLE.search(title):
            continue
        posted = jp.get("datePosted", "")
        if not _age_ok(posted, win):
            continue
        locs = jp.get("jobLocation")
        locs = locs if isinstance(locs, list) else [locs]
        cities = [((l or {}).get("address") or {}).get("addressLocality", "") for l in locs]
        exp = (jp.get("experienceRequirements") or {}).get("monthsOfExperience")
        desc = "\n".join(x for x in (_years_line(months=exp), _ld_salary(jp), _strip(jp.get("description")),
                                     "Skills: " + str(jp.get("skills") or "")) if x)
        rows.append({
            "title": title, "company": (jp.get("hiringOrganization") or {}).get("name", ""),
            "location": ", ".join(c for c in cities if c) or "India", "site": "cutshort",
            "date_posted": str(posted)[:10], "is_remote": "remote" in (title + desc[:300]).lower(),
            "job_url": u, "description": desc,
        })
    return rows


# --------------------------------------------------------------------------- #
# Remote Rocketship (India-eligible remote roles)
# --------------------------------------------------------------------------- #
def fetch_remoterocketship(terms, max_age_hours=0):
    win = _window(max_age_hours)
    ents = _sitemap_entries("https://www.remoterocketship.com/sitemap_job_openings_in.xml")
    pick = [(u, lm) for u, lm in ents
            if _age_ok(lm, win)
            and re.search(r"/jobs/[^/]*(?:backend|back-end|python|node|software|sde|full-?stack|ai-|llm|ml-|developer|engineer)", u, re.I)
            and not _BAD_TITLE.search(u.split("/jobs/")[-1].replace("-", " "))]
    pick.sort(key=lambda x: x[1], reverse=True)
    rows = []
    for u, lm in pick[:CAPS["remoterocketship"]]:
        page = _get(u)
        time.sleep(_SLEEP)
        nd = _next_data(page.text) if page is not None else None
        jo = ((nd or {}).get("props", {}).get("pageProps", {}) or {}).get("jobOpening")
        if not jo:
            continue
        title = jo.get("roleTitle") or ""
        if not _DEV.search(title) or _BAD_TITLE.search(title) or jo.get("dateDeleted"):   # site seniority flags are unreliable; jd_screener reads the real years
            continue
        try:                                          # the site's own ghost-job score: skip clear ghosts
            if float(jo.get("ghostScore") or 0) >= 70:
                continue
        except (TypeError, ValueError):
            pass
        created = jo.get("created_at", "")
        if not _age_ok(created, win):
            continue
        sal = jo.get("salaryRange")
        sal_line = f"Salary: {sal}." if sal else ""
        desc = "\n".join(x for x in (
            _years_line(months=jo.get("experienceRequirementsMonthsOfExperience")), sal_line,
            _strip(jo.get("roleDescription")), "Requirements:\n" + _strip(jo.get("roleRequirements"))
            if jo.get("roleRequirements") else "",
            "Stack: " + ", ".join(jo.get("techStack") or [])) if x)
        rows.append({
            "title": title, "company": (jo.get("company") or {}).get("name", ""),
            "location": jo.get("location") or "India (remote)", "site": "remoterocketship",
            "date_posted": str(created)[:10], "is_remote": True,
            "job_url": jo.get("url") or u, "description": desc,
        })
    return rows


# --------------------------------------------------------------------------- #
# Wellfound (server-rendered role pages)
# --------------------------------------------------------------------------- #
_WF_ROLES = ["backend-engineer", "software-engineer", "full-stack-engineer", "python-developer",
             "machine-learning-engineer", "node-js-developer"]


def fetch_wellfound(terms, max_age_hours=0):
    win = _window(max_age_hours)
    rows, seen = [], set()
    for role in _WF_ROLES:
        page = _get(f"https://wellfound.com/role/l/{role}/india")
        time.sleep(_SLEEP)
        nd = _next_data(page.text) if page is not None else None
        ap = (((nd or {}).get("props", {}).get("pageProps", {}) or {}).get("apolloState", {}) or {}).get("data", {})
        if not ap:
            continue
        owner = {}
        for k, v in ap.items():
            if k.startswith("StartupResult"):
                for ref in v.get("highlightedJobListings") or []:
                    owner[(ref or {}).get("__ref", "")] = v
        for k, v in ap.items():
            if not k.startswith("JobListingSearchResult"):
                continue
            title = v.get("title") or ""
            jid = str(v.get("id") or k.split(":")[-1])
            if jid in seen or not _DEV.search(title) or _BAD_TITLE.search(title):
                continue
            posted = ""
            try:
                posted = dt.datetime.fromtimestamp(int(v.get("liveStartAt")), dt.timezone.utc).isoformat()
            except (TypeError, ValueError):
                pass
            if posted and not _age_ok(posted, win):
                continue
            seen.add(jid)
            st = owner.get(k) or {}
            comp = v.get("compensation") or ""
            desc = "\n".join(x for x in (
                _years_line(lo=v.get("yearsExperienceMin"), hi=v.get("yearsExperienceMax")),
                f"Compensation: {comp}" if comp else "", _strip(v.get("description"))) if x)
            locs = v.get("locationNames") or []
            rows.append({
                "title": title, "company": st.get("name", ""),
                "location": ", ".join(locs) or "India", "site": "wellfound",
                "date_posted": posted[:10], "is_remote": bool(v.get("remote")),
                "job_url": f"https://wellfound.com/jobs/{jid}-{v.get('slug') or 'job'}",
                "description": desc,
                "company_num_employees": {"SIZE_1_10": "1-10", "SIZE_11_50": "11-50", "SIZE_51_200": "51-200",
                                          "SIZE_201_500": "201-500"}.get(st.get("companySize"), ""),
            })
    return rows


# --------------------------------------------------------------------------- #
# Y Combinator â€” Work at a Startup
# --------------------------------------------------------------------------- #
_YC_ROLES = ["software-engineer", "backend-engineer", "full-stack-engineer", "machine-learning-engineer"]


def _lpa_from_yc(rng):
    """'â‚¹1M - â‚¹2.5M INR' -> 'Salary: 10-25 LPA.' (1M rupees = 10 lakh)."""
    m = re.findall(r"â‚¹\s*([\d.]+)\s*([MK]?)", rng or "")
    if len(m) < 1:
        return f"Salary: {rng}." if rng else ""
    vals = []
    for n, u in m[:2]:
        v = float(n) * {"M": 1e6, "K": 1e3}.get(u, 1)
        vals.append(v / 1e5)
    return f"Salary: {min(vals):.1f}-{max(vals):.1f} LPA."


def fetch_yc(terms, max_age_hours=0):
    links, seen = [], set()
    pages = ["https://www.ycombinator.com/jobs/location/india", "https://www.ycombinator.com/jobs/location/remote"]
    pages += [f"https://www.ycombinator.com/jobs/role/{role}" for role in _YC_ROLES]
    for purl in pages:
        page = _get(purl)
        time.sleep(_SLEEP)
        if page is None:
            continue
        for l in re.findall(r'href="(/companies/[^"/]+/jobs/[^"]+)"', page.text):
            if l not in seen and not _BAD_TITLE.search(l.split("/jobs/")[-1].replace("-", " ")):
                seen.add(l); links.append(l)
    rows = []
    for l in links[:CAPS["yc"] * 3]:
        if len(rows) >= CAPS["yc"]:
            break
        page = _get("https://www.ycombinator.com" + l)
        time.sleep(_SLEEP)
        if page is None:
            continue
        m = re.search(r'data-page="([^"]+)"', page.text)
        try:
            props = json.loads(html.unescape(m.group(1)))["props"] if m else {}
        except Exception:
            continue
        jb = props.get("job") or {}
        title = jb.get("title") or ""
        loc = jb.get("location") or ""
        if not title or not _DEV.search(title) or _BAD_TITLE.search(title):
            continue
        # createdAt is relative ("3 days", "about 2 months"): keep only recent postings
        if not re.search(r"hour|day|week|less than|about 1 month", str(jb.get("createdAt") or ""), re.I):
            continue
        desc = "\n".join(x for x in (
            f"Experience: {jb.get('minExperience')} required." if jb.get("minExperience") else "",
            _lpa_from_yc(jb.get("salaryRange")), _strip(jb.get("description")),
            "Skills: " + ", ".join(jb.get("skills") or [])) if x)
        if not JDS.geo_ok(loc, desc) or re.search(r"US citizen|visa only", str(jb.get("visa") or ""), re.I) \
                and not JDS._INDIA_TOK.search(loc):
            continue
        rows.append({
            "title": title, "company": (props.get("company") or {}).get("name", jb.get("companyName", "")),
            "location": loc.split(" / ")[0] or "Remote", "site": "ycombinator (Work at a Startup)",
            "date_posted": dt.date.today().isoformat(), "is_remote": "remote" in loc.lower(),
            "job_url": "https://www.ycombinator.com" + (jb.get("url") or l), "description": desc,
            "company_num_employees": "1-50",
        })
    return rows


# --------------------------------------------------------------------------- #
# Reddit r/developersIndia (hiring / referral posts)
# --------------------------------------------------------------------------- #
def fetch_reddit(terms, max_age_hours=0):
    win = _window(max_age_hours)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    rows, seen = [], set()
    for q in ("hiring", "opening backend", "referral"):
        r = _get("https://www.reddit.com/r/developersIndia/search.rss",
                 params={"q": q, "restrict_sr": 1, "sort": "new", "t": "month"})
        time.sleep(_SLEEP)
        if r is None:
            continue
        try:
            root = ET.fromstring(r.content)
        except Exception:
            continue
        for e in root.findall("a:entry", ns):
            title = (e.findtext("a:title", "", ns) or "").strip()
            link = e.find("a:link", ns)
            url = link.get("href") if link is not None else ""
            upd = e.findtext("a:updated", "", ns)
            body = _strip(html.unescape(e.findtext("a:content", "", ns) or ""))
            if (not url or url in seen or not _age_ok(upd, win)
                    or not re.search(r"\b(hiring|openings?|vacanc\w+|referrals?)\b", title, re.I)
                    or re.search(r"looking\s+for\s+(?:a\s+)?(?:job|opportunit|role|work|referral|internship)|"
                                 r"\b(?:fresher|grad|batch|resume\s+review|roast)\b", title, re.I)
                    or not _DEV.search(title + " " + body[:300]) or _BAD_TITLE.search(title)):
                continue
            seen.add(url)
            rows.append({
                "title": re.sub(r"^\s*\[?(hiring|referral)\]?[:\- ]*", "", title, flags=re.I)[:120] or title,
                "company": "", "location": "India", "site": "reddit r/developersIndia",
                "date_posted": str(upd)[:10], "is_remote": "remote" in (title + body[:300]).lower(),
                "job_url": url, "description": body[:4000],
            })
    return rows


def fetch_all(terms, max_age_hours=0):
    """Run every portal in parallel threads. Returns (rows, per-source counts)."""
    jobs = {
        "instahyre": fetch_instahyre, "cutshort": fetch_cutshort,
        "remoterocketship": fetch_remoterocketship, "wellfound": fetch_wellfound,
        "yc": fetch_yc, "reddit": fetch_reddit,
    }
    out, counts = [], {}

    def run(name):
        try:
            return name, jobs[name](terms, max_age_hours)
        except Exception as e:
            print(f"  ! {name} failed: {e}", flush=True)
            return name, []

    with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        for name, rows in ex.map(run, list(jobs)):
            counts[name] = len(rows)
            out += rows
    return out, counts
