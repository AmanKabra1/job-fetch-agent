"""
2026 job sources that few candidates watch (lower applicant competition) — all free,
no login, verified live on 2026-10-06:

  * Workable Jobs      jobs.workable.com/api/v1/jobs   (JSON; full JD + requirements;
                       aggregates postings from small/mid companies on Workable ATS;
                       supports location=India and workplace=remote)
  * Working Nomads     workingnomads.com/jobsapi/_search (JSON; has experience_level
                       + annual_salary_usd, so fit can be judged before opening)
  * Himalayas search   himalayas.app/jobs/api/search?country=India (JSON; salary,
                       seniority, location restrictions)
  * Hasjob             hasjob.co/feed (Atom; HasGeek's Indian startup/dev board)

Rows use the same shape as extra_sources.py:
    title / company / location / site / date_posted / is_remote / job_url / description
plus optional structured pay: min_amount / max_amount / interval / currency.

Every fetcher is best-effort: any failure returns [] and never aborts the run.
"""

import re
import html
import datetime as dt
import xml.etree.ElementTree as ET

import requests

import jd_screener as JDS

_UA = {"User-Agent": "Mozilla/5.0 (compatible; job-fetch-agent/1.0)"}
_TIMEOUT = 25

_DEV = re.compile(
    r"\b(backend|back[- ]end|full[- ]?stack|software|developer|engineer|sde|swe|python|node|nest|"
    r"typescript|golang|api|ai|ml|llm|genai|machine learning|platform|programmer)\b", re.I)
_SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|director|head of|vp|architect|manager)\b", re.I)


def _strip(s):
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", str(s))
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def _age_ok(iso, max_age_hours):
    if not iso or not max_age_hours:
        return True
    raw = str(iso).strip().replace("Z", "+00:00")
    try:
        if raw.isdigit():
            d = dt.datetime.fromtimestamp(int(raw), dt.timezone.utc)
        else:
            d = dt.datetime.fromisoformat(raw)
            if d.tzinfo is None:
                d = d.replace(tzinfo=dt.timezone.utc)
        return dt.datetime.now(dt.timezone.utc) - d <= dt.timedelta(hours=max_age_hours)
    except Exception:
        return True


