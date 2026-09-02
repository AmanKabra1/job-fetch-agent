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
import strict_matcher as SM        # strict filtering before ranking
import job_analyzer as JA          # free heuristic-based job analysis (no API needed)
import job_requirement_agent as JRA  # LangGraph agent: check JD + expiration
import job_fit_analyzer as JFA     # AI agent: analyzes top 50 jobs for interview likelihood


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
    # TOP PRIORITY: Node.js, NestJS, Full Stack, AI (your preferred tech)
    "Node.js developer", "NestJS developer", "full stack developer",
    "AI engineer", "LLM engineer", "AI developer",
    "Node.js backend engineer", "NestJS backend engineer", "full stack engineer",

    # HIGH PRIORITY: Python, Backend, AI/ML
    "Python developer", "Python backend engineer", "backend developer", "backend engineer",
    "TypeScript backend developer", "Express.js developer",
    "machine learning engineer", "ML engineer",

    # SECONDARY: Java, Go, other backends (expanded to get more jobs)
    "Java backend engineer", "Java developer", "Spring Boot developer",
    "Go developer", "Golang engineer", "Go backend developer",
    "microservices developer", "API developer", "REST API developer",

    # INCLUSIVE: Junior/Entry-level (1-2 years OK, not just 2+)
    "Junior developer", "Junior backend developer", "Junior full stack developer",
    "junior engineer", "entry level developer", "graduate engineer",
    "Junior Java developer", "Junior Python developer", "Junior Node.js developer",

    # GENERAL: Catch-all for more volume
    "software developer", "software engineer", "SDE 1",
    "data engineer", "full stack engineer",
]

# Extra skills/keywords to emphasise on top of the resume. Edit freely.
PREFERRED_SKILLS = ["Node.js", "NestJS", "Express.js", "TypeScript", "JavaScript",
                    "Python", "Java", "Spring Boot", "Go", "Golang", "Docker", "Microservices",
                    "PostgreSQL", "MongoDB", "REST API", "GraphQL",
                    "AI", "LLM", "RAG", "Machine Learning", "ML Engineer",
                    "LangChain", "LangGraph", "Agentic AI", "Junior", "Entry Level"]


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

# Only jobs posted within this many hours (72 = last 3 days for sufficient volume).
# Increased from 24 to 72 to get enough jobs on Indian boards
HOURS_OLD = 72

# How many results to pull per search term, per site.
# Increased to 100 for more job options matching user skills
RESULTS_WANTED = 100

# Where the daily feed is written. The Vercel app reads this same file.
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jobs.json")
# Cap the stored feed so the committed file doesn't grow without bound.
MAX_STORED = 2000  # Increased to show 300+ jobs
# Always keep at least this many fresh jobs in the feed (when that many were fetched).
# Realistic target: 200-300 quality jobs per cron run (more chances to apply)
MIN_KEEP_BEFORE_RELAX = 200
# even if some fall below the quality gate — so the hosted page is never sparse.
MIN_FEED = 300  # Target: Show 300+ jobs matching user's skills, experience, requirements

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

    # Extra real sources — Remotive + RemoteOK + Jobicy + Arbeitnow + Himalayas AND
    # direct company career pages (Greenhouse/Lever/Ashby ATS APIs + HN + WWR).
    #
    # The cron runs 3x a day, so disable Tavily sources for speed.
    # Tavily is too slow for this frequency. Focus on direct board APIs instead.
    use_tavily = False  # DISABLED for speed - direct APIs are enough
    print(f"  Tavily sources this run: {'ON' if use_tavily else 'off (free sources only)'}",
          flush=True)
    try:
        extra = ES.fetch_extra(SEARCH_TERMS, per_term=20, max_age_hours=HOURS_OLD,
                               include_career=True, use_tavily=use_tavily)
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


