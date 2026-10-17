# brig

A standalone sandbox library: it jails a program's processes and grades how well each part of the
jail is enforced. It imports the standard library only, and it knows nothing of the programs that
embed it.

## Where the work starts

- **The board is the source.** `backlog task list --plain`; the intent (the root task) says what
  finished looks like, and decision-0001 is the design: the layout, the rules, and the pypeeker rule
  behind each boundary. Change the board only through the `backlog` CLI.
- **`just --list`** is every command the work runs, once the scaffolding task has landed: `just check`
  while working, `just done` before a task goes to review.
- **The owner's plugins** come from `.claude/settings.json` (from the knowhere marketplace:
  philosophy, authoring-kit, c4-architecture), and the LikeC4 MCP server from `.mcp.json`.

## The old brig

Read-only reference at `~/ref/brig-v1`, outside this repository. Read it for the measured facts in
its SPEC's rulings, cited as "old SPEC decision-NNN". Never copy its code in, and never name in brig
the program it came from.
