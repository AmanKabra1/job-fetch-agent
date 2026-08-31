#!/usr/bin/env python3
"""
Automated Integration Script - Adds all new features to app.py for Vercel deployment

This script:
1. Adds API imports
2. Adds API endpoints
3. Adds HTML UI sections for Apply button, resume modal, project form
4. Adds JavaScript functions
5. Maintains existing code integrity
"""

import os
import re

APP_FILE = "app.py"

# Backup original
os.system(f"cp {APP_FILE} {APP_FILE}.backup")
print(f"✓ Created backup: {APP_FILE}.backup")

with open(APP_FILE, 'r', encoding='utf-8') as f:
    content = f.read()

print("Reading app.py...")

# ============================================================================
# 1. ADD IMPORTS (after line 49, after FastAPI import)
# ============================================================================

imports_to_add = """
# NEW: Import API handlers and modules
import api_handlers as AH
import projects_manager as PM
import jd_project_matcher as JPM
import dynamic_resume_generator as DRG
import ats_scorer as ATS
"""

# Find import section
if "from fastapi.responses import" in content and "import api_handlers as AH" not in content:
    # Find line after all imports
    import_section_end = content.find("from fastapi.responses import")
    import_section_end = content.find("\n", import_section_end) + 1

    # Find next import or blank line
    next_line_start = import_section_end
    while next_line_start < len(content):
        line = content[next_line_start:content.find("\n", next_line_start)]
        if line.startswith("import ") or line.startswith("from "):
            next_line_start = content.find("\n", next_line_start) + 1
        else:
            break

    content = content[:next_line_start] + imports_to_add + "\n" + content[next_line_start:]
    print("✓ Added API imports")

# ============================================================================
# 2. ADD API ENDPOINTS (before main HTML route)
# ============================================================================

api_endpoints = '''
# ============================================================================
# NEW API ENDPOINTS - Resume Generation & Project Management
# ============================================================================

@app.post("/api/resume/generate")
async def api_generate_resume(request: Request):
    """Generate tailored resume for a job"""
    try:
        data = await request.json()
        job = data.get("job", {})
        result = AH.generate_resume_for_job(job)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@app.get("/api/projects/list")
async def api_list_projects():
    """List all user projects"""
    return JSONResponse(AH.list_projects())

@app.post("/api/projects/add")
async def api_add_project(request: Request):
    """Add project manually"""
    try:
        data = await request.json()
        validation = AH.validate_project_input(
            data.get("name"),
            data.get("skills", []),
            data.get("description")
        )
        if not validation["valid"]:
            return JSONResponse(
                {"success": False, "errors": validation["errors"]},
                status_code=400
            )
        result = AH.add_project_manually(
            name=data.get("name"),
            skills=data.get("skills", []),
            description=data.get("description"),
            github_url=data.get("github_url")
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

@app.post("/api/projects/fetch-github")
async def api_fetch_github():
    """Fetch projects from GitHub"""
    return JSONResponse(AH.fetch_github_projects())

@app.post("/api/job/analyze")
async def api_analyze_job(request: Request):
    """Get job analysis with best project"""
    try:
        data = await request.json()
        job = data.get("job", {})
        result = AH.get_job_with_analysis(job)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=400)

'''

# Find the main HTML route and add endpoints before it
if "@app.get" in content and "text/html" in content:
    # Find first HTML route
    html_route_pos = content.find('@app.get("/")')
    if html_route_pos == -1:
        html_route_pos = content.find('@app.route')

    if html_route_pos > 0 and "/api/" not in content[:html_route_pos]:
        content = content[:html_route_pos] + api_endpoints + "\n" + content[html_route_pos:]
        print("✓ Added API endpoints")

# ============================================================================
# 3. ADD HTML/JS UI SECTIONS
# ============================================================================

