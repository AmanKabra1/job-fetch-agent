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
    """Extract rich 4-5 line summary from README."""
    if not readme_content:
        return ""

    lines = readme_content.split("\n")
    summary_parts = []
    paragraph_buffer = []

    for i, line in enumerate(lines):
        line = line.strip()

        # Skip empty lines and badges early
        if not line or line.startswith("[![") or line.startswith("!["):
            # If we have buffered content, add it
            if paragraph_buffer and len(summary_parts) < 5:
                summary_parts.append(" ".join(paragraph_buffer))
                paragraph_buffer = []
            continue

        # Skip main title and headings
        if line.startswith("#"):
            if paragraph_buffer and len(summary_parts) < 5:
                summary_parts.append(" ".join(paragraph_buffer))
                paragraph_buffer = []
            continue

        # Skip HTML tags, markdown special syntax
        if line.startswith("<") or line.startswith("|") or line.startswith("-") or line.startswith("*"):
            continue

        # Clean markdown formatting
        line = line.replace("**", "").replace("__", "").replace("_", "").replace("`", "").replace("~~", "")
        line = line.replace("[", "").replace("]", "").replace("(", "").replace(")", "")

        # Skip links that are now empty
        if line:
            paragraph_buffer.append(line)

            # If we have a sentence (ends with period/colon) or buffer is long, add to parts
            if line.endswith((".", ":", "!", "?")) or len(" ".join(paragraph_buffer)) > 120:
                if len(summary_parts) < 5:  # Get up to 5 substantial sentences/lines
                    summary_parts.append(" ".join(paragraph_buffer))
                    paragraph_buffer = []

    # Add any remaining buffer
    if paragraph_buffer and len(summary_parts) < 5:
        summary_parts.append(" ".join(paragraph_buffer))

    # Join with newlines and limit to substantial content
    result = "\n".join(summary_parts[:5])  # Keep up to 5 paragraphs

    # Remove excessive whitespace
    result = " ".join(result.split())

    return result[:1200] if result else ""  # Much longer - 1200 chars = 4-5 full lines


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
