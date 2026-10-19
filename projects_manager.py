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

GITHUB_USERNAME = "AmanKabra1"
PROJECTS_FILE = Path(__file__).parent / "data" / "projects.json"
# PRIVATE-repo projects live here (gitignored: this repo is PUBLIC, so committing private repo
# names/details would leak them). Set STORE_PRIVATE_IN_REPO=1 to keep them in projects.json instead.
PRIVATE_PROJECTS_FILE = Path(__file__).parent / "data" / "projects_private.json"
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
    """Load all projects (public file + the local private-projects file when present)."""
    _ensure_data_dir()

    if not PROJECTS_FILE.exists():
        data = {"projects": [], "last_updated": None, "source": "none", "total": 0}
    else:
        try:
            with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"projects": [], "last_updated": None, "source": "none", "total": 0}

    if PRIVATE_PROJECTS_FILE.exists():
        try:
            with open(PRIVATE_PROJECTS_FILE, "r", encoding="utf-8") as f:
                pj = json.load(f)
            priv = pj.get("projects", [])
            have = {p.get("name") for p in data.get("projects", [])}
            data["projects"] = data.get("projects", []) + [p for p in priv if p.get("name") not in have]
            data["repo_checks"] = {**data.get("repo_checks", {}), **pj.get("repo_checks", {})}
            data["total"] = len(data["projects"])
        except Exception:
            pass
    return data


def save_projects(projects_data: dict):
    """Save projects. Everything about PRIVATE repos (their projects AND the cached "not a
    project" verdicts, which carry repo names) goes to the gitignored
    data/projects_private.json unless STORE_PRIVATE_IN_REPO=1 - this repo is public."""
    _ensure_data_dir()
    projects = projects_data.get("projects", [])
    keep_in_repo = os.environ.get("STORE_PRIVATE_IN_REPO") == "1"
    checks = projects_data.get("repo_checks") or {}
    private_names = set(projects_data.get("private_repo_names") or []) | {p["name"] for p in projects if p.get("private")}
    if keep_in_repo:
        private_names = set()
    priv = [p for p in projects if p.get("private") and not keep_in_repo]
    pub = [p for p in projects if p not in priv]
    public_data = {k: v for k, v in projects_data.items() if k not in ("private_repo_names", "includes_private")}
    public_data.update(projects=pub, total=len(pub),
                       repo_checks={k: v for k, v in checks.items() if k not in private_names})
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(public_data, f, indent=2)
    if private_names:
        with open(PRIVATE_PROJECTS_FILE, "w", encoding="utf-8") as f:
            json.dump({"projects": priv, "repo_checks": {k: v for k, v in checks.items() if k in private_names},
                       "last_updated": projects_data.get("last_updated")}, f, indent=2)
    elif PRIVATE_PROJECTS_FILE.exists() and projects_data.get("source") == "github":
        PRIVATE_PROJECTS_FILE.unlink()          # full sync found nothing private: drop the stale file


# --------------------------------------------------------------------------- #
# GitHub sync — real projects only, public AND private, with rich details
# --------------------------------------------------------------------------- #
# A repo counts as a project only when the repository really contains one:
#   * a build/dependency manifest (package.json, requirements.txt, pom.xml, go.mod, ...)
#     OR a runnable front-end (several html/js/css files + README + a real description)
#   * enough source files (MIN_SOURCE_FILES), not just a snippet or a single script
#   * a README or a real description
# Excluded with a reason shown to you: empty repos, your profile-README repo, forks,
# framework boilerplate left unchanged (e.g. a bare `nest new`), notebook-only learning
# collections, and generic-name dumps (demo/test/Basic/one/Final...).
#
# For every real project we store what helps win jobs: full tech stack (read from the
# manifests' dependencies + language bytes + topics + README), README summary and feature
# bullets, live-demo URL, Docker / CI / tests flags, commit count, dates, stars and a 0-100
# quality score. PRIVATE repos need a token with `repo` scope (GH_PAT / GITHUB_TOKEN env,
# or — on your own machine only — the `gh` CLI login); see _gh_token().
MIN_SOURCE_FILES = 8
MIN_SOURCE_FILES_SUSPECT = 15      # for boilerplate-looking repos (starter README, generic names)

