"""
Smart job analyzer — uses Claude to read job descriptions and match them
against your actual profile, not just posted experience years.

A job posting might say "5 years required" but the description might say
"early career welcome" or "we mentor juniors" — this module reads the full
text and gives a smarter verdict than keyword matching alone.

Results are cached (7 days) so we don't re-analyze the same jobs repeatedly.
"""

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
import anthropic

HERE = Path(__file__).parent
CACHE_DIR = HERE / "data" / "job_analysis_cache"

# TTL for cached analyses (7 days)
CACHE_TTL_HOURS = 7 * 24


def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(job_url: str) -> str:
    """Hash the job URL to a cache filename."""
    digest = hashlib.md5(job_url.encode()).hexdigest()
    return str(CACHE_DIR / f"{digest}.json")


def _load_cache(job_url: str) -> dict | None:
    """Load cached analysis if it exists and is fresh."""
    path = _cache_key(job_url)
    if not Path(path).exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cached_at = datetime.fromisoformat(data.get("cached_at", ""))
        if (datetime.now(timezone.utc) - cached_at).total_seconds() > CACHE_TTL_HOURS * 3600:
            return None
        return data
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def _save_cache(job_url: str, analysis: dict):
    """Save analysis result to cache."""
    _ensure_cache_dir()
    path = _cache_key(job_url)
    data = {
        "job_url": job_url,
        "cached_at": datetime.now(timezone.utc).isoformat(),
        **analysis,
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"  ! cache write failed: {e}", flush=True)


def analyze_job(job: dict, profile: dict) -> dict:
    """
    Analyze ONE job to see if it's actually a good fit for the candidate,
    despite what the posted requirements say.

    Returns:
        {
            "fit": True/False,  # is this job a good match for them?
            "reason": str,      # why (or why not)
            "score_delta": int, # suggest rank adjustment: +10 if great fit, -15 if misleading
        }
    """
    job_url = str(job.get("job_url", ""))
    if not job_url:
        return {"fit": None, "reason": "no URL", "score_delta": 0}

    cached = _load_cache(job_url)
    if cached:
        cached.pop("cached_at", None)
        cached.pop("job_url", None)
        return cached

    title = str(job.get("title") or "")
    desc = str(job.get("description") or "")
    company = str(job.get("company") or "")
    blob = f"{title}\n{desc}"

    if not desc or len(desc.strip()) < 50:
        return {"fit": None, "reason": "job description too short to analyse", "score_delta": 0}

    exp_years = profile.get("experience_years", 0)
    skills = profile.get("all_searchable_skills", [])

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = f"""Analyse this job posting against this 2-year backend developer's profile.

CANDIDATE PROFILE:
- Years of experience: {exp_years}
- Key titles: {', '.join(profile.get('job_titles', [])[:3])}
- Primary skills: {', '.join(skills[:10])}

JOB POSTING:
Title: {title}
Company: {company}

Description:
{desc[:2000]}

QUESTION: Does the job description suggest this is actually suitable for a {exp_years}-year junior developer,
even if the posting says "X+ years required"?

Look for signs like:
- "early career", "junior", "entry-level", "we mentor"
- Job is actually junior work (e.g. "Full Stack Junior Developer" despite saying 5 years)
- Flexible experience ("ideally X but will consider")
- Emphasis on skills match over years
- Misleading: senior title but junior-level work, or vice versa

RESPOND in JSON ONLY:
{{
  "fit": true/false,
  "reason": "one sentence why/why not",
  "score_delta": number from -20 to +15
}}

Example if it's junior-friendly despite 5yr posted: {{"fit": true, "reason": "job says 5yr but description emphasizes mentoring early-career devs and Python/Node skills match", "score_delta": 10}}
Example if it's misleadingly senior: {{"fit": false, "reason": "title is 'Senior Staff Engineer' — too senior for your level", "score_delta": -15}}
"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(text[json_start:json_end])
            else:
                return {"fit": None, "reason": "analysis failed to parse", "score_delta": 0}

        _save_cache(job_url, result)
        return result
    except Exception as e:
        print(f"  ! Claude analysis failed for {title}: {e}", flush=True)
        return {"fit": None, "reason": f"analysis error: {type(e).__name__}", "score_delta": 0}


def batch_analyze(jobs: list, profile: dict, max_jobs: int = 100) -> dict:
    """
    Analyse multiple jobs in parallel (respecting Claude rate limits).

    Returns dict: {job_url -> analysis result}
    """
    import concurrent.futures

    jobs_to_analyse = jobs[:max_jobs]
    results = {}

    def _analyze_one(job):
        return job.get("job_url"), analyze_job(job, profile)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_analyze_one, job) for job in jobs_to_analyse]
        for future in concurrent.futures.as_completed(futures):
            try:
                url, analysis = future.result()
                results[url] = analysis
            except Exception as e:
                print(f"  ! batch analysis error: {e}", flush=True)

    return results
