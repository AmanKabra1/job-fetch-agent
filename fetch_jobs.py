"""
Daily job fetcher.

Scrapes LinkedIn / Indeed / Glassdoor / Google / ZipRecruiter via python-jobspy,
dedupes against what is already in your Google Sheet, and appends only new
listings (with a direct apply link) to the sheet.

Run locally:   python fetch_jobs.py
Run in CI:      GitHub Actions cron (see .github/workflows/daily-jobs.yml)
"""

import os
import sys
import json
from datetime import datetime, timezone

import pandas as pd
import gspread
from jobspy import scrape_jobs

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

# Which boards to hit. google + linkedin + indeed are the most useful in India.
SITES = ["linkedin", "indeed", "google"]

# Only jobs posted within this many hours (24 = last day, since this runs daily).
HOURS_OLD = 48

# How many results to pull per search term, per site.
RESULTS_WANTED = 30

# Your Google Sheet. The tab/worksheet is created automatically if missing.
SHEET_NAME = "Job Listings"
WORKSHEET_NAME = "jobs"

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
    "search_term",
]
# --------------------------------------------------------------------------- #


def get_worksheet():
    """Authenticate with a service account and return the target worksheet."""
    # Credentials come from env var GOOGLE_CREDENTIALS (JSON string) in CI,
    # or from a local service_account.json file when running on your machine.
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json:
        gc = gspread.service_account_from_dict(json.loads(creds_json))
    else:
        gc = gspread.service_account(filename="service_account.json")

    sh = gc.open(SHEET_NAME)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=len(COLUMNS))
        ws.append_row(COLUMNS)
    # Make sure a header row exists.
    if not ws.row_values(1):
        ws.append_row(COLUMNS)
    return ws


def fetch_all_jobs() -> pd.DataFrame:
    """Run every search term and return one combined, deduped DataFrame."""
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

    ws = get_worksheet()

    # Dedup against URLs already in the sheet so we only append genuinely new jobs.
    existing = ws.get_all_records()
    seen_urls = {row.get("job_url", "") for row in existing}
    fresh = jobs[~jobs["job_url"].isin(seen_urls)]

    if fresh.empty:
        print("Nothing new to add. Sheet is already up to date.", flush=True)
        return

    ws.append_rows(fresh.values.tolist(), value_input_option="USER_ENTERED")
    print(f"Appended {len(fresh)} new jobs to '{SHEET_NAME}' / '{WORKSHEET_NAME}'.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