_SOURCE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".php", ".rb", ".cs",
               ".swift", ".dart", ".c", ".cpp", ".h", ".vue", ".svelte", ".html", ".scss", ".css"}
_CODE_ONLY = _SOURCE_EXT - {".html", ".css", ".scss"}
_MANIFESTS = {"package.json", "requirements.txt", "pyproject.toml", "setup.py", "pipfile", "pom.xml",
              "build.gradle", "build.gradle.kts", "go.mod", "cargo.toml", "composer.json", "gemfile",
              "dockerfile", "docker-compose.yml", "docker-compose.yaml", "angular.json", "nest-cli.json",
              "manage.py", "vercel.json", "next.config.js", "vite.config.ts", "vite.config.js"}
_SKIP_DIRS = ("node_modules/", "dist/", "build/", "vendor/", ".git/", "venv/", ".venv/", "__pycache__/",
              "bower_components/", ".next/", "coverage/", "target/", ".idea/", "env/", "site-packages/")
_SUSPECT_NAME = re.compile(r"^(demo|test|tests|temp|tmp|practice|tutorial|sample|hello|trial|learn|learning|"
                           r"untitled|new[-_ ]?project|first[-_ ]?repo|basic|one|two|final|project|my[-_ ]?project|"
                           r"django\d*|nodejs|node[-_ ]?js|js[-_ ]?njs|regex|webdev|frontback|aman|github[-_ ]?test|"
                           r"combined[-_ ]?\w*|n[-_ ]?fundamental)\w*$", re.I)
_BOILERPLATE_DESC = re.compile(r"circleci-image|img\.shields\.io|a progressive node\.js framework|"
                               r"nest logo|this project was bootstrapped|create react app|getting started with", re.I)
_JUNK_DESC = re.compile(r"^\s*(<|\[!\[|!\[|\d+\.\s|#|>)", re.I)

# dependency name (regex over lower-cased package names) -> canonical tech label
_DEP_MAP = [
    (r"^@nestjs/", "NestJS"), (r"^express$", "Express.js"), (r"^fastify$", "Fastify"),
    (r"^typeorm$", "TypeORM"), (r"^@prisma/|^prisma$", "Prisma"), (r"^sequelize$", "Sequelize"),
    (r"^mongoose$|^mongodb$|^pymongo$|^motor$", "MongoDB"), (r"^pg$|^postgres|psycopg|asyncpg", "PostgreSQL"),
    (r"^mysql2?$|mysqlclient|pymysql|aiomysql", "MySQL"), (r"^ioredis$|^redis$", "Redis"),
    (r"^bullmq$|^bull$|^celery$", "Message Queues"), (r"^kafkajs$|confluent.kafka|^aiokafka$", "Kafka"),
    (r"^amqplib$|^pika$", "RabbitMQ"), (r"^socket\.io|^ws$|websockets?$", "WebSockets"),
    (r"graphql|^apollo", "GraphQL"), (r"jsonwebtoken|passport-jwt|^@nestjs/jwt$|pyjwt|python-jose|^jose$", "JWT Authentication"),
    (r"^passport$|oauth|authlib", "OAuth 2.0"), (r"swagger|openapi", "Swagger/OpenAPI"),
    (r"^jest$|^vitest$|^mocha$|^supertest$|^pytest|^unittest", "Unit Testing"),
    (r"^react$|^react-dom$", "React"), (r"^next$", "Next.js"), (r"^@angular/core$", "Angular"), (r"^vue$", "Vue"),
    (r"^tailwindcss$", "Tailwind CSS"), (r"^stripe$", "Stripe"), (r"^aws-sdk$|^@aws-sdk/|^boto3$", "AWS"),
    (r"^firebase", "Firebase"), (r"^langchain|^@langchain/", "LangChain"), (r"^langgraph|^@langchain/langgraph", "LangGraph"),
    (r"^openai$", "OpenAI API"), (r"^anthropic$|^@anthropic-ai/", "Anthropic API"), (r"^groq$", "Groq"),
    (r"chromadb|faiss|pinecone|qdrant|weaviate|pgvector", "Vector Databases"),
    (r"^transformers$|sentence.transformers", "Hugging Face"), (r"^torch$|^tensorflow$|scikit.learn|^keras$", "Machine Learning"),
    (r"^fastapi$", "FastAPI"), (r"^flask$", "Flask"), (r"^django$|djangorestframework", "Django"),
    (r"^sqlalchemy$|^alembic$", "SQLAlchemy"), (r"^pydantic", "Pydantic"), (r"^uvicorn$|^gunicorn$", "ASGI/WSGI"),
    (r"^pandas$", "Pandas"), (r"^playwright$|^selenium$|^puppeteer$", "Browser Automation"),
    (r"^laravel/framework$", "Laravel"), (r"^livewire/", "Livewire"), (r"^class-validator$|^zod$", "Validation"),
    (r"^multer$|^cloudinary$|^@aws-sdk/client-s3$", "File Uploads / S3"), (r"^nodemailer$|^@sendgrid", "Email Integration"),
    (r"^razorpay$", "Razorpay Payments"), (r"^helmet$|^bcrypt|^argon2", "Security Best Practices"),
]


