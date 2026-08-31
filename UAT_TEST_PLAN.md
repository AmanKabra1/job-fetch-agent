# UAT Test Plan - First Level Testing

## Test Coverage

### 1. Project Management Tests
- [ ] Fetch projects from GitHub
- [ ] Validate project data
- [ ] Manually add project
- [ ] List all projects
- [ ] Verify project storage

### 2. Job Fetching Tests
- [ ] Verify 300+ jobs fetched
- [ ] Check date categorization (TODAY/THIS_WEEK/RECENT)
- [ ] Verify filtering removes old jobs (>14 days)
- [ ] Check job deduplication
- [ ] Verify all job fields present

### 3. Job Analysis Tests
- [ ] Verify Groq scores jobs (0-100)
- [ ] Check fit levels assigned
- [ ] Verify interview likelihood calculation
- [ ] Test edge cases (short descriptions, etc.)

### 4. Project Matching Tests
- [ ] Match projects to sample jobs
- [ ] Verify match scoring (0-100)
- [ ] Test 40%+ swap threshold
- [ ] Test no-match scenario (keep original)

### 5. Resume Generation Tests
- [ ] Generate resume for sample job
- [ ] Verify project swapping works
- [ ] Check ATS score (85+)
- [ ] Verify 1-page format maintained
- [ ] Test skill/keyword updates

### 6. ATS Scoring Tests
- [ ] Score generated resume (should be 85+)
- [ ] Verify keyword matching
- [ ] Check skill detection
- [ ] Test bonus for generated resumes

### 7. State Management Tests
- [ ] Generate resume for job 1
- [ ] Generate resume for job 2
- [ ] Verify no cross-contamination
- [ ] Test state reset

### 8. Edge Cases
- [ ] Job with no description
- [ ] Job with minimal description
- [ ] Project with 0% match to job
- [ ] Multiple projects same score
- [ ] Missing required fields

---

## Test Results Summary

| Test | Status | Notes |
|------|--------|-------|
| | | |

