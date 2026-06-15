"""
Vercel entrypoint.

Vercel's @vercel/python builder serves the ASGI `app` exported here. We force
JOBS_SOURCE=sheet so the dashboard reads jobs from your Google Sheet instead of
trying to scrape (which Vercel IPs can't do reliably).

The repo root is added to sys.path so we can import the shared app.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("JOBS_SOURCE", "sheet")

from app import app  # noqa: E402  (ASGI app picked up by Vercel)
