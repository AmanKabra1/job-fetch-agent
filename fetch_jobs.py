"""
Daily job fetcher.

Scrapes LinkedIn / Indeed / Glassdoor / Google / ZipRecruiter via python-jobspy,
dedupes against the jobs already in data/jobs.json, and appends only new listings
(with a direct apply link) to that file. The GitHub Actions cron commits the
updated file back to the repo; the Vercel app reads it directly — no Google
Sheet, no service account, no credentials.

Run locally:   python fetch_jobs.py
Run in CI:      GitHub Actions cron (see .github/workflows/daily-jobs.yml)
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone

import re

import pandas as pd
from jobspy import scrape_jobs

import extra_sources as ES
import resume_profile as RP        # your saved resume drives search + ranking


def _quiet_jobspy():
    """Disable jobspy's per-board loggers (named 'JobSpy:<Board>', each with its
    own handler). jobspy resets their level every call so setLevel() won't stick,
    but disabling does — blocked-board errors are expected and handled. Lower/
    upper-case variants are pre-disabled too (jobspy makes a fresh logger at call
    time for its 'finished scraping' line)."""
    names = {n for n in logging.root.manager.loggerDict if n.startswith("JobSpy:")}
    for site in ("LinkedIn", "Linkedin", "linkedin", "Indeed", "indeed", "Google",
                 "google", "Glassdoor", "glassdoor", "ZipRecruiter", "zip_recruiter",
                 "Naukri", "naukri", "Bayt", "bayt", "BDJobs", "bdjobs"):
        names.add(f"JobSpy:{site}")
    for name in names:
        logging.getLogger(name).disabled = True

# --------------------------------------------------------------------------- #
# CONFIG  -- edit these freely
# --------------------------------------------------------------------------- #
# Roles to query on the job boards. These reflect your resume (backend / Python /
# Node / full-stack) plus the SDE and AI/ML roles you want. Boards search by role,
# so we keep these as roles; your detailed SKILLS drive the RANKING below.
SEARCH_TERMS = [
    "backend developer",
    "software developer",
    "python developer",
    "node.js developer",
    "software engineer",        # covers SDE / SDE-1 / SDE I postings
    "SDE 1",
    "machine learning engineer",
    "AI engineer",
    "LLM engineer",
    "AI agent engineer",
]

# Extra skills/keywords to emphasise on top of the resume. Edit freely.
PREFERRED_SKILLS = ["Python", "AI", "LLM", "RAG", "Machine Learning",
                    "LangChain", "LangGraph", "Agentic AI", "Java", "Spring Boot"]


def _clean_skill(s: str) -> str:
    """Drop parenthetical detail so 'Java (Spring Boot)' -> 'Java' for matching."""
    return re.sub(r"\s*\(.*?\)\s*", " ", s or "").strip()


# Your resume's skills (flattened from resume_profile.SKILLS) + titles. These are
# what the feed is RANKED against, so jobs that fit YOUR resume rank highest.
RESUME_SKILLS = []
for _cat, _items in RP.SKILLS.items():
    for _s in _items:
        _c = _clean_skill(_s)
        if _c and _c not in RESUME_SKILLS:
            RESUME_SKILLS.append(_c)

# Everything the feed ranking matches against: your search roles + your full
# resume skill set + the extra keywords. This is the "rank mainly by my resume".
RANK_KEYWORDS = list(dict.fromkeys(SEARCH_TERMS + RESUME_SKILLS + PREFERRED_SKILLS))

# Where to look. For India keep country_indeed="India".
LOCATION = "India"
COUNTRY_INDEED = "India"

# Which boards to hit. Every board python-jobspy supports — LinkedIn/Indeed/
# Google are the workhorses in India; the rest are tried resiliently (a board
# that blocks us or returns nothing never aborts the run).
SITES = ["linkedin", "indeed", "google", "glassdoor", "zip_recruiter", "naukri", "bayt"]

# Only jobs posted within this many hours (24 = last day, since this runs daily).
HOURS_OLD = 48

# How many results to pull per search term, per site.
RESULTS_WANTED = 30

# Where the daily feed is written. The Vercel app reads this same file.
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jobs.json")
# Cap the stored feed so the committed file doesn't grow without bound.
MAX_STORED = 1000
# Always keep at least this many jobs in the feed (when that many were fetched),
# even if some fall below the quality gate — so the hosted page is never sparse.
MIN_FEED = 50

# Columns we keep, in order. (jobspy returns many more; these are the useful ones.)
COLUMNS = [
    "date_fetched",
    "title",
    "company",
    "location",
    "site",
    "date_posted",
    "job_url",          # <-- the real, direct link where it's posted
    "min_amount",
    "max_amount",
    "is_remote",
    "company_num_employees",
    "search_term",
]
# --------------------------------------------------------------------------- #


def load_existing() -> list:
    """Return the job rows already stored in data/jobs.json (empty if none)."""
    if not os.path.exists(OUTPUT_FILE):
        return []
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, dict):
        return payload.get("jobs", [])
    return payload if isinstance(payload, list) else []


def write_feed(jobs: list):
    """Write the combined job list to data/jobs.json (newest first, capped)."""
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    payload = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "count": len(jobs),
        "jobs": jobs[:MAX_STORED],
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=0)


def fetch_all_jobs() -> pd.DataFrame:
    """Run every search term and return one combined, deduped DataFrame."""
    _quiet_jobspy()
    frames = []
    for term in SEARCH_TERMS:
        print(f"  searching: {term!r} ...", flush=True)
        try:
            df = scrape_jobs(
                site_name=SITES,
                search_term=term,
                google_search_term=f"{term} jobs near {LOCATION} since yesterday",
                location=LOCATION,
                results_wanted=RESULTS_WANTED,
                hours_old=HOURS_OLD,
                country_indeed=COUNTRY_INDEED,
                linkedin_fetch_description=False,
            )
        except Exception as e:  # one bad board shouldn't kill the whole run
            print(f"    ! {term!r} failed: {e}", flush=True)
            continue
        if df is not None and not df.empty:
            df["search_term"] = term
            frames.append(df)
            print(f"    -> {len(df)} rows", flush=True)

    # Extra real sources — Remotive + RemoteOK + Jobicy + Arbeitnow AND direct
    # company career pages (Greenhouse/Lever/Ashby ATS APIs + Hacker News + We
    # Work Remotely). include_career=True makes the hosted feed match what a local
    # "Fetch live jobs" with the career-pages toggle returns, so Vercel and local
    # show the SAME all-websites result.
    try:
        extra = ES.fetch_extra(SEARCH_TERMS, per_term=20, max_age_hours=HOURS_OLD,
                               include_career=True)
        if extra:
            edf = pd.DataFrame(extra)
            edf["search_term"] = "remote-api"
            frames.append(edf)
            print(f"    -> {len(edf)} rows (APIs + career pages)", flush=True)
    except Exception as e:
        print(f"    ! extra sources failed: {e}", flush=True)

    if not frames:
        return pd.DataFrame(columns=COLUMNS)

    jobs = pd.concat(frames, ignore_index=True)
    jobs = jobs.drop_duplicates(subset=["job_url"])
    return jobs


def normalise(jobs: pd.DataFrame) -> pd.DataFrame:
    """Keep only the columns we care about, in order, as strings."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    jobs = jobs.copy()
    jobs["date_fetched"] = now
    for col in COLUMNS:
        if col not in jobs.columns:
            jobs[col] = ""
    jobs = jobs[COLUMNS]
    return jobs.fillna("").astype(str)


