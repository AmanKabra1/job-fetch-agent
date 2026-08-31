# Complete System Flow - Start to End

## 1️⃣ PROJECT CURATION (Your Local Machine)

```
Your 40+ GitHub Repos
        ↓
  [project_curator.py]
        ↓
  Score Each Project:
  - Description quality (35 pts)
  - Recency (30 pts)
  - Stars (25 pts)
  - Language (10 pts)
        ↓
  Filter (Score >= 50)
        ↓
  Top 6-10 Candidates
        ↓
  You add with custom descriptions
        ↓
  [data/projects.json] - 29 Best Projects
```

---

## 2️⃣ DAILY JOB FETCHING (GitHub Cron - 3x/day)

```
         CRON TRIGGER (8am, 12pm, 4pm)
                ↓
    [fetch_jobs.py] on GitHub
                ↓
    Fetch from 8+ job boards:
    - LinkedIn
    - Indeed  
    - Google Jobs
    - Glassdoor
    - ZipRecruiter
    - Naukri
    - Bayt
    - Career pages
                ↓
    Filter by keywords:
    ✓ Node.js, NestJS, Full Stack
    ✓ Backend roles
    ✓ 7-9 LPA salary
    ✓ 1-2 years experience
                ↓
    Keep 300+ fresh jobs
                ↓
    [feed branch] → data/jobs.json
                ↓
    Ready for Vercel to read
```

---

## 3️⃣ USER OPENS APP (Vercel)

```
         Browser opens:
    https://job-fetch-agent.vercel.app
                ↓
         Page loads
                ↓
    [Load Latest Jobs] button click
                ↓
    App reads: data/jobs.json (300+ jobs)
                ↓
    Display jobs organized by date:
    ┌─────────────────────┐
    │ TODAY (2 jobs)      │
    │ THIS_WEEK (15 jobs) │
    │ RECENT (80 jobs)    │
    │ OLD (200+ jobs)     │
    └─────────────────────┘
```

---

## 4️⃣ USER CLICKS "Apply & Generate Resume"

```
    User selects a job
         ↓
    Click: "Apply & Generate Resume"
         ↓
    Frontend sends: job title + description
         ↓
    [POST /api/apply/kit]
         ↓
    ┌──────────────────────────────┐
    │  BACKEND PROCESSING          │
    └──────────────────────────────┘
                ↓
    1. LOAD PROJECTS
       Load all 29 projects from: data/projects.json
                ↓
    2. FIND BEST PROJECT
       [jd_project_matcher.py]
       
       For each project, score:
       - Tech match (40%): Does it use skills JD needs?
       - Role relevance (30%): Does it match job type?
       - Description quality (20%): How well documented?
       - Recency (10%): Is it recently updated?
                ↓
       Result: Best project + match score (0-100)
       Example: "ai-travel-planner (85%)"
                ↓
    3. CHECK SWAP THRESHOLD
       Is match score >= 75%?
       
       YES → Swap project into resume
       NO  → Keep original project
                ↓
    4. GENERATE TAILORED RESUME
       [dynamic_resume_generator.py]
       
       Modify ONLY:
       - Projects (if 75%+ match)
       - Skills (add JD-specific skills)
       - Keywords (add missing JD terms)
       
       Keep UNCHANGED:
       - Education
       - Work experience dates
       - Resume structure
       - 1-page format
                ↓
    5. CALCULATE ATS SCORE
       [ats_scorer.py]
       
       Score the tailored resume:
       - Match keywords to JD
       - Count skill overlap
       - Guaranteed 85+ for good match
                ↓
    6. GENERATE FILES
       Create PDF + DOCX with:
       - Tailored resume
       - Project swap applied
       - High ATS score guaranteed
                ↓
    7. DRAFT COVER NOTE
       Auto-generate cover letter
       Using matched skills
```

---

## 5️⃣ SHOW RESULTS TO USER (Modal)

```
    [Apply Kit Modal Opens]
    ┌─────────────────────────────────┐
    │ Apply kit — Python Developer    │
    ├─────────────────────────────────┤
    │                                 │
    │ ATS Score: 89/100 (Excellent)  │ ← Green badge
    │                                 │
    │ 📌 Project Matched              │
    │ ai-travel-planner               │
    │ 🔄 Swapped to best match        │
    │ Match Score: 85%                │
    │                                 │
    ├─────────────────────────────────┤
    │ 1. Resume tailored to this job  │
    │    [Download PDF]               │
    │                                 │
    │ 2. Cover note (edit, then copy) │
    │    [Generated cover letter]     │
    │                                 │
    │ 3. Apply on the site            │
    │    [Open job & apply]           │
    └─────────────────────────────────┘
```

---

## 6️⃣ USER TAKES ACTION

```
    User has 3 options:
    
    A) Download Resume
       ✓ Get PDF/DOCX
       ✓ Has swapped project
       ✓ 89+ ATS score
       ✓ Ready to send
            ↓
       Email to recruiter
    
    B) Copy Cover Note
       ✓ Get auto-generated text
       ✓ Edit if needed
       ✓ Paste in email
            ↓
       Send personalized message
    
    C) Apply on the Site
       ✓ Open job posting
       ✓ Upload resume
       ✓ Submit application
```

---

## 7️⃣ PROJECT MATCH EXAMPLES

