"""
API Handlers - Backend endpoints for resume generation, project management, etc.

Endpoints:
- POST /api/resume/generate - Generate tailored resume for a job
- GET /api/projects/list - List all user projects
- POST /api/projects/add - Manually add a project
- POST /api/projects/fetch-github - Trigger GitHub project fetch
- GET /api/job/analyze - Get job analysis with best project
"""

import json
from datetime import datetime
import projects_manager as PM
import jd_project_matcher as JPM
import dynamic_resume_generator as DRG
import ats_scorer as ATS


def generate_resume_for_job(job: dict, user_resume: dict = None) -> dict:
    """
    API: Generate tailored resume for a specific job.

    Args:
        job: Job dict from feed (title, description, company, etc.)
        user_resume: User's existing resume (optional)

    Returns:
        {
            "success": true,
            "resume": {tailored resume},
            "ats_score": 87,
            "best_project": {project info},
            "project_action": "swapped" or "kept",
            "project_match_score": 92,
            "matched_skills": ["Python", "FastAPI"],
            "message": "Resume generated successfully"
        }
    """
    try:
        result = DRG.generate_tailored_resume(job, user_resume)

        return {
            "success": True,
            "resume": result["resume"],
            "ats_score": result.get("ats_score", 85),
            "best_project": result.get("best_project"),
            "project_action": result.get("project_action", "kept"),
            "project_match_score": result.get("project_match_score", 0),
            "matched_skills": result.get("matched_skills", []),
            "resume_points": result.get("resume_points", []),
            "message": f"Resume tailored for {job.get('title', 'Unknown')} - ATS {result.get('ats_score', 85)}/100"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to generate resume: {str(e)[:100]}"
        }


def list_projects() -> dict:
    """
    API: List all user projects.

    Returns:
        {
            "success": true,
            "projects": [{project1}, {project2}, ...],
            "total": 28,
            "message": "28 projects in portfolio"
        }
    """
    try:
        data = PM.load_projects()
        projects = data.get("projects", [])

        print(f"  API: loaded {len(projects)} projects from storage", flush=True)

        return {
            "success": True,
            "projects": projects,
            "total": len(projects),
            "last_updated": data.get("last_updated"),
            "source": data.get("source", "unknown"),
            "message": f"{len(projects)} projects in your portfolio"
        }
    except Exception as e:
        print(f"  API ERROR loading projects: {e}", flush=True)
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to load projects"
        }


def add_project_manually(
    name: str,
    skills: list,
    description: str,
    github_url: str = None
) -> dict:
    """
    API: Manually add a project to portfolio.

    Args:
        name: Project name
        skills: List of tech skills used
        description: Project description
        github_url: GitHub link (optional)

    Returns:
        {
            "success": true,
            "project": {added project},
            "message": "Project added successfully"
        }
    """
    try:
        # Validate input
        if not name or len(name.strip()) < 2:
            return {"success": False, "error": "Project name required"}

        if not description or len(description.strip()) < 10:
            return {"success": False, "error": "Description too short (min 10 chars)"}

        if not skills or len(skills) == 0:
            return {"success": False, "error": "At least 1 skill required"}

        # Add project
        try:
            project = PM.add_project_manual(
                name=name.strip(),
                skills=skills,
                description=description.strip(),
                github_url=github_url
            )

            if "error" in project:
                return {"success": False, "error": project["error"]}

            return {
                "success": True,
                "project": project,
                "message": f"✓ Project '{name}' added to portfolio"
            }
        except (OSError, IOError, PermissionError) as write_err:
            # Read-only filesystem - return partial success
            return {
                "success": True,
                "note": "Project added to portfolio (Vercel read-only: not persisted)",
                "message": f"✓ Project '{name}' added to portfolio"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to add project: {str(e)[:100]}"
        }


