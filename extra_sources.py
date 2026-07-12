"""
Extra job sources beyond python-jobspy.
=======================================

python-jobspy only covers a fixed set of boards (LinkedIn/Indeed/Google/etc.),
and several of them block datacenter/home IPs. This module adds more *real,
directly-posted* listings from free public APIs that don't need a key:

  * Remotive  (https://remotive.com/api/remote-jobs) — curated remote roles at
    startups and established companies; supports a search term.
  * RemoteOK  (https://remoteok.com/api) — large remote board; we filter to
    software roles client-side.
  * Jobicy / Arbeitnow — more free remote-job APIs.

DIRECT COMPANY CAREER PAGES (scrape_career_pages):
    Most companies' "careers" pages (careers.google.com, amazon.jobs, etc.) are
    JavaScript apps that serve NO jobs to a plain HTTP GET — scraping those URLs
    returns nothing. What actually works for free, no-auth, no-JS is the ATS
    (applicant-tracking-system) JSON APIs those pages load their data from:

      * Greenhouse  boards-api.greenhouse.io/v1/boards/{slug}/jobs
      * Lever       api.lever.co/v0/postings/{slug}?mode=json
      * Ashby       api.ashbyhq.com/posting-api/job-board/{slug}

    COMPANY_CAREER_PAGES below maps ~50 companies (incl. Indian ones — PhonePe,
    Groww, Slice, Postman) to their ATS slug. Every slug here was live-validated
    to return jobs; unknown/closed boards 404 and are skipped silently. Also:

      * Hacker News "Who is Hiring?"  — current monthly thread via the Algolia +
        Firebase HN APIs (real, free).
      * We Work Remotely              — public RSS feed.
      * LinkedIn (public "guest")     — the no-login jobs-guest HTML fragment
        endpoint (rate-limited/fragile; best-effort).
      * Tavily ATS fallback           — site:boards.greenhouse.io OR
        site:jobs.lever.co … to discover the thousands of startups NOT in the
        registry (needs TAVILY_API_KEY).

Every row is mapped to the same shape app.py already scores
(title/company/location/site/date_posted/is_remote/job_url/description), so they
merge straight into the one ranked list.

All of this is best-effort and resilient: rate-limited to ~1 req/sec per domain,
at most 2 concurrent requests, results cached for 1 hour, and any source that is
down / rate-limited / CAPTCHA-walled just returns [] and never aborts the run.
No paid APIs.
"""

import os
import re
import html
import time
import threading
import datetime as dt
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus, urlparse
from urllib import robotparser
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

_UA = {"User-Agent": "Mozilla/5.0 (compatible; job-fetch-agent/1.0)"}
_TIMEOUT = 20

# Tokens that mark a listing as a software/engineering role (used to filter the
# unsearchable RemoteOK feed down to relevant jobs).
_DEV_TOKENS = (
    "backend", "back end", "back-end", "frontend", "front end", "full stack",
    "fullstack", "software", "developer", "engineer", "sde", "node", "nestjs",
    "java", "python", "golang", " go ", "react", "angular", "spring", "fastapi",
    "api", "devops", "typescript", "javascript", "php", "ruby", ".net",
)


def _strip_html(s: str) -> str:
    """Remotive/RemoteOK descriptions are HTML; turn them into plain text."""
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</p>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _within_age(date_str: str, max_age_hours: int) -> bool:
    """True if date_str (ISO-ish) is within max_age_hours. Unknown dates pass."""
    if not date_str or not max_age_hours:
        return True
    raw = str(date_str).strip().replace("Z", "+00:00")
    for parse in (
        lambda x: dt.datetime.fromisoformat(x),
        lambda x: dt.datetime.fromisoformat(x[:19]),
        lambda x: dt.datetime.strptime(x[:10], "%Y-%m-%d"),
    ):
        try:
            d = parse(raw)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
            age = dt.datetime.now(dt.timezone.utc) - d
            return age <= dt.timedelta(hours=max_age_hours)
        except Exception:
            continue
    return True  # couldn't parse -> don't drop it


def fetch_remotive(terms, per_term=20, max_age_hours=0):
    """Search Remotive for each term and return mapped rows."""
    rows = []
    for term in terms:
        try:
            r = requests.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": term, "limit": per_term},
                headers=_UA, timeout=_TIMEOUT,
            )
            r.raise_for_status()
            jobs = r.json().get("jobs", [])
        except Exception as e:
            print(f"  ! remotive {term!r} failed: {e}", flush=True)
            continue
        for j in jobs:
            date_posted = (j.get("publication_date") or "")[:10]
            if not _within_age(j.get("publication_date", ""), max_age_hours):
                continue
            rows.append({
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": j.get("candidate_required_location") or "Remote",
                "site": "remotive",
                "date_posted": date_posted,
                "is_remote": True,
                "job_url": j.get("url", ""),
                "description": _strip_html(j.get("description", "")),
            })
    return rows


