"""Load existing jobs from feed branch into data/jobs.json before fetch."""
import os
import json
import subprocess

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "data", "jobs.json")

try:
    # Fetch feed branch
    subprocess.run(["git", "fetch", "origin", "feed"], capture_output=True)

    # Get jobs.json from feed branch
    result = subprocess.run(
        ["git", "show", "origin/feed:data/jobs.json"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0 and result.stdout:
        # Parse and save
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        data = json.loads(result.stdout)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        print(f"✓ Loaded {len(data.get('jobs', []))} existing jobs from feed branch")
    else:
        print("! Feed branch not found or empty, will start fresh")

except Exception as e:
    print(f"! Error loading feed: {e}")
