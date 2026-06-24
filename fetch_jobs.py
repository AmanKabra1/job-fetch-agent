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

import pandas as pd
from jobspy import scrape_jobs

import extra_sources as ES


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
SEARCH_TERMS = [
    "backend developer",
    "software engineer",
    "software developer",
]

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

    # Extra real remote sources (Remotive + RemoteOK) — startups & MNCs.
    try:
        extra = ES.fetch_extra(SEARCH_TERMS, per_term=20, max_age_hours=HOURS_OLD)
        if extra:
            edf = pd.DataFrame(extra)
            edf["search_term"] = "remote-api"
            frames.append(edf)
            print(f"    -> {len(edf)} rows (Remotive/RemoteOK)", flush=True)
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


def main():
    print("Fetching jobs ...", flush=True)
    jobs = fetch_all_jobs()
    if jobs.empty:
        print("No jobs returned. Exiting.", flush=True)
        return
    jobs = normalise(jobs)
    print(f"Total unique jobs this run: {len(jobs)}", flush=True)

    # Dedup against URLs already in the feed so we only add genuinely new jobs.
    existing = load_existing()
    seen_urls = {row.get("job_url", "") for row in existing}
    fresh = jobs[~jobs["job_url"].isin(seen_urls)]
    fresh_rows = fresh.to_dict("records")

    if not fresh_rows:
        print("Nothing new to add. Feed is already up to date.", flush=True)
        # Still refresh the file's fetched_at timestamp so the app shows a recent run.
        write_feed(existing)
        return

    # Newest first: prepend this run's fresh jobs to the existing feed.
    combined = fresh_rows + existing
    write_feed(combined)
    print(f"Added {len(fresh_rows)} new jobs to {OUTPUT_FILE} "
          f"(feed now holds {min(len(combined), MAX_STORED)}).", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
