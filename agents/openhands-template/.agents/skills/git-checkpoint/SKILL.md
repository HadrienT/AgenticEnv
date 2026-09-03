---
name: git-checkpoint
description: This skill should be used when the user asks to "commit", "save progress", "checkpoint", "create a commit", or when a task is long enough that partial progress should survive a session restart.
triggers:
- commit
- checkpoint
- save progress
- git commit
---

# Git Checkpoint Discipline

Treat every meaningful, test-passing increment of work as a commit boundary —
do not accumulate multiple unrelated changes into one commit, and do not wait
until the entire task is "done" to commit for the first time.

## Core Instructions

1. One task = one branch. Before making any change, check `git status` /
   `git branch --show-current`; if you are on `main` (or the repo's default
   branch), create and switch to a dedicated branch first (e.g.
   `agent/task-YYYYMMDD-<slug>`). Never commit directly on `main`.
2. Before committing, run the project's test/build command and confirm it
   passes. Never commit with known-failing tests unless the task is
   explicitly "reproduce this failure" (in which case say so in the message).
2. Write commit messages that state what changed and why, not just what file
   was touched. One logical change per commit.
3. After a commit, if `mem.remember` is available, record a short procedural
   note (what was done, what remains) so later sessions can resume without
   re-reading the whole diff history.
4. Never run `git push`, `git merge`, `git rebase`, `--force`, or
   `git reset --hard` — these are hard-blocked by `.openhands/hooks.json`
   regardless of confirmation mode. If the task seems to require one of
   these, stop and say a human needs to run it.

## Common Patterns

- Mid-task interruption: commit what passes tests now, leave a `mem.remember`
  note describing the next step, then continue or stop.
- Multi-file refactor: commit in the smallest slices that keep tests green,
  not as one giant diff at the end.
