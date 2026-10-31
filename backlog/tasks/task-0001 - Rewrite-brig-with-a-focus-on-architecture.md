---
id: TASK-0001
title: Rewrite brig with a focus on architecture
status: To Do
assignee:
  - '@bruk'
created_date: 2026-10-17 19:05
updated_date: '2026-10-31T11:00:00Z'
labels:
  - brig
  - size-8
dependencies: []
references:
  - >-
    backlog/decisions/decision-0001 -
    Rebuild-brig-from-empty-in-three-layers-domain-infra-and-presentation.md
type: intent
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Problem

brig works, and it jails its embedder's processes today, but it grew stage by stage and it shows.
A jail type is spread over four packages, pure decisions sit inside the code that does I/O, grades
are stated before anything proves them, one role has two names (supervisor and "agent"), and the
supervisor program is written to an older Python than the rest. About half of what it ships, its
one embedder never uses.

I want it rewritten with a focus on architecture, in my Python approach, in a repository of its own,
and I don't want brig to have too much knowledge of the programs that use it. "io needs to be
separate", and it "should not care about domain": three layers, domain, infra and presentation, with
standard test layers (unit, integration, e2e, defined by where the mocks start). We won't care about
backwards compatibility; breaking is mostly fine. Keep egress. Keep oci, but pause on it for now.

Working in it should be really clean. While working, only the unit and integration tests the change
reaches run. E2e, the full suites, pypeeker, ruff and mypy run only when the work is done. `just` is
the entry point for running these things, and the boundaries are enforced with pypeeker. It needs a
docs directory, MkDocs with an auto-generated reference, and LikeC4 with the LikeC4 MCP enabled,
following my best practices. A Claude settings file comes first, to make sure my plugins are set up.
I would prefer all logs to be JSON-shaped and consistent.

## Affected users and systems

- **The owner (@bruk)**, who builds, reviews and accepts brig's work.
- **The agents working on brig**: implementing workers and the reviewer that closes tasks.
  `just check`, `just done` and the LikeC4 MCP are their tools as much as the owner's.
- **Embedders**: programs that jail work with brig. Each moves to the new API in its own repository,
  once brig can jail what it runs; that move is not this work.
- **The old brig**, kept outside this repository as read-only reference (`~/ref/brig-v1`, see
  CLAUDE.md): its code, its 3,950-line SPEC and the measured facts in its rulings. Nothing of it is
  copied in.
- **This repository's CI**: Linux with bubblewrap and Docker. Seatbelt needs a Mac.

## Open questions

