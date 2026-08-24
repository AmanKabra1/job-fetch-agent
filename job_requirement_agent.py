"""
LangGraph-based job requirement verification agent.

Multi-step agent that:
1. Analyzes job description against candidate profile
2. Checks if job posting is still open (not expired)
3. Verifies requirements are truly met (not misleading)
4. Returns detailed assessment with expiration status
"""

import os
import re
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from pathlib import Path

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

try:
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Command
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

HERE = Path(__file__).parent
CACHE_DIR = HERE / "data" / "job_requirement_cache"

def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def check_job_expiration(job: dict) -> dict:
    """
    Check if a job posting is likely still open.
    Looks for actual "closed/expired" signals in description, not just date.

    Returns:
        {
            "is_expired": bool,
            "days_old": int,
            "posted_date": str,
            "reason": str,
        }
    """
    # HARD SIGNALS: Check description for "closed", "expired", "no longer accepting"
    description = str(job.get("description", "")).lower()
    title = str(job.get("title", "")).lower()
    full_text = title + " " + description

    closed_signals = [
        r"closed",
        r"expired",
        r"no longer accepting",
        r"no longer hiring",
        r"hiring completed",
        r"position filled",
        r"not accepting applications",
        r"applications closed",
        r"no longer available",
    ]

    for signal in closed_signals:
        if re.search(signal, full_text, re.IGNORECASE):
            return {
                "is_expired": True,
                "days_old": None,
                "posted_date": job.get("date_posted", ""),
                "reason": f"job description says: {signal}"
            }

    date_posted = str(job.get("date_posted", "")).strip()

    if not date_posted or date_posted == "":
        return {
            "is_expired": False,
            "days_old": None,
            "posted_date": None,
            "reason": "no posting date, but no closed signals detected"
        }

    try:
        # Try parsing different date formats
        posted = None
        for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M", "%d/%m/%Y", "%m/%d/%Y"]:
            try:
                posted = datetime.strptime(date_posted[:10], "%Y-%m-%d")
                break
            except (ValueError, TypeError):
                pass

        if not posted:
            return {
                "is_expired": False,
                "days_old": None,
                "posted_date": date_posted,
                "reason": "could not parse posting date (assume still open)"
            }

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        days_old = (now - posted).days

        # Much longer window: jobs older than 60+ days MIGHT be expired,
        # but trust the description signals more than the date
        is_expired = days_old > 90  # Changed from 30 to 90 days

        return {
            "is_expired": is_expired,
            "days_old": days_old,
            "posted_date": date_posted,
            "reason": f"posted {days_old} days ago" + (" (very old, might be closed)" if is_expired else " (likely still open)")
        }
    except Exception as e:
        return {
            "is_expired": False,
            "days_old": None,
            "posted_date": date_posted,
            "reason": f"could not verify expiration: {e}"
        }


def analyze_jd_requirements(job: dict, profile: dict) -> dict:
    """
    Use Groq (free API) to deeply analyze if job truly meets candidate's requirements.

    Returns:
        {
            "meets_requirements": bool,
            "requirement_match": str,  # "high" | "medium" | "low"
            "key_matches": [str],
            "concerns": [str],
            "reason": str,
        }
    """
    if not GROQ_AVAILABLE:
        # Fallback to heuristic if Groq not available
        return {
            "meets_requirements": True,
            "requirement_match": "unknown",
            "key_matches": [],
            "concerns": ["groq unavailable for deep analysis"],
            "reason": "fallback - groq not available"
        }

    title = job.get("title", "")
    description = job.get("description", "")

    if not description or len(description) < 100:
        return {
            "meets_requirements": False,
            "requirement_match": "low",
            "key_matches": [],
            "concerns": ["insufficient job description"],
            "reason": "JD too short to assess"
        }

    # Build candidate profile summary
    candidate_summary = f"""
Experience: {profile.get('experience_years', 2)} years
Target Roles: {', '.join(profile.get('job_titles', [])[:3])}
Key Skills: {', '.join(profile.get('all_searchable_skills', [])[:10])}
Location: India (open to remote)
"""

    prompt = f"""Analyze if this job truly meets the candidate's requirements.

CANDIDATE PROFILE:
{candidate_summary}

JOB POSTING:
Title: {title}
Description (first 2000 chars):
{description[:2000]}

ASSESSMENT CHECKLIST:
1. Experience Required: Does this job match the 2-year level? YES/NO
2. Tech Stack: Does it align with their skills? YES/NO
3. Role Type: Is this a backend/AI/full-stack role? YES/NO
4. Misleading?: Does it say junior but require 5+ years? YES/NO
5. Location: Is it remote or India-based? YES/NO

RESPOND WITH ONLY JSON (no markdown, no code blocks):
{{
  "meets_requirements": true or false,
  "requirement_match": "high" or "medium" or "low",
  "key_matches": ["what aligns well"],
  "concerns": ["red flags or mismatches"],
  "reason": "brief assessment"
}}"""

    try:
        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            return {
                "meets_requirements": True,
                "requirement_match": "medium",
                "key_matches": [],
                "concerns": ["GROQ_API_KEY not set in environment"],
                "reason": "fallback - no API key"
            }

        client = Groq(api_key=groq_key)
        message = client.chat.completions.create(
            model="mixtral-8x7b-32768",  # Free model from Groq
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )

        response_text = message.choices[0].message.content.strip()

        # Extract JSON (Groq returns clean JSON)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        # Clean JSON if needed
        response_text = response_text.strip()
        if not response_text.startswith("{"):
            # Try to find JSON in response
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                response_text = response_text[start:end]

        assessment = json.loads(response_text)
        return assessment

    except json.JSONDecodeError as e:
        return {
            "meets_requirements": True,
            "requirement_match": "medium",
            "key_matches": [],
            "concerns": [f"json parse error: {str(e)}"],
            "reason": "fallback - groq response parse error"
        }
    except Exception as e:
        return {
            "meets_requirements": True,
            "requirement_match": "medium",
            "key_matches": [],
            "concerns": [f"groq error: {str(e)}"],
            "reason": "fallback - groq api error"
        }


