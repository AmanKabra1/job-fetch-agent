# Vercel App Testing Guide - Step by Step

## Prerequisites
- Your Vercel app is deployed at: **https://your-vercel-url.vercel.app**
- Latest code pushed (commit: feat: integrate resume generation and project management)
- Browser: Chrome/Firefox/Edge

---

## TEST 1: View Live Job Feed

### Step 1.1: Open the App
1. Go to your Vercel URL
2. Click **"My Profile"** (not Quick Analysis)
3. You should see:
   - **Header**: "Job Feed - Find Your Next Role"
   - **Filter Dropdown**: Shows "TODAY", "THIS_WEEK", "RECENT", "ALL"
   - **Job Cards**: List of jobs with company, title, location

### Step 1.2: Check Date Categories
1. Look at the dropdown at top
2. Click **"TODAY"** → Should show jobs posted TODAY
3. Click **"THIS_WEEK"** → Should show jobs from last 7 days
4. Click **"RECENT"** → Should show jobs from last 14 days
5. Click **"ALL"** → Should show all 300+ jobs

**Expected:** Each filter shows different job counts

---

## TEST 2: Apply for a Job & Generate Resume

### Step 2.1: Find a Job
1. Go to job feed (TEST 1)
2. Scroll and pick any job card
3. Look for button: **"Apply & Generate Resume"** (blue button at bottom of job card)

### Step 2.2: Click Apply Button
1. Click **"Apply & Generate Resume"**
2. **Loading screen** should appear: "⏳ Generating..."
3. Wait 2-3 seconds

### Step 2.3: See Generated Resume
A modal window pops up with:

**Top section:**
```
ATS: 87/100 ✓ (should be 85+)
```

**Below ATS Score:**
- 📌 **Best Project**: [Project Name shown]
- **Match**: XX% (how well project matches job)

**Skills Section:**
- Matched Skills: Python, FastAPI, Docker, etc.

**Resume Preview:**
- Your name
- Email
- SUMMARY section
- EXPERIENCE section
- PROJECTS section
- SKILLS list

**Buttons at bottom:**
- 📥 Download PDF
- 📋 Copy Text

**Close button:** X in top right corner

### Step 2.4: Test Copy Function
1. Click **"📋 Copy Text"**
2. Should see alert: **"✓ Copied"**
3. Open notepad, paste (Ctrl+V) → Resume text appears

### Step 2.5: Close Modal
1. Click **X button** in top right
2. Or click outside the modal
3. Modal closes, back to job feed

---

## TEST 3: Project Management - Add Manual Project

### Step 3.1: Scroll to Projects Section
1. On main page, scroll DOWN past all jobs
2. You should see:
   ```
   📁 My Projects
   [🔄 Refresh from GitHub button]
   ```

### Step 3.2: Fill Project Form
1. Look for section: **"Add New Project"**
2. Fill in the form:
   - **Project Name**: e.g., "Chat App with NestJS"
   - **Tech Stack**: e.g., "NestJS, TypeScript, PostgreSQL"
   - **Description**: e.g., "Real-time chat application with WebSockets"
   - **GitHub Link**: (optional) https://github.com/...

### Step 3.3: Click Add to Portfolio
1. Click button: **"✅ Add to Portfolio"**
2. Should see alert: **"✓ Project added!"**
3. Form clears automatically

### Step 3.4: See Project in Gallery
1. Scroll down to **"Your Projects"** section
2. Your new project appears as a card:
   ```
   ┌─────────────────────┐
   │ Chat App with NestJS│
   │ Tech: NestJS, Type..│
   │ Real-time chat app..│
   └─────────────────────┘
   ```

---

## TEST 4: Refresh from GitHub

### Step 4.1: Scroll to GitHub Button
1. Scroll down to **"My Projects"** section
2. Find button: **"🔄 Refresh from GitHub"**

### Step 4.2: Click Refresh
1. Click **"🔄 Refresh from GitHub"**
2. Status changes to: **"⏳ Fetching..."**
3. Wait 3-5 seconds
4. Status updates to: **"✓ Fetched X new projects"**

### Step 4.3: See New Projects
1. Scroll down to **"Your Projects"** gallery
2. Your GitHub projects appear (from AmanKabra1 account)
3. Each shows:
   - Project name
   - First 3 tech skills
   - Project description

---

## TEST 5: Apply for Multiple Jobs

### Step 5.1: Generate First Resume
1. Pick Job #1 (e.g., "Node.js Backend Developer")
2. Click **"Apply & Generate Resume"**
3. See Resume Modal #1
4. **Note the project that appears** (e.g., "Job Fetch Agent")
5. Close modal (X button)

### Step 5.2: Generate Second Resume
1. Pick different Job #2 (e.g., "Full Stack Engineer")
2. Click **"Apply & Generate Resume"**
3. See Resume Modal #2
4. **Project may be different!** (e.g., "Chat Application")
5. Check ATS score is still 85+

### Step 5.3: Verify State Management
- Resumes should be different for different jobs
- NO data from Job #1 should appear in Job #2
- ATS scores should both be 85+
- **Status**: ✅ State is clean between operations

---

## TEST 6: ATS Score Accuracy

### Step 6.1: Generate Resume
1. Apply for any job
2. Note the **ATS Score** shown

### Step 6.2: Check Score Details
- **Green badge** = 85+/100 (Excellent)
- **Orange badge** = 70-84 (Good)
- **Red badge** = <70 (Fair)

