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
import re
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
    return days_since_last_sync() >= FETCH_INTERVAL_DAYS


def days_since_last_sync() -> float:
    """Days since the portfolio was last synced from GitHub — by the scheduled job OR by
    pressing the button. Read from data/projects.json's `last_updated` (it is committed, so
    it survives the ephemeral CI runner; the old .projects_fetch_log file did not)."""
    stamp = None
    try:
        with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("source") == "github" or data.get("repo_checks"):
            stamp = data.get("last_updated")
    except Exception:
        pass
    if not stamp and FETCH_LOG_FILE.exists():
        try:
            stamp = FETCH_LOG_FILE.read_text().strip()
        except Exception:
            pass
    if not stamp:
        return 9999.0
    try:
        return (datetime.now() - datetime.fromisoformat(stamp)).total_seconds() / 86400
    except Exception:
        return 9999.0


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


# --------------------------------------------------------------------------- #
# GitHub sync — only REAL projects
# --------------------------------------------------------------------------- #
# A repo counts as a project only when the repository really contains one:
#   * a build/dependency manifest (package.json, requirements.txt, pom.xml, go.mod, ...)
#     OR a runnable front-end (several html/js/css files + README + a real description)
#   * enough source files (MIN_SOURCE_FILES), not just a snippet or a single script
#   * a README or a real description
# Excluded with a reason shown to you: empty repos, your profile-README repo, forks,
# framework boilerplate left unchanged (e.g. a bare `nest new`), notebook-only learning
# collections, and demo/test/practice dumps.
MIN_SOURCE_FILES = 8
MIN_SOURCE_FILES_SUSPECT = 15      # for boilerplate-looking repos (starter README, demo/test names)

_SOURCE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".php", ".rb", ".cs",
               ".swift", ".dart", ".c", ".cpp", ".h", ".vue", ".svelte", ".html", ".scss", ".css"}
_CODE_ONLY = _SOURCE_EXT - {".html", ".css", ".scss"}
_MANIFESTS = {"package.json", "requirements.txt", "pyproject.toml", "setup.py", "pipfile", "pom.xml",
              "build.gradle", "build.gradle.kts", "go.mod", "cargo.toml", "composer.json", "gemfile",
              "dockerfile", "docker-compose.yml", "docker-compose.yaml", "angular.json", "nest-cli.json",
              "manage.py", "vercel.json", "next.config.js", "vite.config.ts", "vite.config.js"}
_SKIP_DIRS = ("node_modules/", "dist/", "build/", "vendor/", ".git/", "venv/", ".venv/", "__pycache__/",
              "bower_components/", ".next/", "coverage/", "target/", ".idea/")
_SUSPECT_NAME = re.compile(r"^(demo|test|tests|temp|tmp|practice|tutorial|sample|hello|trial|learn|learning|"
                           r"untitled|new[-_ ]?project|first[-_ ]?repo)\w*$", re.I)
_BOILERPLATE_DESC = re.compile(r"circleci-image|img\.shields\.io|a progressive node\.js framework|"
                               r"nest logo|this project was bootstrapped|create react app|getting started with", re.I)
_JUNK_DESC = re.compile(r"^\s*(<|\[!\[|!\[|\d+\.\s|#|>)", re.I)


def _gh_headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "job-fetch-agent"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"token {tok}"
    return h


def _inspect_repo(owner: str, repo: dict, headers: dict):
    """Return (is_real, reason, facts) for one repo by reading its file tree."""
    import requests
    name = repo.get("name", "")
    branch = repo.get("default_branch") or "main"
    r = requests.get(f"https://api.github.com/repos/{owner}/{name}/git/trees/{branch}?recursive=1",
                     headers=headers, timeout=20)
    if r.status_code in (403, 429):
        raise RuntimeError("rate-limited")
    if r.status_code == 409 or r.status_code == 404:        # empty repository / no such branch
        return False, "empty repository (no files)", {}
    r.raise_for_status()
    tree = [t for t in r.json().get("tree", []) if t.get("type") == "blob"]
    paths = [t["path"] for t in tree
             if not any(d in ("/" + t["path"].lower()) for d in ("/" + x for x in _SKIP_DIRS))]
    exts = [os.path.splitext(p.lower())[1] for p in paths]
    src = sum(1 for e in exts if e in _SOURCE_EXT)
    code = sum(1 for e in exts if e in _CODE_ONLY)
    manifests = [p for p in paths if os.path.basename(p).lower() in _MANIFESTS and p.count("/") <= 2]
    has_readme = any(os.path.basename(p).lower().startswith("readme") and p.count("/") == 0 for p in paths)
    notebooks = sum(1 for e in exts if e == ".ipynb")
    facts = {"source_files": src, "code_files": code, "manifests": [os.path.basename(m) for m in manifests][:4],
             "has_readme": has_readme, "notebooks": notebooks}

    desc = repo.get("description") or ""
    learning = bool(re.search(r"\b(for learning|learning (?:project|repo)|collection of|tutorial|practice|"
                              r"exercises|playground|hands-on)\b", desc, re.I))
    # 3+ notebooks = a learning / experiments collection, held to the stricter bar
    suspect = bool(_SUSPECT_NAME.match(name) or _BOILERPLATE_DESC.search(desc) or learning or notebooks >= 3)
    need = MIN_SOURCE_FILES_SUSPECT if suspect else MIN_SOURCE_FILES

    if not paths:
        return False, "empty repository (no files)", facts
    if notebooks and not manifests and code < MIN_SOURCE_FILES:
        return False, "notebook/learning collection (no app, no manifest)", facts
    if manifests:
        if src < need:
            why = "learning/starter/boilerplate repo" if suspect else "too little code"
            return False, f"{why} ({src} source files, needs {need}+)", facts
        if not (has_readme or len(desc.strip()) >= 20):
            return False, "no README and no description", facts
        return True, "ok", facts
    # No manifest: accept a genuine static/front-end app only
    if code >= 4 and src >= 6 and has_readme and len(desc.strip()) >= 30 and not suspect:
        return True, "ok (front-end app)", facts
    return False, f"no manifest and only {src} source files — looks like snippets, not a project", facts


