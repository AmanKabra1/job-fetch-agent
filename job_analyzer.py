"""
Smart job analyzer — uses intelligent heuristics to read job descriptions
and match them against your profile. NO API KEYS NEEDED — completely free.

A job posting might say "5 years required" but the description might say
"early career welcome" or "we mentor juniors" — this module reads signals
like this and adjusts ranking accordingly.

Results are cached (7 days) so we don't re-analyze the same jobs repeatedly.
"""

import re
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

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


# Signals that indicate a role is actually junior-friendly despite posted requirements
_JUNIOR_FRIENDLY_SIGNALS = [
    r"\bearly\s*career\b",
    r"\bentry\s*level\b",
    r"\bjunior\s*(?:engineer|developer|role)\b",
    r"\bfresh\s*(?:graduate|grad)\b",
    r"\bwe\s+mentor\b",
    r"\bwe\s+train\b",
    r"\bno\s+(?:prior\s+)?experience\s+required\b",
    r"\bflex(?:ible)?\s+experience\b",
    r"\bwilling\s+to\s+train\b",
    r"\bfirst\s*(?:role|position|job)\b",
    r"\blearning\s+(?:opportunity|environment)\b",
    r"\bgrowth\s+(?:opportunity|focused)\b",
    r"\bcareer\s+development\b",
    r"\bsde\s*-?1\b",
    r"\b1\s*-\s*2\s*years?\b",
    r"\b2\s*-\s*3\s*years?\b",
]

# Signals that indicate a role is TOO SENIOR for a junior candidate
_SENIOR_SIGNALS = [
    r"\bsenior\s+(?:engineer|developer|architect|staff)\b",
    r"\blead\s+(?:engineer|developer)\b",
    r"\bprinciple?\s+engineer\b",
    r"\bstaff\s+engineer\b",
    r"\bvp\s+of\b",
    r"\bdirector\s+(?:of|level)\b",
    r"\bhead\s+of\b",
    r"\b8\+\s*years?\b",
    r"\b10\+\s*years?\b",
    r"\b(?:10|8|7)\s*-\s*(?:15|12|10)\s*years?\b",
]

# Mentorship signals (softens senior requirement)
_MENTOR_SIGNALS = [
    r"\bwe\s+(?:mentor|coach|guide)\b",
    r"\bmentorship\b",
    r"\btraining\s+program\b",
    r"\bbootcamp\b",
    r"\batch\s+house\b",
    r"\bincubat(?:or|e)\b",
]


def _count_signals(text: str, patterns: list) -> int:
    """Count how many signals match in the text."""
    if not text or not patterns:
        return 0
    t = text.lower()
    return sum(1 for p in patterns if re.search(p, t, re.IGNORECASE))


def analyze_job(job: dict, profile: dict) -> dict:
    """
    Analyze ONE job to see if it's actually a good fit for the candidate,
    using intelligent heuristics (no API, completely free).

    Returns:
        {
            "fit": True/False/None,  # is this job a good match?
            "reason": str,           # why (or why not)
            "score_delta": int,      # rank adjustment: +10 if great fit, -15 if misleading
        }
    """
    job_url = str(job.get("job_url", ""))
    if not job_url:
        return {"fit": None, "reason": "no URL", "score_delta": 0}

    # Check cache first
    cached = _load_cache(job_url)
    if cached:
        cached.pop("cached_at", None)
        cached.pop("job_url", None)
        return cached

    title = str(job.get("title") or "")
    desc = str(job.get("description") or "")

    if not desc or len(desc.strip()) < 50:
        return {"fit": None, "reason": "description too short", "score_delta": 0}

    # Analyze the job description for signals
    junior_signals = _count_signals(desc, _JUNIOR_FRIENDLY_SIGNALS)
    senior_signals = _count_signals(desc, _SENIOR_SIGNALS)
    mentor_signals = _count_signals(desc, _MENTOR_SIGNALS)

    score_delta = 0
    reasons = []

    # Positive signals: junior-friendly despite posted requirements
    if junior_signals >= 2:
        score_delta += 12
        reasons.append("junior-friendly signals")
    elif junior_signals == 1:
        score_delta += 6
        reasons.append("some junior-friendly language")

    # Negative signals: role is too senior
    if senior_signals >= 3:
        return {
            "fit": False,
            "reason": "appears too senior (multiple senior titles/requirements)",
            "score_delta": -20,
        }
    elif senior_signals >= 2:
        score_delta -= 10
        reasons.append("senior-level signals")

    # Mentorship softens senior requirement
    if mentor_signals >= 1 and senior_signals >= 1:
        score_delta += 8
        reasons.append("mentors juniors despite senior title")

    # Salary heuristic: check if salary is reasonable for 2-year level in India
    salary_match = re.search(r"([0-9]{1,2})\s*(?:lpa|l|lakhs?|rupees?|₹)", desc, re.IGNORECASE)
    if salary_match:
        try:
            sal = int(salary_match.group(1))
            if 5 <= sal <= 12:
                score_delta += 3
                reasons.append(f"salary ~{sal}L is junior-appropriate")
            elif sal > 15:
                score_delta -= 5
                reasons.append(f"salary ~{sal}L suggests senior role")
        except ValueError:
            pass

    # Build final verdict
    fit = None
    if score_delta > 5:
        fit = True
        reason = "; ".join(reasons) if reasons else "good fit signals"
    elif score_delta < -5:
        fit = False
        reason = "; ".join(reasons) if reasons else "senior-level signals"
    else:
        fit = None
        reason = "; ".join(reasons) if reasons else "neutral fit"

    result = {"fit": fit, "reason": reason, "score_delta": max(-20, min(15, score_delta))}
    _save_cache(job_url, result)
    return result


def batch_analyze(jobs: list, profile: dict, max_jobs: int = 100) -> dict:
    """
    Analyze multiple jobs (fast, no API calls, completely free).
    Returns dict: {job_url -> analysis result}
    """
    results = {}
    for job in jobs[:max_jobs]:
        url = job.get("job_url", "")
        if url:
            results[url] = analyze_job(job, profile)
    return results