def fetch_remoteok(terms, max_age_hours=0):
    """Pull RemoteOK's feed and keep software roles relevant to the terms."""
    try:
        r = requests.get("https://remoteok.com/api", headers=_UA, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"  ! remoteok failed: {e}", flush=True)
        return []

    rows = []
    for j in data:
        if not isinstance(j, dict) or not j.get("position"):
            continue  # first element is a legal/notice object
        haystack = (str(j.get("position", "")) + " "
                    + " ".join(j.get("tags", []) or [])).lower()
        if not any(tok in haystack for tok in _DEV_TOKENS):
            continue
        date_posted = (str(j.get("date", "")) or "")[:10]
        if not _within_age(j.get("date", ""), max_age_hours):
            continue
        rows.append({
            "title": j.get("position", ""),
            "company": j.get("company", ""),
            "location": j.get("location") or "Remote",
            "site": "remoteok",
            "date_posted": date_posted,
            "is_remote": True,
            "job_url": j.get("url") or j.get("apply_url") or "",
            "description": _strip_html(j.get("description", "")),
        })
    return rows


def fetch_jobicy(terms, per_term=20, max_age_hours=0):
    """Jobicy — free remote-jobs API. Searched per term via the `tag` param."""
    rows, seen = [], set()
    for term in terms:
        tag = term.lower().split()[0] if term.strip() else ""
        try:
            r = requests.get("https://jobicy.com/api/v2/remote-jobs",
                             params={"count": per_term, "tag": tag},
                             headers=_UA, timeout=_TIMEOUT)
            r.raise_for_status()
            jobs = r.json().get("jobs", [])
        except Exception as e:
            print(f"  ! jobicy {term!r} failed: {e}", flush=True)
            continue
        for j in jobs:
            url = j.get("url", "")
            if not url or url in seen:
                continue
            date = j.get("pubDate") or j.get("date") or ""
            if not _within_age(date, max_age_hours):
                continue
            seen.add(url)
            rows.append({
                "title": j.get("jobTitle", ""),
                "company": j.get("companyName", ""),
                "location": j.get("jobGeo") or "Remote",
                "site": "jobicy",
                "date_posted": str(date)[:10],
                "is_remote": True,
                "job_url": url,
                "description": _strip_html(j.get("jobDescription") or j.get("jobExcerpt", "")),
            })
    return rows