def _clean_description(repo: dict, owner: str) -> str:
    """GitHub 'description' is often empty or a pasted badge/README line; fall back to the
    README summary in that case."""
    desc = (repo.get("description") or "").strip()
    if desc and not _JUNK_DESC.match(desc) and not _BOILERPLATE_DESC.search(desc):
        return desc
    try:
        from fetch_github_descriptions import fetch_github_readme
        got = fetch_github_readme(repo.get("html_url", ""))
        if got and not _BOILERPLATE_DESC.search(got):
            return got
    except Exception:
        pass
    return "" if (not desc or _JUNK_DESC.match(desc)) else desc


def sync_github_projects(username: str = "AmanKabra1") -> dict:
    """ONE call does everything the button needs: list public repos, keep only the real
    projects, MERGE with what is saved (manual projects are never dropped), and report what
    is new / skipped. Unchanged repos (same pushed_at) reuse their earlier check, so only
    new or changed repos cost GitHub API calls."""
    import requests
    headers = _gh_headers()
    repos, page = [], 1
    while True:
        r = requests.get(f"https://api.github.com/users/{username}/repos",
                         params={"sort": "updated", "per_page": 100, "page": page, "type": "owner"},
                         headers=headers, timeout=20)
        r.raise_for_status()
        chunk = r.json()
        if not chunk:
            break
        repos += chunk
        if len(chunk) < 100:
            break
        page += 1

    old = load_projects()
    old_projects = old.get("projects", [])
    checks = dict(old.get("repo_checks", {}))          # name -> {pushed_at, real, reason}
    old_by_name = {p.get("name"): p for p in old_projects}
    old_github_names = {p.get("name") for p in old_projects if p.get("source") == "github"}

    kept, skipped, errors = [], [], []
    rate_limited = False
    for repo in repos:
        name = repo.get("name", "")
        if repo.get("fork") or repo.get("private"):
            continue
        if name.lower() == username.lower():
            skipped.append({"name": name, "reason": "your profile README repo"}); continue
        if repo.get("size", 1) == 0:
            skipped.append({"name": name, "reason": "empty repository"}); continue
        pushed = repo.get("pushed_at", "")
        prev = checks.get(name)
        if prev and prev.get("pushed_at") == pushed and prev.get("v") == 2:
            real, reason, facts = prev["real"], prev["reason"], prev.get("facts", {})
        else:
            if rate_limited:
                skipped.append({"name": name, "reason": "not checked (GitHub rate limit — set GITHUB_TOKEN)"}); continue
            try:
                real, reason, facts = _inspect_repo(username, repo, headers)
                checks[name] = {"pushed_at": pushed, "real": real, "reason": reason, "facts": facts, "v": 2}
            except RuntimeError:
                rate_limited = True
                skipped.append({"name": name, "reason": "not checked (GitHub rate limit — set GITHUB_TOKEN)"}); continue
            except Exception as e:
                errors.append(f"{name}: {str(e)[:60]}")
                continue
        if not real:
            skipped.append({"name": name, "reason": reason}); continue

        prior = old_by_name.get(name, {})
        project = {
            **{k: v for k, v in prior.items() if k not in ("name",)},     # keep bullets etc. you already generated
            "name": name,
            "description": prior.get("description") if prior.get("source") == "github" and len(prior.get("description") or "") > 40
                           else _clean_description(repo, username),
            "github_url": repo.get("html_url", ""),
            "language": repo.get("language", ""),
            "stars": repo.get("stargazers_count", 0),
            "updated": repo.get("pushed_at") or repo.get("updated_at", ""),
            "source": "github",
            "tech_stack": _extract_tech_from_repo(repo),
            "repo_facts": facts,
        }
        kept.append(project)

    kept_names = {p["name"] for p in kept}
    # manual projects always survive; GitHub projects that no longer qualify are dropped
    manual = [p for p in old_projects if p.get("source") != "github"
              and p.get("name") not in kept_names and p.get("name") != "UAT Test Project"]
    projects = kept + manual
    new_names = [p["name"] for p in kept if p["name"] not in old_github_names]
    removed = sorted(old_github_names - kept_names)

    data = {"projects": projects, "last_updated": datetime.now().isoformat(),
            "source": "github", "total": len(projects), "repo_checks": checks}
    return {"data": data, "new": new_names, "removed": removed, "skipped": skipped,
            "errors": errors, "rate_limited": rate_limited, "repos_seen": len(repos)}


def fetch_github_projects(username: str = "AmanKabra1", force: bool = False) -> list:
    """Back-compat wrapper returning the verified GitHub projects.

    force=False keeps the old 14-day throttle for scripted callers; the dashboard button
    calls sync_github_projects() directly (a button press always fetches)."""
    if not force and not _should_fetch_github():
        print("  ! GitHub fetch skipped (last fetch <14 days ago)", flush=True)
        return []
    try:
        res = sync_github_projects(username)
        _log_fetch()
        return [p for p in res["data"]["projects"] if p.get("source") == "github"]
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