def add_date_category(rows):
    """Categorize jobs by posting date: TODAY (last 3 days), THIS_WEEK (3-7 days), RECENT (8-14 days), OLD (15+ days)"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_date = now.date()

    for row in rows:
        date_posted = str(row.get("date_posted", "")).strip()
        try:
            posted = datetime.strptime(date_posted[:10], "%Y-%m-%d")
            posted_date = posted.date()
            days_old = (now - posted).days

            # TODAY = posted in last 14 days (freshest available jobs)
            if days_old >= 0 and days_old <= 14:
                row["_date_category"] = "TODAY"
            # THIS_WEEK = posted 15-21 days ago
            elif days_old >= 15 and days_old <= 21:
                row["_date_category"] = "THIS_WEEK"
            # RECENT = posted 22-30 days ago
            elif days_old >= 22 and days_old <= 30:
                row["_date_category"] = "RECENT"
            else:
                row["_date_category"] = "OLD"  # Will be filtered out
        except (ValueError, TypeError):
            row["_date_category"] = "UNKNOWN"

    return rows


def rank_for_feed(rows):
    """Gate + rank the raw rows against the OWNER'S SAVED PROFILE (resume_profile.py)
    using the SAME personalised scorer the live dashboard uses — skill-match %,
    experience cut-offs, target-title relevance, plus salary/recency/remote/size
    nudges. So the committed feed arrives already matched to your resume and the
    hosted page (mobile, no upload) shows jobs that fit YOU.

    Also uses Claude (job_analyzer.py) to intelligently read job descriptions and
    adjust ranking if the posting says "5 years" but actually mentors junior devs.

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

    # AI job intelligence: read job descriptions and adjust ranking based on actual fit,
    # not just posted experience years. E.g., "5 years posted but mentors juniors" -> boost.
    try:
        import job_analyzer as JA
        print(f"  analysing top {min(100, len(ordered))} jobs with Claude ...", flush=True)
        analyses = JA.batch_analyze(ordered[:100], profile, max_jobs=100)
        for job in ordered:
            url = job.get("job_url", "")
            if url not in analyses:
                continue
            analysis = analyses[url]
            delta = analysis.get("score_delta", 0)
            if delta:
                job["_ai_analysis"] = analysis
                job["_ai_delta"] = delta
        # Re-rank with AI adjustments
        ordered.sort(key=lambda j: (j.get("_ai_delta", 0), -APP._days_old(j.get("date_posted"))),
                     reverse=True)
        boosted = len([j for j in ordered if j.get("_ai_delta", 0) > 0])
        penalised = len([j for j in ordered if j.get("_ai_delta", 0) < 0])
        if boosted or penalised:
            print(f"  AI analysis: {boosted} boosted, {penalised} penalised", flush=True)
    except Exception as e:
        print(f"  ! AI analysis skipped: {e}", flush=True)

    # Floor: if the gate left fewer than MIN_FEED, top up with the remaining
    # (deduped) raw rows so the feed is never sparse. But NEVER include jobs with
    # 0 skill matches (completely irrelevant roles).
    if len(ordered) < MIN_FEED:
        seen = {str(r.get("job_url", "")) for r in ordered}
        for r in rows:
            u = str(r.get("job_url", ""))
            if u and u not in seen:
                # Only add if it has at least 1 skill match (not completely irrelevant)
                has_skill_match = any(skill in r.get('description', '').lower()
                                     for skill in SEARCH_TERMS)
                if has_skill_match or r.get('search_term') in SEARCH_TERMS:
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

    # STRICT FILTERING: Apply hard gates before ranking.
    # This is crucial — filter out jobs that don't match your experience/skills
    # BEFORE they even enter the feed, not just downranking them.
    print(f"  applying strict filter (experience: 2yr, core stack: Python/Node/Java/Backend/AI) ...", flush=True)
    filtered_rows, filter_stats = SM.filter_jobs(today_rows, candidate_experience_years=2)
    print(f"    strict filter: {filter_stats['kept']}/{filter_stats['total']} kept "
          f"({filter_stats['rejected']} rejected)", flush=True)

    # Show top rejection reasons
    reject_reasons = {}
    for url, info in filter_stats['rejection_reasons'].items():
        reason = info.get('reason', 'unknown')
        reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
    if reject_reasons:
        top_reasons = sorted(reject_reasons.items(), key=lambda x: x[1], reverse=True)[:3]
        for reason, count in top_reasons:
            print(f"      {count}× {reason}", flush=True)

    today_rows = filtered_rows  # Use filtered jobs from now on

    # DEDUPLICATION STEP 1: Remove exact URL duplicates within this run
    print(f"  deduplicating jobs within this run ...", flush=True)
    today_rows, dedup_stats = JRA.deduplicate_jobs(today_rows)
    print(f"    removed {dedup_stats['duplicate_count']} duplicates (same title+company or URL)", flush=True)

    # DEDUPLICATION STEP 2: Remove jobs already in previous feed
    print(f"  deduplicating against previous feed ...", flush=True)
    existing = load_existing()
    existing_urls = {str(r.get("job_url", "")) for r in existing}
    today_rows = [r for r in today_rows if str(r.get("job_url", "")) not in existing_urls]
    dedup_removed = len(filtered_rows) - len(today_rows)
    if dedup_removed > 0:
        print(f"    removed {dedup_removed} duplicate jobs from previous runs", flush=True)
    print(f"    now have {len(today_rows)} new unique jobs", flush=True)

    # REQUIREMENT AGENT: Temporarily disabled to debug why only 12 jobs show
    # Uncomment below to re-enable Groq verification
    # profile_dict = {
    #     "experience_years": 2,
    #     "job_titles": getattr(RP, "TARGET_TITLES", ["Backend Developer", "Software Engineer"]),
    #     "all_searchable_skills": [s for items in RP.SKILLS.values() for s in items],
    # }
    # verified_rows, req_stats = JRA.filter_jobs_with_agent(today_rows, profile_dict, max_assess=50)
    # today_rows = verified_rows

    # For now, skip Groq verification - just check basic expiration
    print(f"  checking job expiration only (Groq verification disabled for debugging) ...", flush=True)
    expired_count = 0
    fresh_rows = []
    for job in today_rows:
        exp_check = JRA.check_job_expiration(job)
        if not exp_check.get("is_expired", False):
            fresh_rows.append(job)
        else:
            expired_count += 1
    if expired_count > 0:
        print(f"    filtered {expired_count} expired jobs, kept {len(fresh_rows)}", flush=True)
    today_rows = fresh_rows

    # REPLACE, not append: each run the feed is this run's latest jobs, ranked.
    existing = load_existing()
    seen = {str(r.get("job_url", "")) for r in today_rows}

    # Carry forward the Tavily-only sources (LinkedIn "we're hiring" posts +
    # web-discovered career pages) from the previous feed. They're fetched only
    # twice a day (to stay in the free Tavily tier), so on the ~6 non-Tavily runs
    # each day they'd otherwise vanish from the feed. Keep the recent ones (by
    # date_fetched, up to CARRY_DAYS old) so they persist between Tavily runs.
    CARRY_DAYS = 3
    now = datetime.now(timezone.utc)
    def _tavily_row(r):
        s = (r.get("site") or "").lower()
        return "linkedin post" in s or "via tavily" in s
    def _fresh(r):
        try:
            d = datetime.strptime(str(r.get("date_fetched", ""))[:16], "%Y-%m-%d %H:%M")
            return (now.replace(tzinfo=None) - d).days <= CARRY_DAYS
        except (ValueError, TypeError):
            return True
    carried = [r for r in existing
               if _tavily_row(r) and _fresh(r) and str(r.get("job_url", "")) not in seen]
    if carried:
        today_rows = today_rows + carried
        seen |= {str(r.get("job_url", "")) for r in carried}
        print(f"  carried forward {len(carried)} Tavily rows (LinkedIn posts / career "
              f"pages) from the previous feed.", flush=True)

    # Safety: if this run's scrape came back thin — boards block sometimes — top up
    # from the previous feed so the page is never sparse below the floor.
    # BUT: Only top up with FRESH jobs (< 14 days old) to keep the feed current!
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    def _is_fresh(r, max_days=14):
        try:
            date_str = str(r.get("date_posted", "")).strip()
            if not date_str:
                return False
            posted = datetime.strptime(date_str[:10], "%Y-%m-%d")
            age_days = (now - posted).days
            return age_days <= max_days
        except (ValueError, TypeError):
            return False

    feed_rows = today_rows
    if len(today_rows) < MIN_FEED:
        # QUALITY: From existing jobs, keep ONLY 95%+ matches (from previous cron filtering)
        high_quality_existing = [r for r in existing
                                if str(r.get("job_url", "")) not in seen
                                and _is_fresh(r)
                                and r.get("_match_score", 0) >= 95]  # Keep 95%+ only
        low_quality_existing = [r for r in existing
                               if str(r.get("job_url", "")) not in seen
                               and _is_fresh(r)
                               and r.get("_match_score", 0) < 95]  # These are older, lower quality

        feed_rows = today_rows + high_quality_existing
        removed_low = len(low_quality_existing)

        if removed_low > 0:
            print(f"  thin scrape ({len(today_rows)}); removed {removed_low} low-quality jobs (<95%) from previous cron", flush=True)
        print(f"  topped up with {len(high_quality_existing)} high-quality (95%+) fresh jobs "
              f"(< 14 days old) to {len(feed_rows)} before ranking.", flush=True)

    # ADD DATE CATEGORIES: TODAY (3d), THIS_WEEK (7d), RECENT (14d)
    print(f"  categorizing jobs by posting date ...", flush=True)
    feed_rows = add_date_category(feed_rows)

    # Count jobs per category
    today_count = sum(1 for r in feed_rows if r.get("_date_category") == "TODAY")
    week_count = sum(1 for r in feed_rows if r.get("_date_category") == "THIS_WEEK")
    recent_count = sum(1 for r in feed_rows if r.get("_date_category") == "RECENT")
    old_count = sum(1 for r in feed_rows if r.get("_date_category") == "OLD")
    print(f"    categories: {today_count} TODAY, {week_count} THIS_WEEK, {recent_count} RECENT, {old_count} OLD", flush=True)

    ranked = rank_for_feed(feed_rows)

    # QUALITY BREAKDOWN: Show all jobs now, but track quality for next cron
    high_quality = [r for r in ranked if r.get("_match_score", 0) >= 95]
    medium_quality = [r for r in ranked if 75 <= r.get("_match_score", 0) < 95]
    low_quality = [r for r in ranked if r.get("_match_score", 0) < 75]

    quality_breakdown = f"High(95%+):{len(high_quality)} | Medium(75-95%):{len(medium_quality)} | Low:<75:{len(low_quality)}"
    print(f"  quality breakdown: {quality_breakdown}", flush=True)
    print(f"  NOTE: Showing ALL jobs this cron. Next cron will keep ONLY 95%+ from this batch.", flush=True)

    # AI Analysis: Analyze top 50 jobs for interview likelihood
    print(f"  analyzing top 50 jobs for interview likelihood ...", flush=True)
    try:
        ranked = JFA.analyze_top_jobs(ranked, top_n=50)
        print(f"    ✓ analyzed top 50 jobs for fit", flush=True)
    except Exception as e:
        print(f"    ! fit analysis failed: {e} (continuing without analysis)", flush=True)

    write_feed(ranked)
    print(f"Replaced feed with today's latest: {len(ranked)} jobs "
          f"({quality_breakdown}, organized by quality + match score, floor {MIN_FEED}).", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