- [x] Reservations (`.reserve(`): carry over the per-jail socket directory an embedder can reserve before the jail starts, or drop it? Settled by decision-0002: carry it over, as a request channel (name, bound_path, endpoint reservation against a per-jail channel directory, readiness a verified connect, never path existence). Full implementation is a later slice; the shape is decided.
- [ ] Egress: cooperative as today (the workload is pointed at the proxy and may ignore it), or enforced, by relaying the jail's only route out through the supervisor to the proxy? Carried forward: decision-0002 resequenced this to be designed after the supervisor lands (egress's own open question names the supervisor), not before; the cooperative-vs-enforced choice itself is still open.
- [x] Seatbelt: build its slice before a Mac run proves it, or wait for a Mac run? Settled by the owner, 2026-10-31: wait for a Mac run.
- [ ] The log envelope: its fields (time, level, source, event, then the event's own fields?), and whether "all logs JSON-shaped and consistent" becomes a rule in the philosophy plugin for every repository. Carried forward: decision-0002 resequenced this to be designed after the supervisor lands (the envelope's own open question names the supervisor's first log line), not before; the fields themselves are still open.
- [x] The docs theme: bh-01's components or Material for MkDocs? Settled by TASK-0001.02: Material for MkDocs; bh-01 is a UI/artifact design system, not an MkDocs theme, and Material integrates natively with mkdocstrings and mkdocs-likec4.
- [x] The ruff hook that formats every file an agent edits: add it to `.claude/settings.json`, or run ruff only in `just done`? Settled by TASK-0001.01: no hook. Ruff runs only in `just done`, matching this intent's own words above ("ruff ... run only when the work is done").
- [x] The SPEC's numbering: settled by decision-0001 (rule 18): new rulings are this board's decisions, and the old SPEC's are cited as "old SPEC decision-NNN".
- [x] What must not break: settled by the owner: no backwards compatibility, so brig's ten laws (criterion 17) are all that must not break.

## References

- decision-0001 (accepted): the design. Where it is built, the layout, the rules and the pypeeker rule that enforces each boundary, what is kept, cut and paused, and the order, outside-in.
- decision-0002 (accepted): the supervisor, request channels, and the grading skeleton -- the next slice's shape, and a revised order for decision-0001's step 4.
- The owner's philosophy plugin: the Python rules and the test rules (unit, integration, e2e, defined by where the mocks start), from knowhere.
- The c4-architecture plugin, from knowhere (`likec4-diagrams`: scaffold.py's layout, c4lint, the hard rules).
- `@likec4/mcp` (1.60.0), `mkdocs-likec4` (1.2.2), `mkdocstrings-python` (2.0.9), `rust-just` (1.59.0): the versions current on 2026-10-17.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 brig lives in a repository of its own, default branch `main`, built from empty, and imports only the standard library. Every file is Python 3.15, the supervisor program included.
- [x] #2 The repository's first commit is `.claude/settings.json`, which sets up the owner's plugins for every session in it, the owner's or an agent's, local or in the cloud: it registers the knowhere marketplace (`bruk-io/knowhere`), enables `philosophy@knowhere`, `authoring-kit@knowhere` and `c4-architecture@knowhere`, and approves the `likec4` server from `.mcp.json`.
- [x] #3 The code is in three layers: `domain` does no I/O and imports nothing outside itself, `infra` imports nothing from brig and takes and returns plain data, and `presentation` is the only layer that knows both. A pypeeker rule fails any change that breaks one of these.
- [ ] #4 Each jail type is a slice of its own, and no jail type imports another. bwrap and Seatbelt are built. oci has its place in the layout but is not built yet (paused).
- [ ] #5 Kept, and working: the filesystem policy, environment scrubbing, channels, the supervisor (named supervisor everywhere, never agent), the verified teardown and its report, grades, egress through the allowlisting proxy, and the interpreter checks.
- [x] #6 Cut, with nothing left of them: resource limits and the trampoline, rebuilding a jail in another process, probes as public API (the batteries stay, as e2e tests), events and denial signatures, exec fidelity, the mechanism stack and its compatibility matrix, the fake runtime, and the general helper machinery (the proxy is the one helper, started and stopped as part of the jail).
- [x] #7 The code follows the owner's Python approach (`philosophy:python-idioms`) and passes strict mypy.
- [x] #8 Every test sits in one of three layers, defined by where the mocks start (the owner's test rules): `tests/unit/` tests one pure function, with nothing mocked; `tests/integration/` tests brig's own parts together from a real entry point, with the world faked at its edge and nowhere else (fakes only, asserted on through their state); `tests/e2e/` tests against the real world with nothing faked, either a whole journey through the public API (the batteries included) or one infra module against bubblewrap, sandbox-exec or Docker. No test in any layer patches: time, randomness and the host enter the code as data.
- [x] #9 `just` is the only entry point: `just --list` shows every recipe with what it does, and each command line is written once, in the justfile.
- [x] #10 `just check` runs only the unit and integration tests that the change reaches (the diff against `main`, plus uncommitted and untracked files), and nothing else.
- [x] #11 `just done` runs ruff, mypy, every pypeeker rule (`check --strict`), every test in all three layers with the integration suite twice in one process, the docs build and the architecture lint. It reports every step whole and every failure in one pass. An e2e test it cannot run on this host is listed by name, never counted as a pass. CI runs `just done`, and nothing else counts as green.
- [x] #12 A `docs/` directory builds with MkDocs, failing on any warning. Its API reference is generated from brig's public API at build time and never committed.
- [x] #13 brig's architecture is a LikeC4 model in orthodox C4, laid out and linted by the c4-architecture plugin's rules (`likec4 validate` and c4lint clean). Its views are embedded in the docs, and the LikeC4 MCP server is enabled for every session in the repository, at a pinned version.
- [x] #14 The SPEC is part of the docs: brig's ten laws carried over, then one section per layer.
- [ ] #15 Every line brig's own processes write (the supervisor program, the egress proxy and its decision lines) is one JSON object in one envelope, defined once and written by one encoder. The library itself writes no log: what it knows comes back to the embedder as data.
- [x] #16 brig knows nothing of the programs that embed it: an embedder creates a jail, runs a process in it and tears it down through the public API alone, and no embedder's name, path or concept appears in brig's code or tests.
- [ ] #17 Must not break: every one of brig's ten laws (the old SPEC, section 2) holds in the new brig. Each has a test that would fail if it stopped holding, law 10's with a planted violation and its positive control.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Accepted by @bruk in conversation, 2026-10-17, as size-8. Spec waived by @bruk: the owner is both requester and approver, and decision-0001 carries the design. The open questions are resolved as listed: six carried forward with their reasons, two settled.

Bookkeeping pass (2026-10-25), checked against the real repo, not assumed from the
sub-tasks closed under it:

Verified TRUE, ticked: #1 (stdlib-only, Python 3.15 floor, own repo), #2 (first real
commit is exactly .claude/settings.json + .mcp.json, matching this AC's own text
field for field, including the pinned likec4@1.60.0), #3 (brig-layers/brig-pure-domain
pypeeker rules enforce the three layers), #6 (grepped src/brig for every cut concept
named -- trampoline, resource limits, exec fidelity, mechanism stack, fake runtime --
zero matches), #7 (mypy strict clean on every run this session), #8 (three test
layers, no patch/mock anywhere observed), #9-#11 (justfile is the one entry point;
just check/just done both exist and CI runs only just done), #12 (docs/reference.md
is a two-line mkdocstrings stub, `::: brig`, never committed static content; site/ is
gitignored), #13 (docs/architecture/index.md embeds four likec4-view blocks; c4lint
and likec4 validate clean every run), #14 (docs/spec/index.md: "## The ten laws" then
"## Domain" / "## Infra" / "## Presentation", exactly the structure this AC asks
for), #16 (no embedder name, path or concept found anywhere in src/ or tests/).