def fetch_github_projects() -> dict:
    """
    API: Fetch projects from GitHub. EVERY button press fetches (no 14-day block):
    lists your public repos, keeps only the REAL projects (manifest + enough source files +
    README/description — not snippets, empty repos or boilerplate), merges with the saved
    list (manual projects are never dropped) and reports what is new and what was skipped.
    """
    try:
        res = PM.sync_github_projects("AmanKabra1")
    except Exception as e:
        return {"success": False, "error": str(e),
                "message": f"GitHub fetch failed: {str(e)[:100]}"}

    data = res["data"]
    skipped = res["skipped"]
    out = {
        "success": True,
        "projects_fetched": len(data["projects"]),
        "new_projects_added": len(res["new"]),
        "new_project_names": res["new"],
        "removed": res["removed"],
        "skipped": skipped,
        "rate_limited": res["rate_limited"],
        "repos_seen": res["repos_seen"],
        "errors": res["errors"],
        "private_projects": data.get("private_count", 0),
        "private_included": res["authed"],
    }
    msg = (f"✓ {len(data['projects'])} real projects ({len(res['new'])} new, "
           f"{data.get('private_count', 0)} private). "
           f"Skipped {len(skipped)} repos that aren't real projects.")
    if not res["authed"]:
        msg += " Private repos NOT included — set GH_PAT (a token with repo scope) or run locally while logged in to gh."
    if res["rate_limited"]:
        msg += " GitHub rate limit hit — set GITHUB_TOKEN to check every repo."
    out["message"] = msg

    try:
        PM.save_projects(data)
        PM._log_fetch()
    except (OSError, IOError, PermissionError):
        out["note"] = ("Read-only filesystem (Vercel): list shown but not saved. "
                       "Run the fetch locally or via the cron to persist it.")
    return out

def get_job_with_analysis(job: dict) -> dict:
    """
    API: Get job with full analysis + best project recommendation.

    Args:
        job: Job from feed

    Returns:
        {
            "job": {...job data},
            "best_project": {project},
            "project_match_score": 92,
            "interview_likelihood": 85,
            "fit_level": "APPLY_NOW",
            "reason": "Why this job is good fit"
        }
    """
    try:
        # Get best project
        project_match = JPM.get_best_project_for_jd(job)

        return {
            "success": True,
            "job": job,
            "best_project": project_match.get("best_project"),
            "project_match_score": project_match.get("best_project", {}).get("match_score", 0),
            "interview_likelihood": job.get("interview_likelihood", 0),
            "fit_level": job.get("fit_level", "GOOD_FIT"),
            "recommendation": project_match.get("recommendation", ""),
            "resume_points": project_match.get("resume_points", [])
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "job": job
        }


def validate_project_input(name: str, skills: list, description: str) -> dict:
    """
    Validate project input before adding.

    Returns:
        {
            "valid": true/false,
            "errors": ["error1", "error2"],
            "warnings": ["warning1"]
        }
    """
    errors = []
    warnings = []

    # Name validation
    if not name or len(name.strip()) == 0:
        errors.append("Project name is required")
    elif len(name.strip()) < 2:
        errors.append("Project name too short (min 2 characters)")
    elif len(name.strip()) > 100:
        errors.append("Project name too long (max 100 characters)")

    # Skills validation
    if not skills or len(skills) == 0:
        errors.append("At least 1 skill is required")
    elif len(skills) > 10:
        warnings.append("You listed 10+ skills; top 5 will be used")

    # Description validation
    if not description or len(description.strip()) == 0:
        errors.append("Description is required")
    elif len(description.strip()) < 10:
        errors.append("Description too short (min 10 characters)")
    elif len(description.strip()) > 500:
        errors.append("Description too long (max 500 characters)")

    # Tech stack validation
    for skill in skills:
        if len(skill.strip()) == 0:
            errors.append("Empty skill in list")
        elif len(skill.strip()) > 50:
            errors.append(f"Skill '{skill}' too long (max 50 chars)")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }
