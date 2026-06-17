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

Every row is mapped to the same shape app.py already scores
(title/company/location/site/date_posted/is_remote/job_url/description), so they
merge straight into the one ranked list. All jobs here are remote by nature.

These are best-effort and resilient: a source that is down or rate-limited just
returns [] and never aborts the run.
"""

import re
import html
import datetime as dt

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


def fetch_extra(terms, per_term=20, max_age_hours=0):
    """All extra sources combined. Never raises — returns whatever came back.
    Real, currently-active free APIs: Remotive, RemoteOK, Jobicy, Arbeitnow."""
    rows = []
    for name, fn in (
        ("remotive", lambda: fetch_remotive(terms, per_term=per_term, max_age_hours=max_age_hours)),
        ("remoteok", lambda: fetch_remoteok(terms, max_age_hours=max_age_hours)),
        ("jobicy", lambda: fetch_jobicy(terms, per_term=per_term, max_age_hours=max_age_hours)),
        ("arbeitnow", lambda: fetch_arbeitnow(terms, max_age_hours=max_age_hours)),
    ):
        try:
            rows += fn()
        except Exception as e:
            print(f"  ! {name} source failed: {e}", flush=True)
    return rows