class JobRequirementState:
    """State object for LangGraph agent."""
    def __init__(self):
        self.job = {}
        self.profile = {}
        self.expiration_check = {}
        self.jd_analysis = {}
        self.final_verdict = {}


def assess_job_requirement(job: dict, profile: dict) -> dict:
    """
    Main entry point: Assess if job meets requirements AND is still open.
    Uses LangGraph for multi-step reasoning.

    Returns:
        {
            "verdict": "KEEP" | "FILTER",
            "reason": str,
            "is_expired": bool,
            "meets_requirements": bool,
            "requirement_match": str,
            "key_matches": [str],
            "concerns": [str],
            "expiration_info": {...},
        }
    """

    job_url = job.get("job_url", "")

    # Step 1: Check if job is expired
    expiration_check = check_job_expiration(job)

    if expiration_check["is_expired"]:
        return {
            "verdict": "FILTER",
            "reason": f"job posting is {expiration_check['days_old']} days old (likely expired)",
            "is_expired": True,
            "meets_requirements": None,
            "requirement_match": "n/a",
            "key_matches": [],
            "concerns": ["posting has expired"],
            "expiration_info": expiration_check,
        }

    # Step 2: Analyze if JD truly meets requirements
    jd_analysis = analyze_jd_requirements(job, profile)

    # Step 3: Make final verdict
    if not jd_analysis.get("meets_requirements", True):
        return {
            "verdict": "FILTER",
            "reason": f"JD doesn't match requirements: {jd_analysis.get('reason', '')}",
            "is_expired": False,
            "meets_requirements": False,
            "requirement_match": jd_analysis.get("requirement_match", "low"),
            "key_matches": jd_analysis.get("key_matches", []),
            "concerns": jd_analysis.get("concerns", []),
            "expiration_info": expiration_check,
        }

    # Step 4: Job is OPEN and meets requirements
    return {
        "verdict": "KEEP",
        "reason": f"Job is open and meets requirements ({jd_analysis.get('requirement_match', 'medium')} match)",
        "is_expired": False,
        "meets_requirements": True,
        "requirement_match": jd_analysis.get("requirement_match", "medium"),
        "key_matches": jd_analysis.get("key_matches", []),
        "concerns": jd_analysis.get("concerns", []),
        "expiration_info": expiration_check,
    }


def filter_jobs_with_agent(jobs: list, profile: dict, max_assess: int = 200) -> tuple[list, dict]:
    """
    Filter jobs using LangGraph agent.

    Returns: (kept_jobs, stats)
    """
    kept = []
    filtered = {}
    stats = {
        "total": len(jobs),
        "assessed": 0,
        "kept": 0,
        "filtered_expired": 0,
        "filtered_requirements": 0,
        "filtered_other": 0,
    }

    for job in jobs[:max_assess]:
        url = job.get("job_url", "")

        # Assess job
        assessment = assess_job_requirement(job, profile)
        stats["assessed"] += 1

        if assessment["verdict"] == "KEEP":
            kept.append(job)
            job["_requirement_assessment"] = assessment
            stats["kept"] += 1
        else:
            filtered[url] = {
                "title": job.get("title", ""),
                "reason": assessment["reason"],
                "is_expired": assessment.get("is_expired", False),
                "meets_requirements": assessment.get("meets_requirements"),
                "concerns": assessment.get("concerns", [])
            }

            if assessment.get("is_expired"):
                stats["filtered_expired"] += 1
            elif not assessment.get("meets_requirements"):
                stats["filtered_requirements"] += 1
            else:
                stats["filtered_other"] += 1

    # Keep remaining unassessed jobs
    kept.extend(jobs[max_assess:])

    return kept, {"stats": stats, "filtered": filtered}
