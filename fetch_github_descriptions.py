"""
Fetch full project descriptions from GitHub README files.
Extracts meaningful content from each project's GitHub repo to enrich project descriptions.
"""

import json
import os
from pathlib import Path

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

PROJECTS_FILE = Path(__file__).parent / "data" / "projects.json"


def extract_readme_summary(readme_content: str) -> str:
    """Extract meaningful summary from README (skip badges, titles, etc)."""
    if not readme_content:
        return ""

    lines = readme_content.split("\n")
    summary_lines = []
    skip_next = False

    for line in lines:
        line = line.strip()

        # Skip badges, shields, images
        if line.startswith("[![") or line.startswith("![") or not line:
            continue

        # Skip main title (first # heading)
        if line.startswith("# ") and len(summary_lines) == 0:
            continue

        # Skip TOC
        if "Table of Contents" in line or "## " in line[:4]:
            if skip_next:
                break
            skip_next = True
            continue

        # Get meaningful content
        if line and not line.startswith("#"):
            # Clean up markdown
            line = line.replace("**", "").replace("_", "").replace("`", "")
            summary_lines.append(line)

            # Get 2-4 meaningful lines (4-5 sentences worth)
            if len(summary_lines) >= 4:
                break

    return " ".join(summary_lines)[:500]  # Max 500 chars


def fetch_github_readme(github_url: str) -> str:
    """Fetch README from GitHub using raw.githubusercontent.com."""
    if not github_url or not REQUESTS_AVAILABLE:
        return ""

    try:
        # Parse GitHub URL: https://github.com/user/repo
        parts = github_url.rstrip("/").split("/")
        if len(parts) < 5:
            return ""

        user = parts[-2]
        repo = parts[-1]

        # Try main first, then master
        for branch in ["main", "master"]:
            url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/README.md"
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200 and response.text:
                    return extract_readme_summary(response.text)
            except:
                continue

        return ""

    except Exception as e:
        print(f"  [!] Error fetching {github_url}: {str(e)[:50]}")
        return ""


def enrich_projects_with_descriptions():
    """Fetch and add GitHub descriptions to projects."""
    if not PROJECTS_FILE.exists():
        print("! projects.json not found")
        return False

    if not REQUESTS_AVAILABLE:
        print("! requests library not available, install: pip install requests")
        return False

    print("\n[*] Fetching full project descriptions from GitHub...")

    try:
        with open(PROJECTS_FILE, "r") as f:
            data = json.load(f)

        projects = data.get("projects", [])
        updated_count = 0

        for i, proj in enumerate(projects, 1):
            github_url = proj.get("github_url", "")
            current_desc = proj.get("description", "")

            # Skip if already has good description or no GitHub URL
            if current_desc and len(current_desc) > 80:
                print(f"  [{i}/{len(projects)}] {proj.get('name', '?')}: Already has description")
                continue

            if not github_url:
                print(f"  [{i}/{len(projects)}] {proj.get('name', '?')}: No GitHub URL")
                continue

            print(f"  [{i}/{len(projects)}] Fetching: {proj.get('name', '?')}...", end=" ")

            # Fetch README
            readme_desc = fetch_github_readme(github_url)

            if readme_desc:
                proj["description"] = readme_desc
                updated_count += 1
                print(f"[OK] ({len(readme_desc)} chars)")
            else:
                print("[SKIP] (no README)")

        # Save updated projects
        with open(PROJECTS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        print(f"\n[+] Updated {updated_count} projects with GitHub descriptions")
        return True

    except Exception as e:
        print(f"[-] Error: {e}")
        return False


if __name__ == "__main__":
    import sys
    success = enrich_projects_with_descriptions()
    sys.exit(0 if success else 1)
