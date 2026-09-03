# OpenHands dotfile template (WP08)

Reusable `.openhands/` + `.agents/` scaffolding to drop into any target
repository an OpenHands profile will work on (e.g. `/srv/repos/quant-modeling`
once it exists). Not meant to be used from AgenticEnv itself.

## Apply to a target repo

```bash
target=/srv/repos/<project>
cp -r agents/openhands-template/.openhands "$target/"
cp -r agents/openhands-template/.agents "$target/"
cp agents/openhands-template/AGENTS.md.template "$target/AGENTS.md"
chmod +x "$target/.openhands/hooks/"*.sh
```

Then edit the copied `AGENTS.md` to describe the actual repo (purpose, setup,
structure, CI checks) instead of the placeholder comments, and commit
`.openhands/`, `.agents/`, and `AGENTS.md` to the target repo.

## What's included

- `.openhands/hooks.json` + `.openhands/hooks/block_dangerous.sh` — hard
  `PreToolUse` block on `git push`/`merge`/`rebase`/force-flags/
  `reset --hard`/`clean -f`/`rm -rf`/secret-path access, regardless of the
  session's confirmation mode. This is the safety net required because
  `openhands --headless` always runs in always-approve mode (confirmed via
  docs.openhands.dev/openhands/usage/cli/headless — cannot be changed).
- `.agents/skills/git-checkpoint/SKILL.md` — commit discipline (small,
  test-passing increments; never push/merge/reset).
- `.agents/skills/rag-citation/SKILL.md` — never state a formula/number from
  memory when `kb.search`/a `cpp.*` tool can confirm it.
- `.agents/skills/quant-conventions/SKILL.md` — unit/tolerance conventions,
  no silent reinterpretation.
- `AGENTS.md.template` — always-loaded repo context (OpenHands "General
  Skills" convention, see docs.openhands.dev/overview/skills/repo).

Per-repo additions (not templated here, add when needed):

- A `Stop` hook requiring the repo's actual test command to pass before the
  agent may finish (repo-specific test runner, see `agent-smoke-test`'s copy
  for a worked example).
- A `.openhands/setup.sh` if the repo needs first-run dependency install.