### Step 6.3: Expected Scores
- Tailored resumes: **85-90/100** ✓
- Good match jobs: **87-92/100** ✓
- All should be 85+ minimum

---

## TEST 7: Matched Skills Display

### Step 7.1: Apply for Job
1. Pick a job with clear tech stack
2. Generate resume

### Step 7.2: Look for Matched Skills
Below the ATS score, you should see:
```
Matched Skills: Python, FastAPI, Docker, REST API, PostgreSQL
```

These are skills extracted from the job description that match your resume.

### Step 7.3: Verify Accuracy
- Should show 3-8 skills from the job
- Should all be backend/technical skills
- Should NOT show irrelevant skills

---

## TEST 8: Resume Structure Integrity

### Step 8.1: Generate Resume
1. Apply for a job
2. Open resume modal

### Step 8.2: Check Structure (SHOULD NEVER CHANGE)
- ✅ Your name stays the same
- ✅ Your email stays the same
- ✅ Your phone stays the same
- ✅ Your location stays the same
- ✅ Education section stays the same
- ✅ Experience dates stay the same

### Step 8.3: Check What CAN Change
- ✓ Summary (tailored to job)
- ✓ Projects (swapped if 40%+ match)
- ✓ Skills (updated based on job)
- ✓ Experience title (matches job title)

### Step 8.4: Verify 1-Page Limit
1. Copy resume text (Copy Text button)
2. Paste in Google Docs or Word
3. Should fit on 1 page when printed

---

## TEST 9: Mobile Responsiveness

### Step 9.1: Open on Mobile
1. On iPhone/Android, go to same Vercel URL
2. Should see:
   - Jobs in mobile-friendly cards
   - Apply button visible
   - Projects section scrollable

### Step 9.2: Test Modal on Mobile
1. Click Apply button
2. Resume modal should:
   - Take up most of screen
   - Have scroll if needed
   - Close button (X) visible
   - Copy/Download buttons visible

---

## TEST 10: Error Handling

### Step 10.1: Test with Bad Input
1. Go to "Add New Project" form
2. Leave **Project Name** empty
3. Click "Add to Portfolio"
4. Should see error: "Project name is required"

### Step 10.2: Test Missing Tech Stack
1. Fill project name only
2. Leave **Tech Stack** empty
3. Click "Add to Portfolio"
4. Should see error: "Tech stack is required"

---

## QUICK CHECKLIST

Print this out and check as you test:

```
TEST 1: Job Feed & Filters
  [ ] Page loads with job cards
  [ ] TODAY filter shows jobs
  [ ] THIS_WEEK filter shows jobs
  [ ] RECENT filter shows jobs
  [ ] ALL shows 300+ jobs

TEST 2: Apply & Resume
  [ ] Apply button visible on jobs
  [ ] Clicking opens modal
  [ ] ATS score shows (85+)
  [ ] Best project displayed
  [ ] Matched skills shown
  [ ] Copy button works
  [ ] Close button works

TEST 3: Add Project Manually
  [ ] Form visible and fields work
  [ ] Can enter project name
  [ ] Can enter tech stack
  [ ] Can enter description
  [ ] Can add GitHub link
  [ ] Clicking "Add" shows success
  [ ] Project appears in gallery

TEST 4: GitHub Refresh
  [ ] Refresh button visible
  [ ] Shows loading state
  [ ] Fetches projects
  [ ] Shows count: "✓ Fetched X new"
  [ ] Projects appear in gallery

TEST 5: Multiple Resumes
  [ ] Job #1 resume generates
  [ ] Job #2 resume generates
  [ ] Different projects may show
  [ ] No data mixing between jobs
  [ ] Both ATS scores 85+

TEST 6: ATS Scores
  [ ] All resumes show 85+ score
  [ ] Green badge for 85+
  [ ] Scores are realistic
  [ ] Scores match job difficulty

TEST 7: No Structure Breaking
  [ ] Name never changes
  [ ] Email never changes
  [ ] Education never changes
  [ ] Only skills/projects/summary change
  [ ] Resume fits 1 page

OVERALL STATUS: [ ] All tests pass - Ready for production!
```

---

## Troubleshooting

### Issue: Apply button not working
**Solution**: 
1. Refresh page (F5)
2. Check browser console (F12 → Console tab)
3. Look for red errors
4. Report any errors seen

### Issue: Resume modal won't load
**Solution**:
1. Check internet connection
2. Wait 5 seconds (API might be slow)
3. Try different job
4. Check if api_handlers.py is running on backend

### Issue: Projects not showing
**Solution**:
1. Refresh page
2. Click "Refresh from GitHub" button
3. Check if you have projects in GitHub account
4. Manually add a project via form

### Issue: ATS score is low (<85)
**Solution**: This shouldn't happen for tailored resumes
1. Refresh and try again
2. Try different job
3. Check that job description is complete
4. If still low, there may be API issue

---

## Success Criteria ✅

Your Vercel app is **FULLY WORKING** when:

1. ✅ All job feed filters work (TODAY/THIS_WEEK/RECENT/ALL)
2. ✅ Clicking "Apply" generates resume in 2-3 seconds
3. ✅ ATS score always shows 85+ for tailored resumes
4. ✅ Best project matches job requirements
5. ✅ Can add projects manually via form
6. ✅ Can fetch projects from GitHub
7. ✅ Projects appear in portfolio gallery
8. ✅ Multiple resumes don't interfere with each other
9. ✅ Resume text copies to clipboard
10. ✅ Mobile layout looks good

**When all 10 pass: Your app is ready to use! 🎉**
