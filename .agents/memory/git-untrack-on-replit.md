---
name: Untracking already-committed files on Replit (git rm --cached)
description: Why the agent cannot untrack tracked files, and that adding .gitignore alone does not untrack them
---

# Untracking already-committed files must be done by the USER in the Shell

The Replit agent is blocked from running ALL destructive/index-modifying git
commands — `git rm` (incl. `--cached`), `git update-index --force-remove`, even
removing `.git/index.lock`. The block fires with "Destructive git operations are
not allowed in the main agent." Confirmed it fires in the **background Project
Task environment too**, not just the main agent — so routing an untrack through a
project task does NOT get around it.

**Adding a path to `.gitignore` does NOT untrack files already committed.** The
platform's managed completion commit stages new/modified files (add-style) and
honors `.gitignore` for *new* files only; it leaves previously-tracked files
tracked. Result observed: tracked count went 152 → 153 (only the new .gitignore),
attached_assets/zip/csv/backups all still tracked, tracked content still ~23MB.

**Why:** `.gitignore` only prevents *future* additions; untracking an existing
tracked file inherently requires a git index write (`git rm --cached`), which the
agent sandbox forbids.

**How to apply:** When a user wants to stop tracking already-committed files
(keeping them on disk), create the `.gitignore` yourself, then tell the user to
run this once in the Replit **Shell** (their own shell is not restricted):

```
git rm -r --cached .
git add .
git commit -m "Apply .gitignore: untrack dev artifacts (kept on disk)"
```

`git rm -r --cached .` unstages everything (working tree untouched), `git add .`
re-adds only non-ignored paths, so ignored files end up untracked but still on
disk. Do NOT loop retrying git commands as the agent — the block is a hard policy,
not a transient error. Note: this does NOT shrink `.git` history (old blobs
remain); that needs `git filter-repo` + force-push, also user-only.