Verified FALSE, left unchecked -- genuine remaining scope, not stale bookkeeping:
- #4: only bwrap is built (src/brig/domain/jail_types/ and presentation/drivers/ each
  hold exactly one file). Seatbelt exists only as a planned LikeC4 element
  (TASK-0001.14's own "parallel slices" work modeled it, never built it); oci is
  paused as the AC itself already says.
- #5/#15: no egress, proxy, or allowlisting code anywhere in src/brig (grepped;
  the only "egress" string hits were "regressed" as a substring). infra/log.py,
  named in `[tool.pypeeker.brig-one-writer]`'s own comment as a write path alongside
  the supervisor's wire, does not exist either. Everything else #5 lists (fs policy,
  env scrubbing, channels, supervisor, verified teardown+report, grades, interpreter
  checks) is built and kept.
- #17: grepped every "law N" reference across src/, tests/ and backlog/ -- only laws
  1, 4, 9 and 10 have any reference at all, and not all of those are a dedicated
  test yet (law 9's is real, TASK-0001.28's own channel_exclusivity battery; the
  others are passing mentions). Laws 2, 3, 5, 6, 7 and 8 have no test tying them to
  this rewrite yet.

Net: the channels vertical slice (decision-0002 item 2, through TASK-0001.28) is
genuinely done. The egress proxy, the Seatbelt jail type, and systematic law-by-law
test coverage are the real remaining chunks of this intent -- not administrative
catch-up.
<!-- SECTION:NOTES:END -->
