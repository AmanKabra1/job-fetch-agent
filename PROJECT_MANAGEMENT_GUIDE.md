# Project Management Guide - Aman Kabra

## How to Manage Your 28 Projects

### **1. GitHub Auto-Fetch (SAFE - Once per 2 weeks)**

**Automatic:**
```
Every 2 weeks, system checks GitHub (AmanKabra1)
  ↓
If new projects added:
  → Download them
  → Save to data/projects.json
  → Update memory
  
If no new projects:
  → Skip (NO API hit - safe!)
```

**Manual Trigger (anytime, but respects 2-week limit):**
```bash
python fetch_my_projects.py
```
OR from Vercel UI (when built):
- Go to Resume tab
- Click "Refresh Projects from GitHub"
- System: Checks if 2 weeks passed
  - If YES: Fetches new projects
  - If NO: Shows "Check back in X days"

---

### **2. Manual Project Input (ANYTIME)**

**Format to provide:**
```
Project Name: [name]
Tech Stack: [skill1, skill2, skill3]
Description: [1-2 sentences about what it does]
GitHub Link: [https://github.com/AmanKabra1/project-name] (optional)
```

**Example:**
```
Project Name: Job Fetch Agent
Tech Stack: Python, FastAPI, LLM, LangChain, GitHub Actions, Groq
Description: Multi-source job aggregator fetching 300+ daily jobs. Uses AI to rank jobs by interview likelihood and generates tailored resumes with ATS 85+ scores.
GitHub Link: https://github.com/AmanKabra1/job-fetch-agent
```

**How to add (when Vercel UI ready):**
1. Go to Resume tab → "Add Project" button
2. Fill form with above info
3. Click "Add to Portfolio"
4. Project saved instantly (no API call)
5. Available for resume generation immediately

---

### **3. Resume Generation - Project Logic**

When you paste a JD or click "Apply":

**Step 1: Match project to JD**
```
System finds best project from your 28
  ↓
Calculates match score (0-100)
```

**Step 2: Project Action Logic**
```
IF match score >= 40%:
  ✓ SWAP in best project
  ✓ Update project bullets to match JD
  ✓ Example: "Built task management API" → "Implemented REST APIs for vendor management"

IF match score < 40%:
  ✗ DON'T force swap
  ✓ KEEP original project (e.g., job-fetch-agent)
  ✓ Focus on keyword/skill matching
  ✓ Ensure ATS 85+ anyway
  
  Example:
    Job: "Blockchain Developer" (you do Backend)
    No projects match blockchain (0%)
    → Keep job-fetch-agent as-is
    → Update keywords to mention relevant tech
    → ATS still 85+
```

**Step 3: Resume Structure (NOT BROKEN)**
```
❌ NEVER swap:
  - Header (name, email, phone)
  - Contact info
  - Education
  - Overall layout

✓ ONLY change:
  - Projects section (project name, tech, description)
  - Skills list (add/remove specific skills)
  - Summary (tailor to job role)
  - Experience bullets (make job-relevant)

✓ ALWAYS maintain:
  - 1-page limit
  - Same formatting
  - Same structure
  - Same order of sections
```

---

### **4. Complete Resume Generation Flow**

```
User provides: Job OR JD
        ↓
System calls: get_best_project_for_jd()
        ↓
MATCH ANALYSIS:
  Best match found? Score it (0-100)
        ↓
IF score >= 40%:
  → Action: "Swapped in [project name]"
  → Resume gets: New project info
  → ATS boost: +5-15 points
ELSE:
  → Action: "Kept original project (no good match)"
  → Resume gets: Same project, keyword focus
  → ATS boost: +2-5 points (keyword matching)
        ↓
System calls: generate_tailored_resume()
        ↓
Resume generation:
  1. Swap project (if match >= 40%)
  2. Update skills to match JD
  3. Regenerate experience bullets
  4. Keep structure intact (1 page)
        ↓
System calls: score_resume_for_jd()
        ↓
ATS Scoring:
  - Base score from structure: 60-70
  - Keyword match bonus: +10-20
  - Generated resume bonus: +10
  - ENSURE: Result >= 85 ✓
        ↓
Output to user:
  ✅ Tailored resume (PDF/DOCX)
  ✅ ATS score: 85+
  ✅ Project action: "Swapped" OR "Kept"
  ✅ Match score: 92%
```

---

### **5. Your Current Portfolio (28 Projects)**

**Top candidates for swaps:**
1. **job-fetch-agent** - Python, AI, Backend (most versatile)
2. **ai-travel-planner** - LangGraph, AI, Full-stack
3. **langgraph-chatbot** - LLM, RAG, Python
4. **task-management-api** - REST, MongoDB, TypeScript
5. **vendor-management** - NestJS, Full-stack, Auth

**Low-match scenarios where original is kept:**
- Blockchain jobs → Keep job-fetch-agent (0% blockchain match)
- DevOps jobs → Keep best available (DevOps not your focus)
- Mobile jobs → Keep task-management-api (0% mobile match)

---

### **6. Clear State When Done**

**When JD cleared / New job started:**
```
✓ Reset ATS score (doesn't show old number)
✓ Clear matched skills list
✓ Clear project suggestion
✓ Clear tailored resume
✓ Ready for next job
```

---

## **FAQ**

**Q: What if I have a new project on GitHub but the 2-week auto-fetch hasn't run yet?**
A: You can:
1. Wait for auto-fetch (2 weeks max)
2. OR manually add it using "Add Project" form
3. Manual add works immediately (no waiting)

**Q: What if a job needs C++/Blockchain and I have no matching projects?**
A: System keeps your best project and focuses on keywords. ATS still 85+ because it's well-formatted + your core skills are there.

**Q: Can I have 2 projects in one resume?**
A: Currently keeps 1 best-fit project (1-page limit). If needed, can highlight 1-2 projects in experience bullets instead.

**Q: How do I know if a project was swapped or kept?**
A: Resume shows:
- "Project action: Swapped in vendor-management (92% match)"
- "Project action: Kept job-fetch-agent (no good match - 15%)"

---

## **Your Contact for Updates**
Email: amankabra.it24@gmail.com
GitHub: https://github.com/AmanKabra1
