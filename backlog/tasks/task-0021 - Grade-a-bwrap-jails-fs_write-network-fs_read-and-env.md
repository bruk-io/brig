---
id: TASK-0021
title: Grade a bwrap jail's fs_write, network, fs_read and env
status: In Progress
assignee:
  - '@claude'
created_date: '2026-10-31T11:00:00Z'
updated_date: '2026-11-03T04:20:00Z'
labels:
  - size-5
dependencies: []
references:
  - >-
    backlog/tasks/task-0001.18 -
    Grading-skeleton-claims-evidence-and-grade-unenforced-by-default-independent-of-the-supervisor.md
type: task
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An embedder that shows its person how well a jail holds wants one grade per axis of enforcement: what the command may write (`fs_write`), reach on the network (`network`), read (`fs_read`) and see of the environment (`env`), as the old brig graded them. At a7e7f45 brig states one claim, `CHANNEL_EXCLUSIVITY_CLAIM`; TASK-0001 criterion #5 keeps grades, and the grading skeleton (TASK-0001.18) is unenforced by default until evidence proves otherwise.

Each claim's grade must come from evidence, never be stated ahead of it (law: grades are honest). A path masked with a bind is enforced only while the host leaves the masked entry alone: an embedder that knows the host may replace it needs the grade to say best-effort, or the evidence to let it decide.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A bwrap jail's compile states a claim for each of fs_write, network, fs_read and env, re-exported from brig like CHANNEL_EXCLUSIVITY_CLAIM
- [ ] #2 Each claim is graded from evidence an e2e battery produces against real bwrap, and none grades stronger than that battery shows
- [x] #3 With no evidence, each grades unenforced (TASK-0001.18's default)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Architecture review, 2026-11-02: there is no runtime report today. Grade and Evidence exist only inside e2e tests, and only one Claim is in src (fd_inheritance and tiocsti_closure are defined in tests/e2e/test_claims_wiring.py). An embedder needs a call that returns a jail's claims and grades at runtime (something like claims_for(jail) or report(policy)), built from claims the compile states for that policy and evidence that ships with the commit. Include a claim for a read-only bind nested in a writable one, which the host can undo by replacing the entry, computed from the binds. The claims must also measure what TASK-0022 and DRAFT-0012 found, or they will overstate.

Accepted 2026-11-03 under the owner's goal. Worker's report (Claude): built at bcf6047, decision-0008. bwrap states FS_WRITE_CLAIM, FS_READ_CLAIM, NETWORK_CLAIM and ENV_CLAIM beside CHANNEL_EXCLUSIVITY_CLAIM, all re-exported from brig; ceilings(policy, mounts, channels) gives each the strongest grade the compiled jail can have (fs_write/fs_read BEST_EFFORT while a deny/mask is mounted inside a writable root; channel_exclusivity VIOLATED when a writable shared path is not a declared channel), and Jail.report carries it. Grade gains BEST_EFFORT; at_most(stated, measured) orders the grades. tests/e2e/test_report_battery.py: per claim, the violation planted against a real jail with a positive control (a loopback listener the host reaches; a write outside the root beside one inside it; a masked file beside a plain one; an allowed variable beside a secret one), graded with grade(), and the report asserted no stronger; plus the BEST_EFFORT case. Seen failing: with the env scrub removed from operations.create, the env case fails. A jail with no evidence (no compile, a fake supervisor port) reports nothing, so nothing is stated enforced unproven. Unit tests: tests/unit/test_report_ceilings.py. uv run just done passes.

Check `uv run just done` exited 0

