"""
Project Curator - Helps select best GitHub repos for portfolio.

1. Fetches ALL repos from GitHub
2. Scores them by: quality, recency, stars, description, language
3. Shows TOP candidates for manual curation
4. User adds custom descriptions
"""

import os
import json
from datetime import datetime, timedelta
import requests

GITHUB_USER = "AmanKabra1"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def fetch_all_repos() -> list:
    """Fetch ALL repos from GitHub (max 100 per page, paginate)."""
    print(f"\n[*] Fetching all repos for {GITHUB_USER}...", flush=True)

    all_repos = []
    page = 1
    per_page = 100

    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    while True:
        url = f"https://api.github.com/users/{GITHUB_USER}/repos?sort=updated&per_page={per_page}&page={page}"

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            repos = response.json()

            if not repos:
                break  # No more repos

            all_repos.extend(repos)
            print(f"  [][][] Page {page}: {len(repos)} repos", flush=True)
            page += 1

        except Exception as e:
            print(f"  [][][][][][]  Error fetching page {page}: {e}", flush=True)
            break

    print(f"  [][][][] Total repos found: {len(all_repos)}\n", flush=True)
    return all_repos


def score_repo(repo: dict) -> dict:
    """
    Score a repo for portfolio quality (0-100).

    Scoring:
    - Has description (20 pts)
    - Description length >50 chars (15 pts)
    - Updated < 3 months (20 pts)
    - Updated < 6 months (10 pts)
    - Has stars (15 pts)
    - 5+ stars (10 pts)
    - Backend relevant languages (10 pts)
    """
    score = 0
    reasons = []

    # 1. DESCRIPTION (35 pts max)
    description = repo.get("description", "") or ""
    if description:
        score += 20
        reasons.append("[][][] Has description")
        if len(description) > 50:
            score += 15
            reasons.append("[][][] Good description length")

    # 2. RECENCY (30 pts max)
    updated_at = repo.get("updated_at", "")
    if updated_at:
        updated_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        days_old = (datetime.now(updated_date.tzinfo) - updated_date).days

        if days_old < 90:  # < 3 months
            score += 20
            reasons.append(f"[][][] Recent update ({days_old} days)")
        elif days_old < 180:  # < 6 months
            score += 10
            reasons.append(f"[][][] Fairly recent ({days_old} days)")
        else:
            reasons.append(f"[][][][][][]  Outdated ({days_old} days)")

    # 3. STARS (25 pts max)
    stars = repo.get("stargazers_count", 0) or 0
    if stars > 0:
        score += 15
        reasons.append(f"[][][] {stars} stars")
        if stars >= 5:
            score += 10
            reasons.append("[][][] Good popularity (5+ stars)")

    # 4. LANGUAGE (10 pts max)
    language = repo.get("language", "")
    backend_langs = ["Python", "JavaScript", "TypeScript", "Java", "Go", "Rust", "PHP"]
    if language in backend_langs:
        score += 10
        reasons.append(f"[][][] Backend lang: {language}")

    # PENALTIES
    if repo.get("fork"):
        score -= 20
        reasons.append("[][][] Fork (not original)")

    if repo.get("private"):
        score -= 50
        reasons.append("[][][] Private (can't showcase)")

    final_score = max(0, min(score, 100))

    return {
        "name": repo.get("name", ""),
        "url": repo.get("html_url", ""),
        "language": language,
        "description": description,
        "stars": stars,
        "updated": updated_at,
        "score": final_score,
        "reasons": reasons,
        "fork": repo.get("fork", False),
        "private": repo.get("private", False),
    }


def curate_projects(min_score: int = 50) -> list:
    """
    Main curation flow:
    1. Fetch all repos
    2. Score each one
    3. Return top candidates (score >= min_score)
    """
    repos = fetch_all_repos()

    # Score all repos
    scored = []
    for repo in repos:
        scored.append(score_repo(repo))

    # Sort by score (highest first)
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Filter by minimum score
    candidates = [r for r in scored if r["score"] >= min_score]

    print(f"\n[][][][] SCORING RESULTS:")
    print(f"  Total repos: {len(repos)}")
    print(f"  Score >= {min_score}: {len(candidates)} candidates")
    print(f"  Score < {min_score}: {len(scored) - len(candidates)} skipped\n")

    print(f"[][][][] TOP PROJECT CANDIDATES (for portfolio):\n")

    for i, proj in enumerate(candidates[:15], 1):  # Show top 15
        print(f"{i}. {proj['name']} ({proj['score']}/100)")
        print(f"   Language: {proj['language'] or 'N/A'} | Stars: {proj['stars']} | Recency: {proj['updated'][:10] if proj['updated'] else 'N/A'}")
        print(f"   Desc: {proj['description'][:70] if proj['description'] else '[NO DESCRIPTION]'}...")
        for reason in proj['reasons'][:3]:
            print(f"   {reason}")
        print()

    return candidates


if __name__ == "__main__":
    candidates = curate_projects(min_score=50)

    # Save to file
    output = {
        "timestamp": datetime.now().isoformat(),
        "total_candidates": len(candidates),
        "candidates": candidates[:20]  # Top 20
    }

    with open("project_candidates.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n[][][] Saved {len(candidates[:20])} candidates to project_candidates.json")