def rank_for_feed(rows):
    """Gate + rank the raw rows against the OWNER'S SAVED PROFILE (resume_profile.py)
    using the SAME personalised scorer the live dashboard uses — skill-match %,
    experience cut-offs, target-title relevance, plus salary/recency/remote/size
    nudges. So the committed feed arrives already matched to your resume and the
    hosted page (mobile, no upload) shows jobs that fit YOU.

    Returns the ORIGINAL rows (keeping their salary fields) in ranked, best-first
    order. Relaxes the skill gate once if the strict pass leaves too few, then tops
    up to MIN_FEED so the page is never sparse. Falls back to input order if the
    scorer can't be imported, so the cron never fails over ranking."""
    try:
        import app as APP                       # reuse the exact dashboard scorer
    except Exception as e:                       # never let ranking abort the run
        print(f"  ! ranking skipped (could not import scorer: {e})", flush=True)
        return rows[:MAX_STORED]

    profile = APP.build_saved_profile()          # your resume drives the gate
    print(f"  ranking against saved profile: "
          f"{profile.get('experience_years')}yr · "
          f"{', '.join((profile.get('job_titles') or [])[:2]) or 'no titles'} · "
          f"{len(profile.get('all_searchable_skills') or [])} skills", flush=True)

    # Strict pass (>= MIN_SKILL_RATIO of a job's skills are yours); relax once if
    # that leaves too few, so the feed is personalised but never empty.
    ranked, _ = APP._rank_jobs(rows, MAX_STORED, profile, APP.MIN_SKILL_RATIO, min_score=0)
    if len(ranked) < max(APP.MIN_KEEP_BEFORE_RELAX, MIN_FEED):
        ranked, _ = APP._rank_jobs(rows, MAX_STORED, profile, APP.RELAX_SKILL_RATIO, min_score=0)
        print(f"  relaxed skill gate (strict pass kept {len(ranked)})", flush=True)

    by_url = {str(r.get("job_url", "")): r for r in rows}
    ordered = [by_url[j["job_url"]] for j in ranked if j.get("job_url") in by_url]

    # Floor: if the gate left fewer than MIN_FEED, top up with the remaining
    # (deduped) raw rows so the feed is never sparse.
    if len(ordered) < MIN_FEED:
        seen = {str(r.get("job_url", "")) for r in ordered}
        for r in rows:
            u = str(r.get("job_url", ""))
            if u and u not in seen:
                ordered.append(r)
                seen.add(u)
            if len(ordered) >= MIN_FEED:
                break
    return ordered[:MAX_STORED]


def main():
    print("Fetching jobs ...", flush=True)
    jobs = fetch_all_jobs()
    if jobs.empty:
        print("No jobs returned. Exiting.", flush=True)
        return
    jobs = normalise(jobs)
    today_rows = jobs.to_dict("records")
    print(f"Total unique jobs this run: {len(today_rows)}", flush=True)

    # REPLACE, not append: each day the feed is just today's latest jobs, ranked.
    # (Safety only: if today's scrape came back thin — boards block sometimes —
    # top up from yesterday's feed so the page is never sparse below the floor.)
    feed_rows = today_rows
    if len(today_rows) < MIN_FEED:
        existing = load_existing()
        seen = {str(r.get("job_url", "")) for r in today_rows}
        feed_rows = today_rows + [r for r in existing
                                  if str(r.get("job_url", "")) not in seen]
        print(f"  thin scrape ({len(today_rows)}); topped up from previous feed "
              f"to {len(feed_rows)} before ranking.", flush=True)

    ranked = rank_for_feed(feed_rows)
    write_feed(ranked)
    print(f"Replaced feed with today's latest: {len(ranked)} jobs "
          f"(best-first, floor {MIN_FEED}).", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