def _iso_date(v):
    s = str(v or "").strip()
    if s.isdigit():
        try:
            return dt.datetime.fromtimestamp(int(s), dt.timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return ""
    return s[:10]


# --------------------------------------------------------------------------- #
# Workable
# --------------------------------------------------------------------------- #
def fetch_workable(terms, location="India", max_age_hours=0, pages=2):
    """One query per search term (India), plus a remote pass. Only fresh postings."""
    rows, seen = [], set()
    queries = []
    for t in list(dict.fromkeys(terms))[:12]:          # cap: one HTTP call per term per page
        queries.append((t, {"location": location}))
    queries.append(("software engineer", {"location": location, "workplace": "remote"}))
    queries.append(("backend", {"location": "", "workplace": "remote"}))
    for term, extra in queries:
        token = None
        for _ in range(pages):
            params = {"query": term, **{k: v for k, v in extra.items() if v}}
            if token:
                params["pageToken"] = token
            try:
                r = requests.get("https://jobs.workable.com/api/v1/jobs", params=params,
                                 headers=_UA, timeout=_TIMEOUT)
                if r.status_code != 200:
                    break
                d = r.json()
            except Exception:
                break
            for j in d.get("jobs", []):
                url = j.get("url") or ""
                title = j.get("title") or ""
                created = j.get("created") or j.get("updated") or ""
                if (not url or url in seen or not _DEV.search(title)
                        or not _age_ok(j.get("updated") or created, max_age_hours)):
                    continue
                seen.add(url)
                loc = j.get("location") or {}
                loc_s = ", ".join(x for x in (loc.get("city"), loc.get("subregion"), loc.get("countryName")) if x)
                desc = _strip(j.get("description")) + "\n" + _strip(j.get("requirementsSection"))
                rows.append({
                    "title": title,
                    "company": (j.get("company") or {}).get("title", ""),
                    "location": loc_s or "Remote",
                    "site": "workable",
                    "date_posted": _iso_date(j.get("updated") or created),
                    "is_remote": (j.get("workplace") == "remote"),
                    "job_url": url,
                    "description": desc.strip(),
                })
            token = d.get("nextPageToken")
            if not token:
                break
    return rows


# --------------------------------------------------------------------------- #
# Working Nomads
# --------------------------------------------------------------------------- #
_WN_BAD_LEVEL = ("SENIOR", "LEAD", "PRINCIPAL", "STAFF", "DIRECTOR", "EXECUTIVE", "MANAGER")


def fetch_workingnomads(terms, max_age_hours=0, size=40):
    rows, seen = [], set()
    for term in terms[:8]:
        try:
            r = requests.get("https://www.workingnomads.com/jobsapi/_search",
                             params={"q": term, "size": size, "sort": "pub_date:desc"},
                             headers=_UA, timeout=_TIMEOUT)
            if r.status_code != 200:
                continue
            hits = r.json().get("hits", {}).get("hits", [])
        except Exception:
            continue
        for h in hits:
            s = h.get("_source") or {}
            title = s.get("title") or ""
            url = s.get("apply_url") or ""
            if not url:
                continue
            slug = s.get("slug")
            page = f"https://www.workingnomads.com/jobs/{slug}" if slug else url
            if (page in seen or str(s.get("expired")).lower() == "true"
                    or not _DEV.search(title) or not _age_ok(s.get("pub_date"), max_age_hours)):
                continue
            lvl = str(s.get("experience_level") or "").upper()
            if any(b in lvl for b in _WN_BAD_LEVEL):
                continue
            locs = s.get("locations") or []
            if isinstance(locs, str):
                locs = [locs]
            loc_s = ", ".join(str(x) for x in locs) or s.get("location_base") or "Remote"
            if not JDS.geo_ok(loc_s):
                continue
            seen.add(page)
            row = {
                "title": title, "company": s.get("company", ""),
                "location": loc_s, "site": "workingnomads",
                "date_posted": _iso_date(s.get("pub_date")), "is_remote": True,
                "job_url": url if url else page,
                "description": _strip(s.get("description")),
            }
            try:
                usd = float(s.get("annual_salary_usd") or 0)
                if usd > 0:
                    row.update(max_amount=usd, interval="yearly", currency="USD")
            except (TypeError, ValueError):
                pass
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Himalayas (search endpoint with country filter)
# --------------------------------------------------------------------------- #
def fetch_himalayas_india(terms, max_age_hours=0, per_term=20):
    rows, seen = [], set()
    for term in terms[:8]:
        try:
            r = requests.get("https://himalayas.app/jobs/api/search",
                             params={"q": term, "country": "India", "sort": "recent"},
                             headers=_UA, timeout=_TIMEOUT)
            if r.status_code != 200:
                continue
            jobs = r.json().get("jobs", [])[:per_term]
        except Exception:
            continue
        for j in jobs:
            title = j.get("title") or ""
            url = j.get("applicationLink") or j.get("guid") or ""
            if (not url or url in seen or not _DEV.search(title)
                    or not _age_ok(str(j.get("pubDate") or ""), max_age_hours)):
                continue
            sen = j.get("seniority") or []
            sen_s = " ".join(sen if isinstance(sen, list) else [str(sen)]).lower()
            if any(k in sen_s for k in ("senior", "lead", "principal", "staff", "director", "executive")) \
                    and not any(k in sen_s for k in ("entry", "junior", "mid")):
                continue
            locs = j.get("locationRestrictions") or []
            loc_s = ", ".join(str(x) for x in locs) if isinstance(locs, list) and locs else "Remote (worldwide)"
            seen.add(url)
            row = {
                "title": title, "company": j.get("companyName", ""),
                "location": loc_s, "site": "himalayas",
                "date_posted": _iso_date(j.get("pubDate")), "is_remote": True,
                "job_url": url,
                "description": _strip(j.get("description") or j.get("excerpt")),
            }
            try:
                mx = float(j.get("maxSalary") or 0) or float(j.get("minSalary") or 0)
                if mx > 0:
                    per = str(j.get("salaryPeriod") or "").lower()
                    row.update(max_amount=mx, currency=str(j.get("currency") or "USD").upper(),
                               interval={"hourly": "hourly", "monthly": "monthly"}.get(per, "yearly"))
            except (TypeError, ValueError):
                pass
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Hasjob (Atom)
# --------------------------------------------------------------------------- #
def fetch_hasjob(max_age_hours=0):
    try:
        r = requests.get("https://hasjob.co/feed", headers=_UA, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    rows = []
    for e in root.findall("a:entry", ns):
        title = (e.findtext("a:title", "", ns) or "").strip()
        link_el = e.find("a:link", ns)
        url = link_el.get("href") if link_el is not None else ""
        pub = e.findtext("a:published", "", ns) or e.findtext("a:updated", "", ns)
        if not url or not _DEV.search(title) or _SENIOR.search(title) or not _age_ok(pub, max_age_hours):
            continue
        body = _strip(e.findtext("a:content", "", ns))
        m = re.match(r"(.+?)\s+(?:at|@)\s+(.+)", title)
        # hasjob URLs are hasjob.co/<company-domain>/<id>; use that when the title has no "at X"
        dm = re.match(r"https?://hasjob\.co/([^/]+)/", url)
        company = m.group(2).strip() if m else (dm.group(1) if dm else "")
        rows.append({
            "title": (m.group(1).strip() if m else title), "company": company,
            "location": "India", "site": "hasjob", "date_posted": str(pub)[:10],
            "is_remote": "remote" in (title + body).lower(), "job_url": url,
            "description": body,
        })
    return rows


# --------------------------------------------------------------------------- #
# LinkedIn enrichment: full JD + REAL applicant count for rows the bulk scrape left
# without a description (jobspy runs with linkedin_fetch_description=False for speed).
# --------------------------------------------------------------------------- #
_LI_ID = re.compile(r"(?:/jobs/view/(?:[^/?#]*-)?|currentJobId=)(\d{6,})")
_LI_DESC = re.compile(r'<div[^>]+class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', re.S | re.I)
_LI_APPL = re.compile(r'class="[^"]*num-applicants__caption[^"]*"[^>]*>\s*([^<]+?)\s*<', re.I)
_LI_CRIT = re.compile(r'description__job-criteria-text[^>]*>\s*([^<]+?)\s*<', re.I)


def enrich_linkedin(rows, max_n=60, min_interval=1.1):
    """Fetch the public guest posting page for up to `max_n` LinkedIn rows lacking a
    description. Adds the JD text plus a '[LinkedIn: <n> applicants]' tag the screener's
    competition model reads. Polite (≈1 req/s), best-effort: a 429/403 stops the pass
    and the rows simply stay as they were. Returns how many rows were enriched."""
    import time
    todo = [r for r in rows
            if "linkedin" in str(r.get("site", "")).lower()
            and len(str(r.get("description") or "")) < 200
            and _LI_ID.search(str(r.get("job_url") or ""))]
    todo.sort(key=lambda r: str(r.get("date_posted") or ""), reverse=True)   # newest first
    done = 0
    for r in todo[:max_n]:
        jid = _LI_ID.search(r["job_url"]).group(1)
        try:
            resp = requests.get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}",
                                headers=_UA, timeout=15)
        except Exception:
            break
        if resp.status_code in (429, 403, 999):
            print(f"    ! LinkedIn enrichment stopped (HTTP {resp.status_code}) after {done} jobs", flush=True)
            break
        if resp.status_code != 200:
            time.sleep(min_interval)
            continue
        m = _LI_DESC.search(resp.text)
        if m:
            desc = _strip(m.group(1))
            ap = _LI_APPL.search(resp.text)
            crit = " ".join(_LI_CRIT.findall(resp.text)[:4])
            tail = []
            if ap:
                tail.append(f"[LinkedIn: {html.unescape(ap.group(1))}]")
            if crit:
                tail.append(f"[LinkedIn criteria: {html.unescape(crit)}]")
            r["description"] = (desc + "\n" + " ".join(tail)).strip()
            done += 1
        time.sleep(min_interval)
    return done


def fetch_all(terms, max_age_hours=0):
    """All new-portal sources. Returns (rows, per_source_counts)."""
    out, counts = [], {}
    for name, fn in (
        ("workable", lambda: fetch_workable(terms, max_age_hours=max_age_hours)),
        ("workingnomads", lambda: fetch_workingnomads(terms, max_age_hours=max_age_hours)),
        ("himalayas-india", lambda: fetch_himalayas_india(terms, max_age_hours=max_age_hours)),
        ("hasjob", lambda: fetch_hasjob(max_age_hours=max_age_hours)),
    ):
        try:
            rows = fn()
        except Exception as e:
            print(f"  ! {name} failed: {e}", flush=True)
            rows = []
        counts[name] = len(rows)
        out += rows
    return out, counts
