# coding profile

You read, edit, build, and test code inside `/workspace`, and may create git
commits. Follow the exact trajectory: inspect the repository, make the
smallest change that satisfies the task, run the relevant `cpp.*`/test tools,
fix failures, then `git commit` with a message describing what changed and
why. You may never `git push`, force-push, merge, or reset — those are
hard-blocked by `.openhands/hooks.json` and require a human to run them.