(257 earlier lines omitted)
```text
[2m04:07:22.254[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m04:07:22.256[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m04:07:22.281[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m04:07:24.486[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.35s
[2m04:07:24.489[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m04:07:24.492[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.1s[39m[0m

   ┌───────────────────────────────────────────────────────────────┐
   │                                                               │
   │                                                               │
   │   [2mWebcomponents generated to:[22m                                 │
   │    site/assets/mkdocs_likec4/likec4_views.js                  │
   │                                                               │
   │   [2mSetup and usage instructions:[22m                               │
   │    [34mhttps://likec4.dev/tooling/code-generation/webcomponent/[39m   │
   │                                                               │
   │                                                               │
   └───────────────────────────────────────────────────────────────┘

uv run mkdocs build --strict
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

[31m │  ⚠  Warning from the Material for MkDocs team[0m
[31m │[0m
[31m │[0m  MkDocs 2.0, the underlying framework of Material for MkDocs,
[31m │[0m  will introduce backward-incompatible changes, including:
[31m │[0m
[31m │  × [0mAll plugins will stop working – the plugin system has been removed
[31m │  × [0mAll theme overrides will break – the theming system has been rewritten
[31m │  × [0mNo migration path exists – existing projects cannot be upgraded
[31m │  × [0mClosed contribution model – community members can't report bugs
[31m │  × [0mCurrently unlicensed – unsuitable for production use
[31m │[0m
[31m │[0m  Our full analysis:
[31m │[0m
[31m │[0m  [4mhttps://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/[0m
[0m
INFO    -  mkdocs-likec4: No projects discovered, using default root project
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/brig/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig/docs
INFO    -  Documentation built in 6.29 seconds

== architecture validate: PASS ==
[2m04:07:26.205[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m04:07:26.222[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m04:07:26.262[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m04:07:26.263[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m04:07:26.831[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m04:07:27.100[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m04:07:27.100[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 896ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

Review 2026-11-03 (reviewer): not closed. Full gate passes (recorded above). AC#1 met (five claims re-exported from brig), AC#3 met (grade() with no evidence gives UNENFORCED; a jail with no compile reports {}). AC#2 not met: (high, measured) a mask in a read-only root is stated ENFORCED but the host can undo it. Policy FsPolicy(readable=('/',), masks=(f'{root}/secret',)); report[FS_READ_CLAIM] == ENFORCED; the host os.replace()s a new file over secret while the jail runs; the jail then reads NEW-SECRET. Detaching a mount when its dentry is renamed over happens in every namespace, so it does not matter whether the root is writable. ceilings() applies BEST_EFFORT only to deny or mask targets inside policy.writable; it should apply to any deny or mask bound over a host entry. The same holds for write denies, and the battery's best-effort case and test_fs_read should plant the host-side rename. (medium) No battery case plants a write at a write deny, so dropping the deny mounts would fail nothing: fs_write's 'nothing a write deny names' is stated without evidence. (low) fs_read's 'reads only the policy's roots' is measured only indirectly, through the narrow-policy socket dial; add a read outside a narrow policy's roots.

Worker, 2026-11-03, on the latest review, fixed at fe3f40d (see its message for each). TASK-0021: every mounted deny/mask caps fs_write/fs_read at BEST_EFFORT, with e2e cases for a host rename over a mask under a read-only root (this container keeps the mask, the reviewer's kernel did not: the grade allows for both) and a write at a deny. TASK-0034: PolicyStdioThroughLink names the link (infra.files.first_link). TASK-0035: an existing stdio path must be a regular file the embedder owns (PolicyStdioNotOwnFile; checked again once opened); e2e cases for another user's 0666 file and /dev/zero. TASK-0033: the gate failure came from the report battery writing os.environ; it now passes its environment as data; the rule's message names item writes. TASK-0036: law 9 counts argv as a shared medium again and says nothing tests it yet. uv run just done passes at fe3f40d.

Check `uv run just done` exited 0

(259 earlier lines omitted)
```text
[2m04:20:40.656[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m04:20:40.685[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m04:20:40.701[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m04:20:42.921[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.36s
[2m04:20:42.924[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m04:20:42.928[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.2s[39m[0m

   ┌───────────────────────────────────────────────────────────────┐
   │                                                               │
   │                                                               │
   │   [2mWebcomponents generated to:[22m                                 │
   │    site/assets/mkdocs_likec4/likec4_views.js                  │
   │                                                               │
   │   [2mSetup and usage instructions:[22m                               │
   │    [34mhttps://likec4.dev/tooling/code-generation/webcomponent/[39m   │
   │                                                               │
   │                                                               │
   └───────────────────────────────────────────────────────────────┘

uv run mkdocs build --strict
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

[31m │  ⚠  Warning from the Material for MkDocs team[0m
[31m │[0m
[31m │[0m  MkDocs 2.0, the underlying framework of Material for MkDocs,
[31m │[0m  will introduce backward-incompatible changes, including:
[31m │[0m
[31m │  × [0mAll plugins will stop working – the plugin system has been removed
[31m │  × [0mAll theme overrides will break – the theming system has been rewritten
[31m │  × [0mNo migration path exists – existing projects cannot be upgraded
[31m │  × [0mClosed contribution model – community members can't report bugs
[31m │  × [0mCurrently unlicensed – unsuitable for production use
[31m │[0m
[31m │[0m  Our full analysis:
[31m │[0m
[31m │[0m  [4mhttps://squidfunk.github.io/mkdocs-material/blog/2026/02/18/mkdocs-2.0/[0m
[0m
INFO    -  mkdocs-likec4: No projects discovered, using default root project
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /home/user/brig/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig/docs
INFO    -  Documentation built in 6.23 seconds

== architecture validate: PASS ==
[2m04:20:44.996[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m04:20:45.044[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig/docs/architecture[0m
[2m04:20:45.124[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m04:20:45.125[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m04:20:45.687[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 27 source files[0m
[2m04:20:45.935[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (27 files)[22m[0m
[2m04:20:45.935[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 943ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 20 elements, 20 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
