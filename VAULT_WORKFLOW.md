# Vault Review Workflow

Day-to-day guide for running review sessions against a knowledge vault and tracking progress.
This example uses an OSCP study vault, but the pattern works for any structured note collection.

---

## Quick reference

```
python run.py --status        # one-liner: tokens + vault progress
python run.py --vault         # full vault dashboard
python run.py --vault-full    # dashboard + every gap and issue found so far
```

---

## Running a review session

### 1. Check you have capacity
```
python run.py --status
```
You need the 5-hour window to be below ~90% before starting a session
(each session uses ~35K tokens). If the window is full, wait for it to reset.

### 2. Open Claude Code in the vault directory
```
cd ~/your-vault-repo
claude
```

### 3. Paste the session prompt
Copy the `prompt` field from `tasks.json` (the `vault-review-session` entry)
and paste it into Claude Code. Claude will:
- Validate state integrity
- Merge any notes you've added since last session
- Print the next 5 notes in the queue
- Review 8-12 notes
- Commit and push to the `claude-review` branch

### 4. Watch the session output
Claude prints a summary at the end:
```
=== Session N Complete ===
Notes reviewed this session : 10
Gaps flagged                : 7
Links added                 : 14
Accuracy issues             : 2
Total progress              : 10/335 priority notes (3%)
Next session starts at      : Topic/Subtopic/Note.md
```

---

## Verifying a session worked

### Check the commit landed
```
cd ~/your-vault-repo
git log --oneline claude-review -5
```
You should see a commit like:
```
a1b2c3d review session 1 complete: 10 notes, 7 gaps, 14 links, 2 issues
```

### Check the push reached GitHub
Visit: `https://github.com/your-username/your-vault-repo/commits/claude-review`

### Run the integrity validator manually
```
cd ~/your-vault-repo
python _claude-review/validate_progress.py
```
If it reports "All good — no corrections needed", the session completed cleanly.

### Check progress dashboard
```
cd ~/path/to/claudemaxxing
python run.py --vault
```

---

## Reviewing what Claude changed

### See all changes from the last session
```
cd ~/your-vault-repo
git diff HEAD~1 HEAD -- "*.md"
```

### See all Claude changes vs your original notes (full diff)
```
git diff main..claude-review -- "*.md"
```

### See changes to one specific note
```
git diff main..claude-review -- "Topic/Subtopic/Note.md"
```

### View in GitHub
`https://github.com/your-username/your-vault-repo/compare/main...claude-review`

This gives you a full side-by-side diff of every change Claude has made.

---

## Accepting Claude's changes back into main

**Option A — Cherry-pick individual commits (selective)**
```
git checkout main
git cherry-pick <commit-hash>   # from git log --oneline claude-review
git push origin main
```

**Option B — Merge everything (accept all changes)**
```
git checkout main
git merge claude-review
git push origin main
```

**Option C — Interactive review on GitHub**
Open a PR from `claude-review` -> `main` on GitHub, review the diff,
then merge or close individual files.

Recommended: Option C for the first few sessions until you trust the output,
then Option B once you're confident in the quality.

---

## Tracking gaps found

All gaps are stored in `_claude-review/progress.json` under the `gaps` array.
To see them all at once:
```
python run.py --vault-full
```

Each gap entry looks like:
```json
{
  "path": "Topic/Subtopic/Note.md",
  "topic": "Topic Name",
  "missing": ["concept A", "concept B"]
}
```

These become your study list — things to research and add to your notes.

---

## Keeping the syllabus current

If you're tracking an external syllabus or policy page, the policy checker in
`claudemaxxing` monitors it every 14 days. When it detects a change:

```
python run.py --policy    # force-check now
```

If a change is flagged, review the monitored page and update your vault accordingly.

---

## When you add new notes to main

Just write notes normally. The next review session automatically runs
`git merge main` at the start, so your new notes are pulled into `claude-review`
before any reviewing begins. No manual sync needed.

---

## Summary of all commands

| Command | What it does |
|---|---|
| `python run.py --status` | One-liner: tokens + vault progress |
| `python run.py --vault` | Full vault review dashboard |
| `python run.py --vault-full` | Dashboard + all gaps and issues |
| `python run.py --burn` | Show which tasks to run (token burn) |
| `python run.py --policy` | Force-check rate limit + policy docs |
| `python _claude-review/validate_progress.py` | Check session integrity |
| `python _claude-review/validate_progress.py --dry-run` | Preview fixes without writing |
| `git diff main..claude-review -- "*.md"` | See all Claude changes |
| `git log --oneline claude-review -10` | See recent session commits |