```
JOB: "Python FastAPI Backend Developer"
   ↓
Top 3 project matches:
   1. ai-travel-planner (92%)
      ✓ Python ✓ APIs ✓ LLM ✓ Recent
   2. job-fetch-agent (88%)
      ✓ Python ✓ FastAPI ✓ APIs
   3. langgraph-chatbot (80%)
      ✓ Python ✓ Production ✓ Integration
   
SELECTED: ai-travel-planner
ACTION: SWAP (92% >= 75%)
RESULT: Resume now highlights travel planner project

---

JOB: "NestJS TypeScript Full Stack"
   ↓
Top 3 project matches:
   1. Shaadi Vidhaan (87%)
      ✓ NestJS ✓ Angular ✓ TypeScript ✓ Full-stack
   2. task-management-api (75%)
      ✓ TypeScript ✓ Express ✓ API design
   3. vendor-management (72%)
      ✓ NestJS ✓ Angular ✓ TypeScript
   
SELECTED: Shaadi Vidhaan
ACTION: SWAP (87% >= 75%)
RESULT: Resume shows wedding planner (similar skills)

---

JOB: "Random Java Job" (doesn't match well)
   ↓
Best match:
   UAT Test Project (50%)
   ⚠ Only "Testing" matches
   
ACTION: KEEP (50% < 75%)
RESULT: Resume keeps original projects
        Still gets 85+ ATS via keywords
```

---

## 8️⃣ ATS SCORE CALCULATION

```
Resume text (with project swapped):
"Backend Developer with Python, FastAPI, PostgreSQL...
 ai-travel-planner: Multi-agent AI system using LangGraph,
 Groq LLaMA 3.3, flight/weather APIs, PostgreSQL..."

JD text:
"We need Python FastAPI developer. Experience with:
 Python, FastAPI, REST APIs, PostgreSQL, LLM integration..."

Keyword matching:
 Python         ✓ Found in both
 FastAPI        ✓ Found in both
 PostgreSQL     ✓ Found in both
 REST APIs      ✓ Found in both
 LLM            ✓ Found in resume (from project!)
 
 Score calculation:
 - Base score: 70
 - Tech match: +15 (5 keywords × 3 pts)
 - Project match: +5 (project has relevant tech)
 - Final: 90/100

Guarantee: Tailored resumes always >= 85
```

---

## 9️⃣ DATA FLOW SUMMARY

```
GitHub Cron (3x/day)          Your Local Machine
┌─────────────────┐           ┌──────────────────┐
│  Fetch 300+ jobs│           │ project_curator  │
│  Filter & rank  │           │ Curate 29 best   │
│  Save to feed   │           │ projects         │
└────────┬────────┘           └────────┬─────────┘
         │                            │
         ▼                            ▼
    [GitHub Feed Branch]      [GitHub Main Branch]
    data/jobs.json            data/projects.json
         │                            │
         └────────────┬───────────────┘
                      │
                      ▼
             [Vercel Deployment]
               
         Frontend (React/HTML)
         ├─ Load Latest Jobs
         ├─ Display 300+ jobs
         └─ Apply & Generate button
         
         Backend (FastAPI)
         ├─ /api/projects/list (29 projects)
         ├─ /api/apply/kit (generate resume)
         ├─ /api/projects/add (add manually)
         └─ /api/projects/fetch-github (refresh)
         
         AI Systems
         ├─ jd_project_matcher (score projects)
         ├─ dynamic_resume_generator (tailor resume)
         ├─ ats_scorer (check ATS compatibility)
         └─ Groq API (when available)
```

---

## 🔟 DECISION TREE - SHOULD SWAP PROJECT?

```
User clicks "Apply" on a job
         │
         ▼
    Load all 29 projects
         │
         ▼
    Score EACH project against JD
    ┌─────────────────────────────┐
    │ Project scoring logic:      │
    │ - Tech match (40%)          │
    │ - Role relevance (30%)      │
    │ - Description quality (20%) │
    │ - Recency (10%)             │
    └─────────────────────────────┘
         │
         ▼
    Find BEST match (highest score)
         │
         ▼
    Is best_project_score >= 75%?
    
    YES ─→ SWAP
    │     └─→ Use best project in resume
    │     └─→ Likely 90+ ATS score
    │     └─→ Show "🔄 Swapped" badge
    │
    NO  ─→ KEEP ORIGINAL
         └─→ Keep existing projects
         └─→ Still 85+ ATS (from keywords)
         └─→ Show "✓ Kept" badge
```

---

## Summary: Complete User Journey

```
START
  ↓
1. User sees 300+ jobs organized by date
  ↓
2. Click job "Python Backend Developer"
  ↓
3. Click "Apply & Generate Resume"
  ↓
4. System:
   - Analyzes job description
   - Scores all 29 projects
   - Picks best match (ai-travel-planner: 85%)
   - Checks 75% threshold → PASS
   - SWAPS project into resume
   - Tailors skills & keywords
   - Calculates ATS: 89/100
   - Generates PDF + DOCX
   - Creates cover letter
  ↓
5. Modal shows:
   - Resume download (PDF/DOCX)
   - Project swapped: ai-travel-planner (85%)
   - ATS Score: 89/100 (Excellent)
   - Cover letter ready to copy
  ↓
6. User choices:
   - Download + send resume
   - Copy + paste cover letter
   - Apply on job website
  ↓
END - Application sent!
```

---

## Key Features Highlighted

✅ **Automatic project matching** - Analyzes all 29 projects
✅ **Smart swapping** - Only if 75%+ confident
✅ **High ATS guaranteed** - 85+ score minimum
✅ **Tailored resume** - Customized for each job
✅ **One-page format** - Never exceeds 1 page
✅ **Cover letter** - Auto-generated, editable
✅ **300+ jobs** - Fresh daily via cron
✅ **Multiple dates** - TODAY, THIS_WEEK, RECENT, OLD
✅ **Project curator** - Filter 40+ repos down to best 6-10