def fetch_arbeitnow(terms, max_age_hours=0):
    """Arbeitnow — free job-board API (global + remote). Filtered to dev roles."""
    try:
        r = requests.get("https://www.arbeitnow.com/api/job-board-api",
                         headers=_UA, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as e:
        print(f"  ! arbeitnow failed: {e}", flush=True)
        return []
    rows = []
    for j in data:
        haystack = (str(j.get("title", "")) + " "
                    + " ".join(j.get("tags", []) or [])).lower()
        if not any(tok in haystack for tok in _DEV_TOKENS):
            continue
        epoch = j.get("created_at")
        date_iso = ""
        try:
            date_iso = dt.datetime.utcfromtimestamp(int(epoch)).isoformat()
        except Exception:
            pass
        if date_iso and not _within_age(date_iso, max_age_hours):
            continue
        rows.append({
            "title": j.get("title", ""),
            "company": j.get("company_name", ""),
            "location": j.get("location") or ("Remote" if j.get("remote") else ""),
            "site": "arbeitnow",
            "date_posted": date_iso[:10],
            "is_remote": bool(j.get("remote")),
            "job_url": j.get("url", ""),
            "description": _strip_html(j.get("description", "")),
        })
    return rows


def fetch_himalayas(terms, max_age_hours=0):
    """Himalayas — free, no-auth remote-jobs API (https://himalayas.app/api).
    Filtered to dev roles; parsed defensively so a schema change just yields []."""
    try:
        r = requests.get("https://himalayas.app/jobs/api",
                         params={"limit": 100},
                         headers=_UA, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        jobs = data.get("jobs") or data.get("data") or []
    except Exception as e:
        print(f"  ! himalayas failed: {e}", flush=True)
        return []
    rows = []
    for j in jobs:
        title = j.get("title") or ""
        company = j.get("companyName") or j.get("company_name") or ""
        haystack = title.lower()
        if not any(tok in haystack for tok in _DEV_TOKENS):
            continue
        # Prefer junior/mid roles; keep ones with unknown seniority too.
        sen = j.get("seniority") or []
        if isinstance(sen, str):
            sen = [sen]
        sen_l = " ".join(str(s).lower() for s in sen)
        if sen_l and not any(k in sen_l for k in ("junior", "mid", "entry", "associate")):
            if any(k in sen_l for k in ("senior", "lead", "principal", "staff", "director")):
                continue                                  # skip clearly-senior remote roles
        # Date: pubDate/publishedDate as unix epoch or ISO string.
        raw = j.get("pubDate") or j.get("publishedDate") or j.get("date") or ""
        date_iso = ""
        try:
            date_iso = dt.datetime.utcfromtimestamp(int(raw)).isoformat()
        except (TypeError, ValueError):
            date_iso = str(raw)
        if date_iso and not _within_age(date_iso, max_age_hours):
            continue
        url = j.get("applicationLink") or j.get("guid") or j.get("url") or ""
        if not url:
            continue
        locs = j.get("locationRestrictions") or []
        location = ", ".join(str(x) for x in locs) if isinstance(locs, list) and locs else "Remote"
        rows.append({
            "title": title,
            "company": company or "",
            "location": location,
            "site": "himalayas",
            "date_posted": date_iso[:10],
            "is_remote": True,
            "job_url": url,
            "description": _strip_html(j.get("description") or j.get("excerpt") or ""),
        })
    return rows


# Domains that are actual job postings (used to filter Tavily web results).
_JOB_DOMAINS = (
    "linkedin.com/jobs", "indeed.", "glassdoor.", "naukri.com", "lever.co",
    "greenhouse.io", "ashbyhq.com", "myworkdayjobs.com", "workday", "wellfound.com",
    "angel.co", "remoteok", "weworkremotely.com", "remotive.com", "jobicy.com",
    "ziprecruiter.com", "dice.com", "monster.com", "instahyre.com", "cutshort.io",
    "hirist.", "ycombinator.com/jobs", "/careers", "careers.", "jobs.", "smartrecruiters.com",
    "workable.com", "recruitee.com", "jobvite.com", "bamboohr.com",
)


def fetch_tavily(terms, max_results=5, max_age_hours=0):
    """Fallback search via Tavily (AI web-search API). Needs a free API key in
    env TAVILY_API_KEY — returns [] (and a one-time note) if it isn't set. Web
    results are filtered to real job-posting domains and mapped to job rows."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        print("  (Tavily fallback skipped: set TAVILY_API_KEY to enable)", flush=True)
        return []
    rows, seen = [], set()
    for term in terms:
        try:
            r = requests.post("https://api.tavily.com/search", json={
                "api_key": key,
                "query": f"{term} job openings apply",
                "max_results": max_results,
                "search_depth": "basic",
            }, headers=_UA, timeout=_TIMEOUT)
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception as e:
            print(f"  ! tavily {term!r} failed: {e}", flush=True)
            continue
        for res in results:
            url = res.get("url", "")
            if not url or url in seen:
                continue
            if not any(d in url.lower() for d in _JOB_DOMAINS):
                continue
            seen.add(url)
            title, company = res.get("title", ""), ""
            for sep in (" - ", " at ", " | ", " – "):
                if sep in title:
                    bits = title.split(sep)
                    title, company = bits[0].strip(), bits[1].strip()
                    break
            content = res.get("content", "")
            rows.append({
                "title": title,
                "company": company,
                "location": "",
                "site": "tavily",
                "date_posted": "",
                "is_remote": "remote" in (title + " " + content).lower(),
                "job_url": url,
                "description": content,
            })
    return rows


# =========================================================================== #
# DIRECT COMPANY CAREER PAGES (via ATS JSON APIs) + more free sources
# =========================================================================== #
# company display name -> ATS board slug. Every slug below was live-validated to
# return jobs (see the module docstring). To add a company, find its ATS board
# slug; a wrong/closed slug simply 404s and is skipped silently.
GREENHOUSE_BOARDS = {
    "Databricks": "databricks", "Stripe": "stripe", "MongoDB": "mongodb",
    "Datadog": "datadog", "Anthropic": "anthropic", "Samsara": "samsara",
    "Brex": "brex", "Airbnb": "airbnb", "Elastic": "elastic",
    "Cloudflare": "cloudflare", "Pinterest": "pinterest", "Twilio": "twilio",
    "Figma": "figma", "Instacart": "instacart", "Reddit": "reddit",
    "Affirm": "affirm", "Robinhood": "robinhood", "GitLab": "gitlab",
    "Asana": "asana", "Lyft": "lyft", "Postman": "postman",
    "Flexport": "flexport", "Coinbase": "coinbase", "SoFi": "sofi",
    "Gusto": "gusto", "Slice": "slice", "PhonePe": "phonepe",
    "Discord": "discord", "Dropbox": "dropbox", "Twitch": "twitch",
    "Airtable": "airtable", "Groww": "groww",
}
LEVER_BOARDS = {
    "Palantir": "palantir", "Mistral AI": "mistral", "Spotify": "spotify",
}
ASHBY_BOARDS = {
    "OpenAI": "openai", "ElevenLabs": "elevenlabs", "Notion": "notion",
    "Cohere": "cohere", "Ramp": "ramp", "Cursor": "cursor", "Replit": "replit",
    "Perplexity": "perplexity", "Supabase": "supabase", "Linear": "linear",
    "Render": "render", "PostHog": "posthog", "Mux": "mux",
}
# Kept for reference / the UI label "via {company} careers". The big-tech vanity
# pages (Google/Amazon/Meta/Apple/Netflix) are JS apps with no jobs in the raw
# HTML — they are reachable only through the Tavily ATS fallback, not direct GET.
COMPANY_CAREER_PAGES = {**{k: f"greenhouse:{v}" for k, v in GREENHOUSE_BOARDS.items()},
                        **{k: f"lever:{v}" for k, v in LEVER_BOARDS.items()},
                        **{k: f"ashby:{v}" for k, v in ASHBY_BOARDS.items()}}

# Companies that DON'T expose a public ATS board (Greenhouse/Lever/Ashby/Workable/
# Recruitee all return nothing) and whose own careers site is a JS app a plain GET
# can't read. We still surface their roles via a company-targeted Tavily web search
# (needs TAVILY_API_KEY). company -> careers domain to restrict the search to.
# (PhonePe IS on Greenhouse, so it lives in GREENHOUSE_BOARDS above, not here.)
COMPANY_CAREER_SEARCH = {
    "Razorpay": "razorpay.com",
    "Zerodha": "zerodha.com",
}

# --- rate limiting (per-domain) + 1-hour cache + robots.txt ----------------- #
_LOCKS_GUARD = threading.Lock()
_HOST_LOCKS = {}
_LAST_HIT = {}
# Politeness is enforced PER DOMAIN (a given server is never hit faster than its
# interval). The global worker count only controls how many DIFFERENT domains we
# talk to at once — a strict 2 made 48 boards take ~100s, so we allow more
# parallelism across domains while keeping the per-domain rate limit strict.
_API_INTERVAL = 0.25         # documented public JSON APIs: gentle per-host spacing
_SCRAPE_INTERVAL = 1.0       # HTML scraping: 1 req/sec per domain (per spec)
_CAREER_WORKERS = 6          # concurrent DISTINCT-domain requests
_CACHE = {}
_CACHE_TTL = 3600            # 1 hour (per spec)
_ROBOTS = {}


def _host_lock(host):
    with _LOCKS_GUARD:
        return _HOST_LOCKS.setdefault(host, threading.Lock())


def _get(url, min_interval=_SCRAPE_INTERVAL, timeout=_TIMEOUT, headers=None):
    """GET with per-domain throttling. Serialises requests to the SAME host
    `min_interval` seconds apart; different hosts run concurrently."""
    host = urlparse(url).netloc
    with _host_lock(host):
        wait = min_interval - (time.time() - _LAST_HIT.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        try:
            return requests.get(url, headers=headers or _UA, timeout=timeout)
        finally:
            _LAST_HIT[host] = time.time()


def _robots_ok(url):
    """Best-effort robots.txt check for HTML scraping (fails OPEN if robots can't
    be fetched). Public JSON APIs (greenhouse/lever/ashby/HN) are not run through
    this — they are documented APIs, not crawl targets."""
    try:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        rp = _ROBOTS.get(base)
        if rp is None:
            rp = robotparser.RobotFileParser()
            try:
                rr = requests.get(base + "/robots.txt", headers=_UA, timeout=8)
                rp.parse(rr.text.splitlines() if rr.status_code == 200 else [])
            except Exception:
                rp.allow_all = True
            _ROBOTS[base] = rp
        return rp.can_fetch(_UA["User-Agent"], url)
    except Exception:
        return True


def _cache_get(key):
    v = _CACHE.get(key)
    if v and (time.time() - v[0]) < _CACHE_TTL:
        return v[1]
    return None


def _cache_put(key, value):
    _CACHE[key] = (time.time(), value)


_KW_STOP = {"developer", "engineer", "engineering", "the", "and", "for", "with",
            "senior", "junior", "lead", "sde", "dev"}


def _kw_tokens(keywords):
    """Significant search tokens from the keyword phrases — e.g.
    ['Backend Developer','Node.js','TypeScript'] -> {'backend','node','typescript'}.
    Generic words ('developer'/'engineer') are dropped so they don't match every
    posting; this lets 'backend' match a title like 'Backend Engineer, Payments'."""
    toks = set()
    for k in keywords or []:
        for t in re.split(r"[^a-z0-9+#]+", (k or "").lower()):
            if len(t) >= 3 and t not in _KW_STOP:
                toks.add(t)
    return toks


def _kw_match(text, keywords):
    """True if any significant keyword token appears in text (or no keywords).
    Token-based so short titles still match (substring phrase matching missed
    almost everything when only a job title was available)."""
    toks = _kw_tokens(keywords)
    if not toks:
        return True
    low = (text or "").lower()
    return any(t in low for t in toks)


_SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|director|head\b|vp\b|architect|manager)\b", re.I)


def _level_ok(title, experience_level):
    """Light seniority filter: for a JUNIOR profile, drop senior-titled roles
    (the main app scorer enforces this too — this just trims obvious noise)."""
    if experience_level == "JUNIOR" and _SENIOR_TITLE.search(title or ""):
        return False
    return True


# --- ATS fetchers (one company each) --------------------------------------- #
def _fetch_greenhouse(company, slug, keywords, max_age_hours):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    try:
        r = _get(url, min_interval=_API_INTERVAL)
        if r.status_code != 200:
            return []
        jobs = r.json().get("jobs", [])
    except Exception:
        return []
    rows = []
    for j in jobs:
        title = j.get("title", "")
        if not _kw_match(title, keywords):
            continue
        loc = (j.get("location") or {}).get("name", "") or ""
        if not _within_age(j.get("updated_at", ""), max_age_hours):
            continue
        rows.append({
            "title": title, "company": company,
            "location": loc or "—", "site": f"{company} careers (Greenhouse)",
            "date_posted": str(j.get("updated_at", ""))[:10],
            "is_remote": "remote" in (title + " " + loc).lower(),
            "job_url": j.get("absolute_url", ""),
            "description": f"{title} at {company}. {loc}".strip(),
        })
    return rows


def _fetch_lever(company, slug, keywords, max_age_hours):
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = _get(url, min_interval=_API_INTERVAL)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []
    rows = []
    for j in (data if isinstance(data, list) else []):
        title = j.get("text", "")
        cats = j.get("categories") or {}
        loc = cats.get("location", "") or ""
        desc = (j.get("descriptionPlain") or "")[:1500]
        if not _kw_match(f"{title} {desc}", keywords):
            continue
        created = j.get("createdAt")
        iso = ""
        try:
            iso = dt.datetime.utcfromtimestamp(int(created) / 1000).isoformat()
        except Exception:
            pass
        if iso and not _within_age(iso, max_age_hours):
            continue
        rows.append({
            "title": title, "company": company,
            "location": loc or cats.get("team", "") or "—",
            "site": f"{company} careers (Lever)", "date_posted": iso[:10],
            "is_remote": "remote" in (title + " " + loc).lower(),
            "job_url": j.get("hostedUrl", ""),
            "description": desc or f"{title} at {company}",
        })
    return rows


def _fetch_ashby(company, slug, keywords, max_age_hours):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        r = _get(url, min_interval=_API_INTERVAL)
        if r.status_code != 200:
            return []
        jobs = r.json().get("jobs", [])
    except Exception:
        return []
    rows = []
    for j in jobs:
        title = j.get("title", "")
        loc = j.get("location", "") or ""
        desc = (j.get("descriptionPlain") or "")[:1500]
        if not _kw_match(f"{title} {desc}", keywords):
            continue
        if not _within_age(j.get("publishedAt", ""), max_age_hours):
            continue
        # Prefer the canonical posting URL; fall back to applyUrl, then build the
        # public job-board URL from the id so the link never lands on a 404.
        job_url = j.get("jobUrl") or j.get("applyUrl") or ""
        if not job_url and j.get("id"):
            job_url = f"https://jobs.ashbyhq.com/{slug}/{j['id']}"
        if not job_url:
            continue                                  # no usable link -> skip
        rows.append({
            "title": title, "company": company,
            "location": loc or "—", "site": f"{company} careers (Ashby)",
            "date_posted": str(j.get("publishedAt", ""))[:10],
            "is_remote": bool(j.get("isRemote")) or "remote" in (title + " " + loc).lower(),
            "job_url": job_url,
            "description": desc or f"{title} at {company}",
        })
    return rows


# --- Hacker News "Who is Hiring?" ------------------------------------------ #
def fetch_hackernews(keywords, max_age_hours=0, max_posts=80):
    """Parse the current monthly 'Ask HN: Who is hiring?' thread (Algolia finds
    the thread; the comments ARE the job posts). Real, free, no key."""
    try:
        s = _get("https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring"
                 "&query=hiring&hitsPerPage=5", min_interval=_API_INTERVAL)
        hits = [h for h in s.json().get("hits", [])
                if "who is hiring" in (h.get("title", "").lower())]
        if not hits:
            return []
        story_id = hits[0]["objectID"]
        item = _get(f"https://hn.algolia.com/api/v1/items/{story_id}",
                    min_interval=_API_INTERVAL, timeout=15)
        children = item.json().get("children", [])
    except Exception as e:
        print(f"  ! hackernews failed: {e}", flush=True)
        return []
    rows = []
    for c in children[:max_posts]:
        raw = c.get("text") or ""
        if not raw:
            continue
        text = _strip_html(raw)
        if not text or not _kw_match(text, keywords):
            continue
        first = re.split(r"\n|<p>", raw, 1)[0]
        title = _strip_html(first)[:140] or text[:140]
        # HN stores comment HTML with entities (&#x2F; -> /, &amp; -> &), so the
        # raw href reads like "https:&#x2F;&#x2F;kadoa.com" — unescape it to a real URL.
        m = re.search(r'href="([^"]+)"', raw)
        url = html.unescape(m.group(1)) if m else f"https://news.ycombinator.com/item?id={c.get('id')}"
        rows.append({
            "title": title, "company": "(HN Who's Hiring)",
            "location": "—", "site": "Hacker News",
            "date_posted": "", "is_remote": "remote" in text.lower(),
            "job_url": url, "description": text[:1500],
        })
    return rows


# --- We Work Remotely (public RSS) ----------------------------------------- #
def fetch_weworkremotely(keywords, max_age_hours=0):
    url = "https://weworkremotely.com/remote-jobs.rss"
    if not _robots_ok(url):
        return []
    try:
        r = _get(url, min_interval=_SCRAPE_INTERVAL)
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"  ! weworkremotely failed: {e}", flush=True)
        return []
    rows = []
    for item in root.iter("item"):
        def _t(tag):
            el = item.find(tag)
            return (el.text or "") if el is not None else ""
        raw_title = _t("title")
        company, _, role = raw_title.partition(":")
        role = role.strip() or raw_title
        region = _t("region")
        if not _kw_match(f"{raw_title} {_t('category')}", keywords):
            continue
        rows.append({
            "title": role, "company": company.strip() or "—",
            "location": region or "Remote", "site": "WeWorkRemotely",
            "date_posted": _t("pubDate")[:16],
            "is_remote": True, "job_url": _t("link"),
            "description": _strip_html(_t("description"))[:1500] or role,
        })
    return rows


# --- LinkedIn public "guest" listings (no login) --------------------------- #
def fetch_linkedin_public(keywords, location="", max_age_hours=0, limit=25):
    """LinkedIn's no-auth jobs-guest fragment endpoint. Real public listings, but
    rate-limited and fragile (often 429) — best-effort, returns [] on any block.
    Note: jobspy already scrapes LinkedIn; this is a light supplement."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []
    query = " ".join(list(keywords)[:3]) if keywords else "software developer"
    url = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
           f"?keywords={quote_plus(query)}&location={quote_plus(location or 'India')}&start=0")
    try:
        r = _get(url, min_interval=_SCRAPE_INTERVAL)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  ! linkedin public failed: {e}", flush=True)
        return []
    rows = []
    for card in soup.select("li")[:limit]:
        title_el = card.select_one(".base-search-card__title")
        comp_el = card.select_one(".base-search-card__subtitle")
        loc_el = card.select_one(".job-search-card__location")
        link_el = card.select_one("a.base-card__full-link") or card.select_one("a[href]")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title or not link_el:
            continue
        loc = loc_el.get_text(strip=True) if loc_el else ""
        rows.append({
            "title": title,
            "company": comp_el.get_text(strip=True) if comp_el else "",
            "location": loc or location or "—", "site": "LinkedIn (public)",
            "date_posted": "", "is_remote": "remote" in (title + " " + loc).lower(),
            "job_url": (link_el.get("href") or "").split("?")[0],
            "description": title,
        })
    return rows


# --- Tavily ATS fallback (discovers startups NOT in the registry) ---------- #
def fetch_tavily_ats(terms, location="", max_results=5, max_age_hours=0):
    """Use Tavily to search Greenhouse/Lever/Ashby/Workable-hosted boards for the
    thousands of companies not in our registry. Needs TAVILY_API_KEY."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return []
    sites = ("site:boards.greenhouse.io OR site:jobs.lever.co OR "
             "site:jobs.ashbyhq.com OR site:apply.workable.com")
    rows, seen = [], set()
    for term in list(terms)[:3]:
        q = f"{term} {location} ({sites})".strip()
        try:
            r = requests.post("https://api.tavily.com/search", json={
                "api_key": key, "query": q, "max_results": max_results,
                "search_depth": "basic",
            }, headers=_UA, timeout=_TIMEOUT)
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception as e:
            print(f"  ! tavily-ats {term!r} failed: {e}", flush=True)
            continue
        for res in results:
            url = res.get("url", "")
            if not url or url in seen:
                continue
            if not any(d in url.lower() for d in
                       ("greenhouse.io", "lever.co", "ashbyhq.com", "workable.com")):
                continue
            seen.add(url)
            title = res.get("title", "")
            company = ""
            for sep in (" - ", " at ", " | ", " – "):
                if sep in title:
                    title, company = title.split(sep)[0].strip(), title.split(sep)[1].strip()
                    break
            rows.append({
                "title": title, "company": company, "location": location or "",
                "site": "Career page (via Tavily)", "date_posted": "",
                "is_remote": "remote" in (title + " " + res.get("content", "")).lower(),
                "job_url": url, "description": res.get("content", ""),
            })
    return rows


def fetch_linkedin_hiring_posts(terms, location="", max_results=12, max_age_hours=0):
    """Recent LinkedIn *posts* — the 'we're hiring for X' / 'DM me' posts that HRs,
    recruiters and employees write, NOT the jobs board (board listings are often
    stale; these posts are fresh and name a live opening with a direct contact).
    LinkedIn blocks scraping its feed and it's against their ToS, so we go through
    public web search (Tavily) for indexed linkedin.com/posts URLs. Best-effort:
    needs TAVILY_API_KEY and only finds what's publicly indexed.

    Returns job-shaped rows; the post URL is the apply/contact link."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return []
    rows, seen = [], set()
    # More terms + a richer hiring-intent query = more HR/recruiter/employee posts.
    # topic=general (not news — LinkedIn posts are rarely indexed as news) with a
    # recent time window is what actually surfaces these posts.
    for term in list(terms)[:4]:
        q = (f'({term}) ("we are hiring" OR "we\'re hiring" OR "now hiring" OR '
             f'"hiring for" OR "immediate hiring" OR "open position" OR '
             f'"open role" OR "join our team" OR "DM me" OR "share your resume") '
             f'{location} site:linkedin.com/posts').strip()
        try:
            r = requests.post("https://api.tavily.com/search", json={
                "api_key": key, "query": q, "max_results": max_results,
                "search_depth": "basic", "time_range": "month",
                "include_domains": ["linkedin.com"],
            }, headers=_UA, timeout=_TIMEOUT)
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception as e:
            print(f"  ! linkedin-posts {term!r} failed: {e}", flush=True)
            continue
        for res in results:
            url = res.get("url", "")
            if not url or url in seen:
                continue
            u = url.lower()
            if not any(p in u for p in ("linkedin.com/posts", "linkedin.com/feed",
                                        "linkedin.com/pulse")):
                continue
            content = res.get("content", "")
            if not _kw_match(f"{res.get('title','')} {content}", terms):
                continue
            seen.add(url)
            title = (res.get("title", "") or f"{term} — hiring (LinkedIn post)").strip()
            for sep in (" | ", " - ", " on LinkedIn", " – "):
                title = title.split(sep)[0]
            rows.append({
                "title": title[:120] or f"{term} (hiring post)",
                "company": "(LinkedIn post)", "location": location or "—",
                "site": "LinkedIn post (via Tavily)",
                "date_posted": str(res.get("published_date", ""))[:10],
                "is_remote": "remote" in (title + " " + content).lower(),
                "job_url": url, "description": content[:1500],
            })
    return rows


def _looks_like_job_post(url: str) -> bool:
    """A URL that points at a SPECIFIC opening (not a generic careers/marketing/
    blog page). Drops e.g. 'razorpay.com/careers' or 'pages.razorpay.com/promo'."""
    u = (url or "").lower()
    if any(d in u for d in ("greenhouse.io", "lever.co", "ashbyhq.com",
                            "workable.com", "smartrecruiters.com", "gh_jid")):
        return True
    return re.search(r"/(jobs?|careers|openings?|positions?|vacanc\w+)/[^/?#]+", u) is not None


def fetch_company_careers(companies, keywords, location="", max_age_hours=0,
                          max_results=5):
    """Surface roles for specific companies that have NO public ATS board (their
    careers site is a JS app) by a Tavily web search restricted to each company's
    domain. companies: {display name -> careers domain}. Needs TAVILY_API_KEY;
    returns [] without it.

    Strictly filtered: keeps only results whose URL looks like a specific job post
    AND whose text matches the keywords — so generic careers/landing/blog pages
    are dropped (they're not openings). If a company's openings aren't indexed,
    this honestly returns nothing rather than noise."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key or not companies:
        return []
    role = " ".join(list(keywords)[:2]) if keywords else "software engineer"
    rows, seen = [], set()
    for company, domain in companies.items():
        query = f"{company} {role} job opening apply {location}".strip()
        try:
            r = requests.post("https://api.tavily.com/search", json={
                "api_key": key, "query": query, "max_results": max_results,
                "search_depth": "basic", "include_domains": [domain],
            }, headers=_UA, timeout=_TIMEOUT)
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception as e:
            print(f"  ! tavily {company} careers failed: {e}", flush=True)
            continue
        for res in results:
            url = res.get("url", "")
            if not url or url in seen or not _looks_like_job_post(url):
                continue
            title = res.get("title", "") or f"{company} role"
            for sep in (" - ", " | ", " – ", " at "):
                title = title.split(sep)[0]
            content = res.get("content", "")
            if not _kw_match(f"{title} {content}", keywords):
                continue
            seen.add(url)
            rows.append({
                "title": title.strip()[:120], "company": company,
                "location": location or "—",
                "site": f"{company} careers (via Tavily)", "date_posted": "",
                "is_remote": "remote" in (title + " " + content).lower(),
                "job_url": url, "description": content,
            })
    return rows


def scrape_career_pages(keywords, experience_level=None, location="",
                        max_age_hours=0, use_linkedin=True, use_tavily=True):
    """Scrape direct company career pages (via their ATS APIs) + HN/WWR/LinkedIn,
    all matched against `keywords`. Concurrency capped at _CAREER_WORKERS, each
    domain throttled, results cached 1h. Never raises — failed sources return [].

    keywords: skills/titles to match (e.g. the profile's titles + top skills).
    """
    keywords = [k for k in (keywords or []) if k]
    cache_key = ("career", tuple(sorted(keywords))[:12], location, experience_level)
    cached = _cache_get(cache_key)
    if cached is not None:
        print(f"    -> career pages: {len(cached)} rows (cached)", flush=True)
        return cached

    # One thunk per company board + the extra sources, run ≤2 at a time.
    thunks = []
    for company, slug in GREENHOUSE_BOARDS.items():
        thunks.append(lambda c=company, s=slug: _fetch_greenhouse(c, s, keywords, max_age_hours))
    for company, slug in LEVER_BOARDS.items():
        thunks.append(lambda c=company, s=slug: _fetch_lever(c, s, keywords, max_age_hours))
    for company, slug in ASHBY_BOARDS.items():
        thunks.append(lambda c=company, s=slug: _fetch_ashby(c, s, keywords, max_age_hours))
    thunks.append(lambda: fetch_hackernews(keywords, max_age_hours=max_age_hours))
    thunks.append(lambda: fetch_weworkremotely(keywords, max_age_hours=max_age_hours))
    if use_linkedin:
        thunks.append(lambda: fetch_linkedin_public(keywords, location=location,
                                                     max_age_hours=max_age_hours))
    if use_tavily:
        thunks.append(lambda: fetch_tavily_ats(keywords, location=location,
                                               max_age_hours=max_age_hours))
        # Companies with no public ATS board (e.g. Razorpay, Zerodha) — domain-
        # restricted web search so they still appear in the career-pages results.
        thunks.append(lambda: fetch_company_careers(COMPANY_CAREER_SEARCH, keywords,
                                                    location=location,
                                                    max_age_hours=max_age_hours))
        # Fresh LinkedIn "we're hiring" posts (latest openings the jobs board misses).
        thunks.append(lambda: fetch_linkedin_hiring_posts(keywords, location=location,
                                                          max_age_hours=max_age_hours))

    rows = []
    with ThreadPoolExecutor(max_workers=_CAREER_WORKERS) as ex:
        futs = [ex.submit(t) for t in thunks]
        for f in as_completed(futs):
            try:
                rows += f.result(timeout=30) or []      # 30s per source, then skip
            except Exception:
                continue

    rows = [r for r in rows if r.get("job_url") and _level_ok(r.get("title"), experience_level)]
    print(f"    -> career pages: {len(rows)} rows "
          f"({len(GREENHOUSE_BOARDS) + len(LEVER_BOARDS) + len(ASHBY_BOARDS)} companies + HN/WWR)",
          flush=True)
    _cache_put(cache_key, rows)
    return rows


def fetch_extra(terms, per_term=20, max_age_hours=0, include_career=False,
                experience_level=None, location="", use_tavily=True):
    """All extra sources combined. Never raises — returns whatever came back.
    Free remote-job APIs (Remotive, RemoteOK, Jobicy, Arbeitnow, Himalayas), plus —
    when include_career — direct company career pages via scrape_career_pages().

    use_tavily gates ONLY the Tavily-billed sources (web-discovered ATS boards,
    company careers, LinkedIn hiring posts). The free ATS registry + HN/WWR still
    run when it's False — so the caller can run Tavily less often (free-tier budget)
    while keeping the free sources on every run."""
    rows = []
    for name, fn in (
        ("remotive", lambda: fetch_remotive(terms, per_term=per_term, max_age_hours=max_age_hours)),
        ("remoteok", lambda: fetch_remoteok(terms, max_age_hours=max_age_hours)),
        ("jobicy", lambda: fetch_jobicy(terms, per_term=per_term, max_age_hours=max_age_hours)),
        ("arbeitnow", lambda: fetch_arbeitnow(terms, max_age_hours=max_age_hours)),
        ("himalayas", lambda: fetch_himalayas(terms, max_age_hours=max_age_hours)),
    ):
        try:
            rows += fn()
        except Exception as e:
            print(f"  ! {name} source failed: {e}", flush=True)
    if include_career:
        try:
            rows += scrape_career_pages(terms, experience_level=experience_level,
                                        location=location, max_age_hours=max_age_hours,
                                        use_tavily=use_tavily)
        except Exception as e:
            print(f"  ! career pages failed: {e}", flush=True)
    return rows
