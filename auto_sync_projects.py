"""
Scheduled GitHub -> portfolio sync (run by .github/workflows/projects-sync.yml).

Runs the SAME real-projects-only sync the dashboard button uses, but only when the portfolio
is older than 14 days (a manual button press also resets that clock). Writes
data/projects.json; the workflow commits it to main when it changed, which redeploys the site.

    python auto_sync_projects.py            # sync only if >= 14 days since the last sync
    python auto_sync_projects.py --force    # sync now
"""

import sys

import projects_manager as PM


def main(force: bool = False) -> int:
    age = PM.days_since_last_sync()
    if not force and age < PM.FETCH_INTERVAL_DAYS:
        print(f"Portfolio synced {age:.1f} days ago (< {PM.FETCH_INTERVAL_DAYS}) — nothing to do.")
        return 0
    print(f"Syncing GitHub projects (last sync: {'never' if age > 9000 else f'{age:.1f} days ago'}) ...", flush=True)
    res = PM.sync_github_projects("AmanKabra1")
    if res["rate_limited"] and not res["data"]["projects"]:
        print("GitHub rate limit hit before any repo was checked — keeping the saved list.")
        return 1
    PM.save_projects(res["data"])
    print(f"  {len(res['data']['projects'])} real projects | new: {res['new'] or '-'} | "
          f"removed: {res['removed'] or '-'} | skipped {len(res['skipped'])}")
    for s in res["skipped"]:
        print(f"    skipped {s['name']}: {s['reason']}")
    for e in res["errors"]:
        print(f"    ! {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--force" in sys.argv))
