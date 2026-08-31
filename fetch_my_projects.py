#!/usr/bin/env python
"""Fetch Aman's projects from GitHub and save to portfolio."""

import projects_manager as pm

print("Fetching your GitHub projects (AmanKabra1)...", flush=True)
projects = pm.fetch_github_projects("AmanKabra1")

if projects:
    data = {
        "projects": projects,
        "last_updated": pm.datetime.now().isoformat(),
        "source": "github",
        "total": len(projects)
    }
    pm.save_projects(data)

    print(f"\n✅ Portfolio updated with {len(projects)} projects:\n", flush=True)
    for i, p in enumerate(projects, 1):
        print(f"{i}. {p['name']}", flush=True)
        print(f"   Tech: {', '.join(p['tech_stack'][:5])}", flush=True)
        if p.get('description'):
            print(f"   Desc: {p['description'][:60]}...", flush=True)
        print()
else:
    print("❌ No projects fetched", flush=True)