def _gh_token() -> str:
    """Token used for GitHub calls (public AND private repos).

    Order: GH_PAT (a personal access token with `repo` scope — add it as a repository secret
    for the scheduled sync) > GITHUB_TOKEN (CI's built-in token only sees public data) > on
    your own machine only, the logged-in `gh` CLI for the target account."""
    for k in ("GH_PAT", "GITHUB_TOKEN"):
        if os.environ.get(k):
            return os.environ[k]
    if not os.environ.get("CI"):
        try:
            import subprocess
            out = subprocess.run(["gh", "auth", "token", "--user", GITHUB_USERNAME],
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except Exception:
            pass
    return ""


def _gh_headers(raw: bool = False):
    h = {"Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
         "User-Agent": "job-fetch-agent"}
    tok = _gh_token()
    if tok:
        h["Authorization"] = f"token {tok}"
    return h


def _api(path: str, params=None, raw: bool = False, timeout: int = 20):
    """GET api.github.com/<path>; returns the Response (caller checks status). Raises
    RuntimeError('rate-limited') on 403/429 with an exhausted quota."""
    import requests
    r = requests.get("https://api.github.com" + path, params=params, headers=_gh_headers(raw), timeout=timeout)
    if r.status_code in (403, 429) and r.headers.get("X-RateLimit-Remaining") == "0":
        raise RuntimeError("rate-limited")
    return r


def _inspect_repo(owner: str, repo: dict, tree_paths: list):
    """Return (is_real, reason, facts) from the repo's file list."""
    name = repo.get("name", "")
    paths = [p for p in tree_paths
             if not any(d in ("/" + p.lower()) for d in ("/" + x for x in _SKIP_DIRS))]
    exts = [os.path.splitext(p.lower())[1] for p in paths]
    src = sum(1 for e in exts if e in _SOURCE_EXT)
    code = sum(1 for e in exts if e in _CODE_ONLY)
    manifests = [p for p in paths if os.path.basename(p).lower() in _MANIFESTS and p.count("/") <= 2]
    has_readme = any(os.path.basename(p).lower().startswith("readme") and p.count("/") == 0 for p in paths)
    notebooks = sum(1 for e in exts if e == ".ipynb")
    lower = [p.lower() for p in paths]
    facts = {"source_files": src, "code_files": code, "manifests": sorted({os.path.basename(m) for m in manifests})[:6],
             "has_readme": has_readme, "notebooks": notebooks,
             "has_docker": any(os.path.basename(p) in ("dockerfile", "docker-compose.yml", "docker-compose.yaml") for p in lower),
             "has_ci": any(p.startswith(".github/workflows/") or p in (".gitlab-ci.yml", "jenkinsfile") for p in lower),
             "has_tests": any(re.search(r"(^|/)(tests?|__tests__|spec)(/|$)|\.(test|spec)\.[jt]sx?$|(^|/)test_\w+\.py$", p) for p in lower)}

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
        if suspect and not has_readme:
            return False, "generic-name repo without a README", facts
        return True, "ok", facts
    # No manifest: accept a genuine static/front-end app only
    if code >= 4 and src >= 6 and has_readme and len(desc.strip()) >= 30 and not suspect:
        return True, "ok (front-end app)", facts
    return False, f"no manifest and only {src} source files — looks like snippets, not a project", facts


def _deps_from_manifests(owner: str, repo: str, manifest_paths: list) -> list:
    """Dependency names -> canonical tech labels, read from up to 4 manifests (works for
    private repos via the authenticated contents API)."""
    techs = []
    for path in manifest_paths[:4]:
        base = os.path.basename(path).lower()
        if base not in ("package.json", "requirements.txt", "pyproject.toml", "composer.json", "pipfile"):
            continue
        try:
            r = _api(f"/repos/{owner}/{repo}/contents/{path}", raw=True)
            if r.status_code != 200:
                continue
            text = r.text
        except RuntimeError:
            raise
        except Exception:
            continue
        names = []
        if base in ("package.json", "composer.json"):
            try:
                j = json.loads(text)
                for k in ("dependencies", "devDependencies", "require", "require-dev"):
                    names += list((j.get(k) or {}).keys())
                if j.get("devDependencies", {}).get("typescript") or j.get("dependencies", {}).get("typescript"):
                    techs.append("TypeScript")
                if base == "package.json":
                    techs.append("Node.js")
            except Exception:
                pass
        else:
            names = re.findall(r"^[ \t]*([A-Za-z0-9_.\-]+)", text, re.M)
            if base != "requirements.txt":
                names += re.findall(r'["\']([A-Za-z0-9_.\-]+)[><=~! \[]', text)
            techs.append("Python")
        for n in names:
            n = n.lower().strip()
            for pat, label in _DEP_MAP:
                if re.search(pat, n):
                    techs.append(label)
    return list(dict.fromkeys(techs))


def _readme_details(owner: str, repo: str) -> dict:
    """README -> a clean summary + feature bullets (private repos included)."""
    try:
        r = _api(f"/repos/{owner}/{repo}/readme", raw=True)
        text = r.text if r.status_code == 200 else ""
    except RuntimeError:
        raise
    except Exception:
        text = ""
    if not text:
        return {"summary": "", "features": [], "text": ""}
    try:
        from fetch_github_descriptions import extract_readme_summary
        summary = extract_readme_summary(text)
    except Exception:
        summary = ""
    features, in_feat = [], False
    for line in text.splitlines():
        if re.match(r"^#{1,4}\s*(key\s+)?(features?|highlights?|what it does|functionality|capabilities)\b", line, re.I):
            in_feat = True
            continue
        if in_feat and re.match(r"^#{1,4}\s", line):
            in_feat = False
        if in_feat:
            m = re.match(r"^\s*[-*•]\s+(.*\S)", line)
            if m:
                f = re.sub(r"[*_`]|\[([^\]]*)\]\([^)]*\)", lambda mm: mm.group(1) or "", m.group(1)).strip()
                if 12 <= len(f) <= 200:
                    features.append(f)
    return {"summary": summary, "features": features[:6], "text": text[:20000]}


def _languages(owner: str, repo: str) -> list:
    try:
        r = _api(f"/repos/{owner}/{repo}/languages")
        if r.status_code != 200:
            return []
        d = r.json()
        total = sum(d.values()) or 1
        return [l for l, b in sorted(d.items(), key=lambda x: -x[1]) if b / total >= 0.05][:4]
    except RuntimeError:
        raise
    except Exception:
        return []


def _commit_count(owner: str, repo: str) -> int:
    try:
        r = _api(f"/repos/{owner}/{repo}/commits", params={"per_page": 1})
        if r.status_code != 200:
            return 0
        m = re.search(r'[?&]page=(\d+)>; rel="last"', r.headers.get("Link", ""))
        return int(m.group(1)) if m else len(r.json())
    except RuntimeError:
        raise
    except Exception:
        return 0


def _quality_score(f: dict, extra: dict) -> int:
    """0-100: how strong a showcase the repo is (used to prefer it when several match a job)."""
    s = 0
    s += min(25, f.get("source_files", 0) // 4)
    s += 15 if f.get("has_readme") else 0
    s += 10 if f.get("has_docker") else 0
    s += 10 if f.get("has_ci") else 0
    s += 10 if f.get("has_tests") else 0
    s += 10 if extra.get("homepage") else 0
    s += min(10, extra.get("commits", 0) // 5)
    s += 5 if len(extra.get("features", [])) >= 3 else 0
    s += 5 if len(extra.get("tech_stack", [])) >= 5 else 0
    return min(100, s)


def _build_project(owner: str, repo: dict, tree_paths: list, facts: dict, prior: dict) -> dict:
    name = repo["name"]
    manifests_full = [p for p in tree_paths if os.path.basename(p).lower() in
                      ("package.json", "requirements.txt", "pyproject.toml", "composer.json", "pipfile")
                      and p.count("/") <= 2 and not any(d in ("/" + p.lower()) for d in ("/" + x for x in _SKIP_DIRS))]
    deps = _deps_from_manifests(owner, name, manifests_full)
    langs = _languages(owner, name)
    rd = _readme_details(owner, name)
    commits = _commit_count(owner, name)

    # README-mentioned technologies (LLM, RAG, LangGraph, Docker, ...) via the resume keyword lexicon
    readme_tech = []
    try:
        import resume_keywords as K
        blob = f"{repo.get('description') or ''} {rd['text']}"
        for canon, _w in K.jd_keywords(blob):
            if K.LEX[canon][2] in ("lang", "fw", "data", "cloud", "ai"):
                readme_tech.append(canon)
    except Exception:
        pass
    topics = [t.replace("-", " ").title() for t in (repo.get("topics") or [])]
    if facts.get("has_docker"):
        deps.append("Docker")
    if facts.get("has_ci"):
        deps.append("CI/CD")
    tech = list(dict.fromkeys(deps + langs + readme_tech + topics))[:14]

    desc = (repo.get("description") or "").strip()
    if not desc or _JUNK_DESC.match(desc) or _BOILERPLATE_DESC.search(desc):
        desc = rd["summary"] or ("" if (not desc or _JUNK_DESC.match(desc)) else desc)
    private = bool(repo.get("private"))
    extra = {"homepage": (repo.get("homepage") or "").strip(), "commits": commits,
             "features": rd["features"], "tech_stack": tech}
    project = {
        **{k: v for k, v in prior.items() if k in ("bullets", "tailored_bullets", "tailored_description")},
        "name": name,
        "description": desc,
        "summary": rd["summary"],
        "features": rd["features"],
        # private repos: never print a link recruiters cannot open
        "github_url": "" if private else repo.get("html_url", ""),
        "private_repo_url": repo.get("html_url", "") if private else "",
        "private": private,
        "live_url": extra["homepage"],
        "language": repo.get("language", ""),
        "languages": langs,
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "created": repo.get("created_at", ""),
        "updated": repo.get("pushed_at") or repo.get("updated_at", ""),
        "commits": commits,
        "source": "github",
        "tech_stack": tech,
        "quality": _quality_score(facts, extra),
        "repo_facts": facts,
        "v": 3,
    }
    return project


def sync_github_projects(username: str = None) -> dict:
    """ONE call does everything the button needs: list your repos (public AND private when a
    token with `repo` scope is available), keep only the real projects, read their details,
    MERGE with what is saved (manual projects are never dropped) and report what is new /
    skipped. Unchanged repos (same pushed_at) reuse their saved details, so only new or
    changed repos cost GitHub API calls (~7 each)."""
    username = username or GITHUB_USERNAME
    token = _gh_token()
    repos, page, authed = [], 1, False
    if token:
        try:
            me = _api("/user").json().get("login", "")
            authed = me.lower() == username.lower()
        except Exception:
            authed = False
    while True:
        if authed:
            r = _api("/user/repos", params={"affiliation": "owner", "visibility": "all",
                                            "per_page": 100, "page": page, "sort": "pushed"})
        else:
            r = _api(f"/users/{username}/repos", params={"sort": "updated", "per_page": 100,
                                                         "page": page, "type": "owner"})
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
    checks = dict(old.get("repo_checks", {}))          # name -> {pushed_at, real, reason, v}
    old_by_name = {p.get("name"): p for p in old_projects}
    old_github_names = {p.get("name") for p in old_projects if p.get("source") == "github"}

    kept, skipped, errors = [], [], []
    rate_limited = False
    for repo in repos:
        name = repo.get("name", "")
        if repo.get("fork"):
            continue
        if name.lower() == username.lower():
            skipped.append({"name": name, "reason": "your profile README repo"}); continue
        if repo.get("size", 1) == 0:
            skipped.append({"name": name, "reason": "empty repository"}); continue
        pushed = repo.get("pushed_at", "")
        prev = checks.get(name)
        prior = old_by_name.get(name, {})
        cached = (prev and prev.get("pushed_at") == pushed and prev.get("v") == 3
                  and (not prev.get("real") or (prior.get("v") == 3 and prior.get("private") == bool(repo.get("private")))))
        if cached:
            if not prev["real"]:
                skipped.append({"name": name, "reason": prev["reason"], "private": bool(repo.get("private"))}); continue
            kept.append(prior); continue
        if rate_limited:
            skipped.append({"name": name, "reason": "not checked (GitHub rate limit — set GH_PAT/GITHUB_TOKEN)"}); continue
        try:
            branch = repo.get("default_branch") or "main"
            tr = _api(f"/repos/{username}/{name}/git/trees/{branch}", params={"recursive": 1}, timeout=30)
            if tr.status_code in (404, 409):
                paths = []
            else:
                tr.raise_for_status()
                paths = [t["path"] for t in tr.json().get("tree", []) if t.get("type") == "blob"]
            real, reason, facts = _inspect_repo(username, repo, paths)
            checks[name] = {"pushed_at": pushed, "real": real, "reason": reason, "v": 3}
            if not real:
                skipped.append({"name": name, "reason": reason, "private": bool(repo.get("private"))}); continue
            kept.append(_build_project(username, repo, paths, facts, prior))
        except RuntimeError:
            rate_limited = True
            skipped.append({"name": name, "reason": "not checked (GitHub rate limit — set GH_PAT/GITHUB_TOKEN)"})
        except Exception as e:
            errors.append(f"{name}: {str(e)[:80]}")

    kept_names = {p["name"] for p in kept}
    # manual projects always survive; GitHub projects that no longer qualify are dropped
    manual = [p for p in old_projects if p.get("source") != "github"
              and p.get("name") not in kept_names and p.get("name") != "UAT Test Project"]
    # best showcase first
    kept.sort(key=lambda p: p.get("updated", ""), reverse=True)           # newest first...
    kept.sort(key=lambda p: -(p.get("quality") or 0))                       # ...then strongest showcase first (stable)
    projects = kept + manual
    new_names = [p["name"] for p in kept if p["name"] not in old_github_names]
    removed = sorted(old_github_names - kept_names - {s["name"] for s in skipped if "not checked" in s["reason"]})

    data = {"projects": projects, "last_updated": datetime.now().isoformat(),
            "source": "github", "total": len(projects), "repo_checks": checks,
            "private_repo_names": [r["name"] for r in repos if r.get("private")],
            "includes_private": authed, "private_count": sum(1 for p in projects if p.get("private"))}
    return {"data": data, "new": new_names, "removed": removed, "skipped": skipped,
            "errors": errors, "rate_limited": rate_limited, "repos_seen": len(repos),
            "authed": authed}


def fetch_github_projects(username: str = None, force: bool = False) -> list:
    """Back-compat wrapper returning the verified GitHub projects.

    force=False keeps the old 14-day throttle for scripted callers; the dashboard button
    calls sync_github_projects() directly (a button press always fetches)."""
    if not force and not _should_fetch_github():
        print("  ! GitHub fetch skipped (last fetch <14 days ago)", flush=True)
        return []
    try:
        res = sync_github_projects(username)
        save_projects(res["data"])
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
