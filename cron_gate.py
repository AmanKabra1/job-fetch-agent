"""
Cron gate for .github/workflows/daily-jobs.yml.

Why this exists: GitHub's free scheduler starts scheduled runs HOURS late (measured 4.5-6.8 h
late on every run, with 0 min queue time — the delay is in GitHub's dispatch, not ours), and
moving the cron minutes only moves the problem. So the workflow now wakes up every 30 minutes
(cheap: this script costs a few seconds) and this gate decides whether a real fetch is DUE:

  * There are exactly 3 daily slots at the worldwide job-posting peaks (UTC):
        03:43 (09:13 IST)  India business day + Europe morning
        09:43 (15:13 IST)  India afternoon + Europe midday
        16:13 (21:43 IST)  US morning-to-midday peak (largest posting window)
  * A slot is DUE when its time has passed and the feed branch has not been published since.
    => each slot fetches once, as soon as ANY wake-up after it arrives (max ~30 min late once
       GitHub is delivering events), and never more than 3 fetches/day (the token budget).
  * If a fetch FAILS the gate retries, but at most MAX_FAILED_ATTEMPTS per slot, so a broken
    run can never burn tokens in a loop.
  * Manual runs (workflow_dispatch) always go through.

Outputs `run=true|false` and `reason=...` to $GITHUB_OUTPUT (and prints them).
Usage in CI:   python cron_gate.py
Local check:   python cron_gate.py --explain
"""

import datetime as dt
import json
import os
import subprocess
import sys

SLOTS_UTC = [(3, 43), (9, 43), (16, 13)]      # keep in sync with the comment in daily-jobs.yml
MAX_FAILED_ATTEMPTS = 2
IST = dt.timedelta(hours=5, minutes=30)


def latest_slot(now: dt.datetime) -> dt.datetime:
    """Most recent slot time <= now (UTC)."""
    best = None
    for day in (-1, 0):
        base = (now + dt.timedelta(days=day)).replace(second=0, microsecond=0)
        for h, m in SLOTS_UTC:
            s = base.replace(hour=h, minute=m)
            if s <= now and (best is None or s > best):
                best = s
    return best


def decide(now: dt.datetime, last_publish: dt.datetime, failed_since_slot: int, event: str = "schedule"):
    """Pure decision (unit-tested): returns (run: bool, reason: str)."""
    if event == "workflow_dispatch":
        return True, "manual run"
    slot = latest_slot(now)
    slot_ist = (slot + IST).strftime("%H:%M IST")
    if last_publish >= slot:
        return False, f"slot {slot_ist} already published ({last_publish.strftime('%H:%M')} UTC)"
    if failed_since_slot >= MAX_FAILED_ATTEMPTS:
        return False, f"slot {slot_ist}: {failed_since_slot} failed attempts already — not retrying (token cap)"
    late = round((now - slot).total_seconds() / 60)
    return True, f"slot {slot_ist} is due (not published yet, {late} min after the slot)"


def _last_publish() -> dt.datetime:
    """Commit time of the feed branch tip = when jobs.json was last published."""
    for ref in ("origin/feed", "feed"):
        out = subprocess.run(["git", "log", "-1", "--format=%ct", ref], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return dt.datetime.fromtimestamp(int(out.stdout.strip()), dt.timezone.utc)
    return dt.datetime.fromtimestamp(0, dt.timezone.utc)


def _failed_since(slot: dt.datetime) -> int:
    """Failed runs of this workflow created since the slot (needs `gh` + actions:read)."""
    try:
        out = subprocess.run(
            ["gh", "run", "list", "--workflow", "daily-jobs.yml", "--status", "failure", "--limit", "20",
             "--json", "createdAt"], capture_output=True, text=True, timeout=60)
        if out.returncode != 0:
            return 0
        n = 0
        for r in json.loads(out.stdout or "[]"):
            c = dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            if c >= slot:
                n += 1
        return n
    except Exception:
        return 0


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    event = os.environ.get("GITHUB_EVENT_NAME", "schedule")
    # explicit refspec so refs/remotes/origin/feed is always updated (shallow CI checkout)
    subprocess.run(["git", "fetch", "--depth=1", "origin", "+feed:refs/remotes/origin/feed"], capture_output=True)
    last = _last_publish()
    slot = latest_slot(now)
    run, reason = decide(now, last, _failed_since(slot) if event != "workflow_dispatch" else 0, event)
    print(f"gate: run={run} | {reason}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"run={'true' if run else 'false'}\nreason={reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
