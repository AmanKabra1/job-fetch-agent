"""
Vercel entrypoint.

Vercel's @vercel/python builder serves the ASGI `app` exported here. We force
JOBS_SOURCE=feed so the dashboard reads jobs from the committed data/jobs.json
(refreshed by the GitHub Actions cron, already matched to your saved resume)
instead of scraping the boards — which Vercel's datacenter IPs can't do. The
"Fetch live jobs" button still works here via the free REST APIs (api_only).

The repo root is added to sys.path so we can import the shared app.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JOBS_SOURCE", "feed")

from app import app  # noqa: E402  (ASGI app picked up by Vercel)