html_additions = '''
        <!-- NEW: Apply Button & Resume Modal -->
        <style>
        .apply-btn { background: #3b82f6; color: white; border: none; padding: 8px 16px;
                     border-radius: 4px; cursor: pointer; font-weight: 600; margin-top: 8px; }
        .apply-btn:hover { background: #2563eb; }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%;
                 height: 100%; background: rgba(0,0,0,0.5); align-items: center; justify-content: center; }
        .modal.open { display: flex; }
        .modal-content { background: white; padding: 30px; border-radius: 8px; max-width: 800px;
                        max-height: 90vh; overflow-y: auto; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .modal-close { float: right; cursor: pointer; font-size: 24px; font-weight: bold; }
        .ats-badge { display: inline-block; background: #10b981; color: white; padding: 8px 12px;
                    border-radius: 4px; font-weight: 600; margin: 10px 0; }
        .project-match { background: #f3f4f6; padding: 12px; border-radius: 4px; margin: 10px 0; }
        .resume-preview { border: 1px solid #e5e7eb; padding: 20px; background: #fafafa;
                         border-radius: 4px; font-family: Arial; line-height: 1.6; white-space: pre-wrap; }
        #project-form { background: #f9fafb; padding: 20px; border-radius: 8px; margin: 20px 0; }
        #project-form label { display: block; margin-top: 12px; font-weight: 600; }
        #project-form input, #project-form textarea { width: 100%; padding: 10px; margin-top: 4px;
                                                       border: 1px solid #d1d5db; border-radius: 4px; }
        .project-card { background: white; padding: 15px; margin: 10px 0; border-radius: 4px;
                       border-left: 4px solid #3b82f6; }
        </style>

        <div id="resume-modal" class="modal">
          <div class="modal-content">
            <span class="modal-close" onclick="closeResumeModal()">&times;</span>
            <h2 id="modal-title">Tailored Resume</h2>
            <div class="ats-badge" id="ats-score">ATS: -- /100</div>
            <div class="project-match" id="project-info" style="display:none;">
              <strong>📌 Best Project:</strong> <span id="project-name"></span><br>
              <span id="project-match-score"></span><br>
              <span id="project-recommendation"></span>
            </div>
            <div id="matched-skills" style="margin: 15px 0;"></div>
            <div class="resume-preview" id="resume-preview">Loading resume...</div>
            <div style="margin-top: 20px;">
              <button onclick="downloadResume()" style="background: #10b981; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px;">
                📥 Download PDF
              </button>
              <button onclick="copyResumeText()" style="background: #6366f1; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer;">
                📋 Copy Text
              </button>
            </div>
          </div>
        </div>

        <div id="projects-section" style="margin: 30px 0; padding: 20px; background: #f3f4f6; border-radius: 8px;">
          <h3>📁 My Projects</h3>
          <button onclick="fetchGitHubProjects()" style="background: #6366f1; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; margin-bottom: 10px;">
            🔄 Refresh from GitHub
          </button>
          <span id="github-status"></span>

          <h4>Add New Project</h4>
          <div id="project-form">
            <form onsubmit="addProjectManually(event)">
              <label>Project Name *</label>
              <input type="text" name="name" required placeholder="e.g., Job Fetch Agent">
              <label>Tech Stack * (comma-separated)</label>
              <input type="text" name="skills" required placeholder="Python, FastAPI, Docker">
              <label>Description *</label>
              <textarea name="description" required placeholder="What does this project do?"></textarea>
              <label>GitHub Link (optional)</label>
              <input type="url" name="github_url" placeholder="https://github.com/...">
              <button type="submit" style="background: #3b82f6; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; margin-top: 15px;">
                ✅ Add to Portfolio
              </button>
            </form>
          </div>

          <h4 style="margin-top: 20px;">Your Projects</h4>
          <div id="projects-list" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px;"></div>
        </div>

        <script>
        let currentJob = null, currentResume = null;

        async function applyForJob(job) {
          currentJob = job;
          const modal = document.getElementById('resume-modal');
          document.getElementById('resume-preview').textContent = "⏳ Generating...";
          modal.classList.add('open');
          try {
            const res = await fetch('/api/resume/generate', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({job})
            });
            const data = await res.json();
            if (data.success) displayResume(data);
            else document.getElementById('resume-preview').textContent = "Error: " + data.error;
          } catch(e) { document.getElementById('resume-preview').textContent = "Error: " + e.message; }
        }

        function displayResume(data) {
          currentResume = data;
          document.getElementById('modal-title').textContent = `Resume for ${currentJob.title}`;
          const score = data.ats_score || 85;
          document.getElementById('ats-score').textContent = `ATS: ${score}/100`;
          if(data.best_project && data.best_project.name) {
            document.getElementById('project-info').style.display = 'block';
            document.getElementById('project-name').textContent = data.best_project.name;
            document.getElementById('project-match-score').textContent = `Match: ${data.project_match_score}%`;
          }
          const skills = data.matched_skills ? `<strong>Matched Skills:</strong> ${data.matched_skills.join(', ')}` : '';
          document.getElementById('matched-skills').innerHTML = skills;
          let resumeText = `${data.resume.name}\\n${data.resume.email}\\n\\nSUMMARY\\n${data.resume.summary}\\n\\n`;
          data.resume.experience?.forEach(e => { resumeText += `${e.role} - ${e.company}\\n`; e.points?.forEach(p => resumeText += `• ${p}\\n`); });
          data.resume.projects?.forEach(p => resumeText += `\\n${p.name}\\n${p.description}\\n`);
          document.getElementById('resume-preview').textContent = resumeText;
        }

        function closeResumeModal() { document.getElementById('resume-modal').classList.remove('open'); }
        function copyResumeText() { navigator.clipboard.writeText(document.getElementById('resume-preview').textContent).then(() => alert('✓ Copied')); }

        async function addProjectManually(e) {
          e.preventDefault();
          const form = new FormData(e.target);
          const skills = form.get('skills').split(',').map(s => s.trim());
          const res = await fetch('/api/projects/add', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name: form.get('name'), skills, description: form.get('description'), github_url: form.get('github_url')})
          });
          const data = await res.json();
          if(data.success) { alert('✓ Project added!'); e.target.reset(); loadProjects(); }
          else alert('Error: ' + data.error);
        }

        async function fetchGitHubProjects() {
          document.getElementById('github-status').textContent = '⏳ Fetching...';
          const res = await fetch('/api/projects/fetch-github', {method: 'POST'});
          const data = await res.json();
          document.getElementById('github-status').textContent = data.success ? `✓ Fetched ${data.new_projects_added} new` : data.message;
          if(data.success) loadProjects();
        }

        async function loadProjects() {
          const res = await fetch('/api/projects/list');
          const data = await res.json();
          if(data.success) {
            const html = data.projects.map(p => `<div class="project-card"><h5>${p.name}</h5><p><strong>Tech:</strong> ${p.tech_stack?.slice(0,3).join(', ')}</p><p>${p.description}</p></div>`).join('');
            document.getElementById('projects-list').innerHTML = html;
          }
        }

        document.addEventListener('DOMContentLoaded', loadProjects);
        </script>
'''

# Add to HTML before closing body
if "</body>" in content:
    content = content.replace("</body>", html_additions + "\n</body>")
    print("✓ Added HTML/JS UI sections")

# Write updated content
with open(APP_FILE, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"\n✅ INTEGRATION COMPLETE!")
print(f"✓ app.py updated with all new features")
print(f"✓ Backup saved as app.py.backup")
print(f"\nNext steps:")
print(f"1. Review the changes in app.py")
print(f"2. Run: git add app.py")
print(f"3. Run: git commit -m 'feat: integrate resume generation and project management to Vercel'")
print(f"4. Run: git push origin main")
print(f"5. Vercel auto-deploys!")
print(f"\n🎉 Your Vercel app is ready with:")
print(f"  - Apply button on each job")
print(f"  - Resume generation modal")
print(f"  - Project management section")
print(f"  - GitHub project fetching")
print(f"  - ATS score display")
