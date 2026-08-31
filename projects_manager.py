"""
Projects Manager - Manages user's project portfolio for job matching.

Features:
1. GitHub auto-fetch (once per 2 weeks - rate limited)
2. Manual project input (anytime)
3. Memory storage with metadata
4. Project matching to jobs

User: AmanKabra1 (GitHub) / amankabra.it24@gmail.com
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path

PROJECTS_FILE = Path(__file__).parent / "data" / "projects.json"
FETCH_LOG_FILE = Path(__file__).parent / "data" / ".projects_fetch_log"

# Rate limiting: Fetch from GitHub only once per 2 weeks
FETCH_INTERVAL_DAYS = 14


def _ensure_data_dir():
    """Ensure data directory exists."""
    PROJECTS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _should_fetch_github() -> bool:
    """
    Check if we should fetch from GitHub (once per 2 weeks).

    Returns True if:
    - Never fetched before
    - Last fetch was >14 days ago
    """
    if not FETCH_LOG_FILE.exists():
        return True

    try:
        with open(FETCH_LOG_FILE, "r") as f:
            last_fetch_str = f.read().strip()
        last_fetch = datetime.fromisoformat(last_fetch_str)
        days_since = (datetime.now() - last_fetch).days
        return days_since >= FETCH_INTERVAL_DAYS
    except:
        return True


def _is_read_only():
    """Check if filesystem is read-only (Vercel serverless)."""
    try:
        test_file = PROJECTS_FILE.parent / ".write_test"
        with open(test_file, "w") as f:
            f.write("test")
        test_file.unlink()
        return False
    except (OSError, IOError, PermissionError):
        return True


def _log_fetch():
    """Log the last GitHub fetch time."""
    if _is_read_only():
        return  # Can't write on read-only filesystem

    try:
        FETCH_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(FETCH_LOG_FILE, "w") as f:
            f.write(datetime.now().isoformat())
    except:
        pass


def load_projects() -> dict:
    """Load all projects from storage."""
    _ensure_data_dir()

    if not PROJECTS_FILE.exists():
        return {
            "projects": [],
            "last_updated": None,
            "source": "none",
            "total": 0
        }

    try:
        with open(PROJECTS_FILE, "r") as f:
            return json.load(f)
    except:
        return {"projects": [], "last_updated": None, "source": "none", "total": 0}


def save_projects(projects_data: dict):
    """Save projects to storage."""
    _ensure_data_dir()

    with open(PROJECTS_FILE, "w") as f:
        json.dump(projects_data, f, indent=2)


def fetch_github_projects(username: str = "AmanKabra1") -> list:
    """
    Fetch projects from GitHub (ONCE per 2 weeks - rate limited).

    Returns: List of projects with name, tech stack, description
    """
    if not _should_fetch_github():
        print(f"  ! GitHub fetch skipped (last fetch <14 days ago, rate limit protection)", flush=True)
        return []

    print(f"  fetching projects from GitHub ({username}) ...", flush=True)

    try:
        import requests

        # Fetch user repos
        url = f"https://api.github.com/users/{username}/repos?sort=updated&per_page=50"
        headers = {"Accept": "application/vnd.github.v3+json"}

        # Optional: Use GitHub token if available (higher rate limit)
        github_token = os.environ.get("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        repos = response.json()

        projects = []
        for repo in repos:
            # Skip forks and private repos
            if repo.get("fork") or repo.get("private"):
                continue

            project = {
                "name": repo.get("name", ""),
                "description": repo.get("description", ""),
                "github_url": repo.get("html_url", ""),
                "language": repo.get("language", ""),
                "stars": repo.get("stargazers_count", 0),
                "updated": repo.get("updated_at", ""),
                "source": "github",
                "tech_stack": _extract_tech_from_repo(repo),
            }

            if project["name"]:
                projects.append(project)

        _log_fetch()
        print(f"    ✓ fetched {len(projects)} projects from GitHub", flush=True)
        return projects

    except Exception as e:
        print(f"    ! GitHub fetch failed: {e}", flush=True)
        return []


def _extract_tech_from_repo(repo: dict) -> list:
    """Extract tech stack from repo (language + common tech from readme)."""
    tech = []

    # Primary language
    if repo.get("language"):
        tech.append(repo["language"])

    # Common tech detection from repo name/desc
    name_desc = f"{repo.get('name', '')} {repo.get('description', '')}".lower()

    tech_keywords = {
        "python": "Python",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "nodejs": "Node.js",
        "node": "Node.js",
        "react": "React",
        "fastapi": "FastAPI",
        "django": "Django",
        "flask": "Flask",
        "fastapi": "FastAPI",
        "llm": "LLM",
        "langchain": "LangChain",
        "langgraph": "LangGraph",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "aws": "AWS",
        "postgresql": "PostgreSQL",
        "mongodb": "MongoDB",
        "redis": "Redis",
        "ai": "AI",
        "ml": "Machine Learning",
        "data": "Data Engineering",
    }

    for keyword, tech_name in tech_keywords.items():
        if keyword in name_desc and tech_name not in tech:
            tech.append(tech_name)

    return tech[:5]  # Top 5 techs


def add_project_manual(
    name: str,
    skills: list,
    description: str,
    github_url: str = None,
    email: str = "amankabra.it24@gmail.com"
) -> dict:
    """
    Manually add a project (user can do this anytime).

    Args:
        name: Project name
        skills: List of tech/skills used
        description: Brief description
        github_url: GitHub link (optional)
        email: User email for tracking

    Returns: The added project
    """
    project = {
        "name": name,
        "tech_stack": skills if isinstance(skills, list) else [skills],
        "description": description,
        "github_url": github_url or "",
        "source": "manual",
        "added_by_email": email,
        "added_date": datetime.now().isoformat(),
    }

    # Load existing
    data = load_projects()

    # Check for duplicate
    for existing in data.get("projects", []):
        if existing.get("name", "").lower() == name.lower():
            return {"error": f"Project '{name}' already exists"}

    # Add new project
    data["projects"].append(project)
    data["total"] = len(data["projects"])
    data["last_updated"] = datetime.now().isoformat()

    save_projects(data)
    print(f"  ✓ added project: {name}", flush=True)

    return project


def get_best_project_for_job(job: dict) -> dict:
    """
    Find the BEST project from user's portfolio that matches this job.

    Returns: Project with match score (0-100)
    """
    data = load_projects()
    projects = data.get("projects", [])

    if not projects:
        return {"error": "No projects in portfolio"}

    job_desc = f"{job.get('title', '')} {job.get('description', '')}".lower()

    best_project = None
    best_score = 0

    for project in projects:
        # Score based on tech stack overlap
        score = 0
        for skill in project.get("tech_stack", []):
            if skill.lower() in job_desc:
                score += 25

        # Bonus for name match
        if project.get("name", "").lower() in job_desc:
            score += 25

        if score > best_score:
            best_score = score
            best_project = project

    if best_project:
        best_project["match_score"] = min(best_score, 100)
        return best_project

    # Fallback to most recent
    return max(projects, key=lambda p: p.get("added_date", ""), default={})


def list_projects() -> dict:
    """List all projects in portfolio."""
    return load_projects()
