"""
Self-keeping scheduler for .github/workflows/keepalive.yml.

Problem: GitHub's free `schedule:` trigger is unreliable for this repo — it starts runs hours
late or skips slots entirely (a 09:43 UTC slot never fired on 2026-11-16). A `workflow_dispatch`
made from inside a workflow IS delivered promptly, so this script is the clock instead:

  * It runs for ~5h40m (GitHub kills jobs at 6h), checking every CHECK_EVERY seconds whether a
    posting-peak slot is due, using the SAME decision as cron_gate.py (slot passed + feed not
    published since + failed-attempt cap). If due and no fetch is already running, it dispatches
    daily-jobs.yml with source=cron (the fetch workflow's own gate re-checks, so a duplicate
    dispatch can never cause a second fetch).
  * The workflow then starts its own replacement, so the clock never stops. Anything that wakes
    daily-jobs.yml also revives it if it is not running (see "Ensure keepalive" step there).

Usage in CI:  python keepalive.py
Local check:  python keepalive.py --once --dry-run
"""

import datetime as dt
import json
import subprocess
import sys
import time

import cron_gate as G

RUN_FOR = dt.timedelta(hours=5, minutes=40)
CHECK_EVERY = 300          # seconds between checks
AFTER_DISPATCH = 600       # seconds to wait after dispatching (let the fetch start)
FETCH_WORKFLOW = "daily-jobs.yml"


def _gh(*args, timeout=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)


def fetch_busy() -> bool:
    """True when a fetch run is already queued / running (never stack another)."""
    try:
        out = _gh("run", "list", "--workflow", FETCH_WORKFLOW, "--limit", "10", "--json", "status")
        if out.returncode != 0:
            return False
        return any(r.get("status") in ("queued", "in_progress", "waiting", "pending")
                   for r in json.loads(out.stdout or "[]"))
    except Exception:
        return False


def due_now(now: dt.datetime):
    subprocess.run(["git", "fetch", "--depth=1", "origin", "+feed:refs/remotes/origin/feed"],
                   capture_output=True)
    last = G._last_publish()
    return G.decide(now, last, G._failed_since(G.latest_slot(now)), "schedule")


def dispatch() -> bool:
    out = _gh("workflow", "run", FETCH_WORKFLOW, "-f", "source=cron")
    if out.returncode != 0:
        print(f"keepalive: dispatch FAILED: {out.stderr.strip()[:200]}", flush=True)
    return out.returncode == 0


def main() -> int:
    once = "--once" in sys.argv
    dry = "--dry-run" in sys.argv
    started = dt.datetime.now(dt.timezone.utc)
    print(f"keepalive: started {started:%Y-%m-%d %H:%M} UTC, will run until "
          f"{(started + RUN_FOR):%H:%M} UTC", flush=True)
    while True:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            run, reason = due_now(now)
        except Exception as e:                       # never die on a transient error
            run, reason = False, f"gate error: {e}"
        wait = CHECK_EVERY
        if run:
            if fetch_busy():
                reason += " — but a fetch is already queued/running"
            elif dry:
                reason += " — DRY RUN, not dispatching"
            elif dispatch():
                reason += " — dispatched daily-jobs.yml"
                wait = AFTER_DISPATCH
        print(f"keepalive {now:%H:%M} UTC: {reason}", flush=True)
        if once or (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=wait) - started) >= RUN_FOR:
            break
        time.sleep(wait)
    return 0


if __name__ == "__main__":
    sys.exit(main())
