# Shared project rules (Claude Code + Codex)

Two AI tools work on this project, Claude Code and Codex, one at a time. Tim owns it and directs the work; he isn't a programmer, so explain things in plain words.

## Start of a session
- Read `HANDOFF.md` (and `ideas.md`, if there is one) before changing anything.
- Run `git status` and `git log --oneline -5`. If there are uncommitted changes, the last session didn't finish cleanly: tell Tim what they are before building on top of them.

## While working
- Only one tool edits this folder at a time.
- Git history is the backup. Don't make hand-made copies (`file.bak`, dated `.zip` snapshots).
- Never read, print, or commit secrets (API keys, tokens, `.env` files, `key.txt`). `.gitignore` lists them.
- Don't delete files or rewrite Git history (reset, rebase, force push) unless Tim asks.
- No paid services, new subscriptions, or new dependencies without Tim's OK.

## End of a session
1. Update `HANDOFF.md`: where things stand, what changed, anything not verified, and the next useful step. Start the new entry with `[Claude]` or `[Codex]` and the date.
2. Commit everything, with a message that starts with `[Claude]` or `[Codex]`.
3. Don't push to GitHub unless Tim asks or `HANDOFF.md` says this project pushes.

## About this project
`HANDOFF.md` describes what this project is, how it's built, and the decisions already made.
