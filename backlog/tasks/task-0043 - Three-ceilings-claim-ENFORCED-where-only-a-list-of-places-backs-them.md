---
id: TASK-0043
title: Three ceilings claim ENFORCED where only a list of places backs them
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T18:27:00Z'
labels:
  - brig
  - grades
  - size-3
  - finish-moved
dependencies: []
modified_files:
  - >-
    backlog/decisions/decision-0008 -
    A-jails-report-is-its-compiles-ceiling-per-claim-held-by-an-e2e-battery-to-what-it-measures.md
  - docs/spec/index.md
  - src/brig/domain/grades.py
  - src/brig/domain/jail_types/bwrap.py
  - tests/e2e/test_ceiling_host_change_battery.py
  - tests/e2e/test_report_battery.py
  - tests/unit/test_report_ceilings.py
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03. (a) fs_write is ENFORCED with a readable root nested in a writable root; demonstrated: the host renamed W/vendor and made a new one, and the jail then wrote W/vendor/lib.py. ceilings (domain/jail_types/bwrap.py) counts only write_denies and masks; compute it from the mounts (any READ_ONLY under WRITABLE caps it). (b) channel_exclusivity is ENFORCED while the jail reaches a host agent socket outside SOCKET_DIRECTORIES; demonstrated with a gpg-agent socket under a home directory. (c) network stays ENFORCED when a socket the jail can dial gives it the network (reasoned). Principle proposed: a ceiling reaches ENFORCED only when a kernel mechanism holds the claim, never because a path list found nothing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 fs_write's ceiling is computed from the compiled mounts: any read-only mount beneath a writable one (a deny, a mask, a nested readable root) caps it at BEST_EFFORT; e2e: the host replaces a nested readable root and the jail writes into it, and the ceiling it reported allowed for that
- [x] #2 channel_exclusivity is at most BEST_EFFORT whenever the jail sees any host path a socket could sit in beyond its own channel directory (a list of places is not a mechanism); VIOLATED stays for a visible SOCKET_DIRECTORIES entry or a writable shared root; e2e plants a socket outside the listed places and dials it
- [x] #3 decision-0008 is amended (a dated note) with the rule that ENFORCED needs a kernel mechanism, and a draft names the mechanism that could earn channel_exclusivity and network back (Landlock here is ABI 7: abstract sockets only; a supervisor-held listening fd plus a seccomp filter on socket(AF_UNIX) is the candidate)
- [x] #4 network is capped by the socket half of channel_exclusivity only: VIOLATED when a host socket place (SOCKET_DIRECTORIES) is visible, at most BEST_EFFORT whenever the jail sees any host root a socket could sit in; a writable shared root alone, which carries files and not a route out, does not lower it; a unit test pins each case
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Written after the change, as built (the brief from the owner was the plan).

### Order of work
1. Repro battery tests/e2e/test_ceiling_host_change_battery.py (fs_write host rename, socket outside the listed places, socket relaying to TCP), committed and recorded failing.
2. ceilings in src/brig/domain/jail_types/bwrap.py: fs_write from the compiled mounts, channel_exclusivity BEST_EFFORT for any root, network capped by channel_exclusivity; claim texts.
3. Hold the existing batteries to the new ceilings (test_report_battery, test_report_ceilings), add the ordering unit test.
4. decision-0008 dated note, the design draft, spec laws 1 and 9 and the domain section.
5. just done through record-check --tier full.

### Risks
- Embedders see network VIOLATED wherever channel_exclusivity is, a writable project included.
- The host-rename behaviour is kernel and filesystem dependent; the battery holds the report to what it measures either way.

### Proof
The repro passes after the fix; just done passes (recorded on this task).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Repro at 394ee413efe4, test files: tests/e2e/test_ceiling_host_change_battery.py; command: `uv run pytest tests/e2e/test_ceiling_host_change_battery.py` exited 1

(101 earlier lines omitted)
```text
        TCP listener: the jail's bytes reach the network. The control: the host reaches the TCP
        listener itself."""
        with (
            _outside_the_listed_places() as place,
            socket.socket() as server,
            socket.socket(socket.AF_UNIX) as relay,
        ):
            server.bind(("127.0.0.1", 0))
            server.listen()
            server.settimeout(10)
            port = server.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=5):
                control_peer, _ = server.accept()
                control_peer.close()
            path = f"{place}/agent.sock"
            relay.bind(path)
            relay.listen()
            stop = threading.Event()
            relaying = threading.Thread(target=_relay, args=(relay, port, stop), daemon=True)
            relaying.start()
            try:
                _, jail = _run(_DIAL, path, policy=_narrow(place))
                try:
                    peer, _ = server.accept()
                    with peer:
                        peer.settimeout(5)
                        reached = peer.recv(4) == b"ping"
                except TimeoutError:
                    reached = False
            finally:
                stop.set()
                relaying.join(timeout=5)
>       _held_under_host_change(jail, NETWORK_CLAIM, control=True, blocked=not reached)

tests/e2e/test_ceiling_host_change_battery.py:203: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

jail = Jail(process=Process(pid=17078, pgid=17078), supervisors=_RealSupervisor(start=<bound method LiveSupervisor.start of <...eps sockets it could dial: nothing crosses the boundary anonymously (old SPEC law 9)'): <Grade.ENFORCED: 'ENFORCED'>}))
claim = Claim(name='network', description='the command reaches no network: its own network namespace, with no interface')
control = True, blocked = False

    def _held_under_host_change(jail: Jail, claim: Claim, *, control: bool, blocked: bool) -> None:
        """The report for `claim` allows for what was measured with the host's help: anything when
        the violation was blocked, at most `BEST_EFFORT` when it got through."""
        assert control, f"{claim.name}: the positive control failed, so the probe proves nothing"
        allowed = Grade.ENFORCED if blocked else Grade.BEST_EFFORT
>       assert at_most(jail.report[claim], allowed), (claim.name, jail.report[claim], allowed)
E       AssertionError: ('network', <Grade.ENFORCED: 'ENFORCED'>, <Grade.BEST_EFFORT: 'BEST_EFFORT'>)
E       assert False
E        +  where False = at_most(<Grade.ENFORCED: 'ENFORCED'>, <Grade.BEST_EFFORT: 'BEST_EFFORT'>)

tests/e2e/test_ceiling_host_change_battery.py:51: AssertionError
----------------------------- Captured stderr call -----------------------------
In /home/user/brig-pins/.venv/lib/python3.15/site-packages/_editable_impl_brig.pth: /home/user/brig-pins/src does not exist; skipping sys.path append
In /home/user/brig-pins/.venv/lib/python3.15/site-packages/_editable_impl_brig.pth: /home/user/brig-pins/src does not exist; skipping sys.path append
=========================== short test summary info ============================
FAILED tests/e2e/test_ceiling_host_change_battery.py::test_fs_write_the_host_replacing_a_nested_readable_root_lets_the_jail_write_into_it
FAILED tests/e2e/test_ceiling_host_change_battery.py::test_channel_exclusivity_a_host_socket_outside_the_listed_places_is_dialled
FAILED tests/e2e/test_ceiling_host_change_battery.py::test_network_a_dialable_host_socket_carries_the_network
============================== 3 failed in 0.60s ===============================
```

Check `uv run just done` exited 0

(265 earlier lines omitted)
```text
[2m18:03:56.381[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m18:03:56.383[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m18:03:56.414[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m18:03:58.776[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.49s
[2m18:03:58.797[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m18:03:58.801[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.4s[39m[0m

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
INFO    -  Building documentation to directory: /home/user/brig-pins/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-pins/docs
INFO    -  Documentation built in 6.11 seconds

== architecture validate: PASS ==
[2m18:04:00.619[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m18:04:00.643[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m18:04:00.692[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m18:04:00.693[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m18:04:01.232[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m18:04:01.587[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m18:04:01.588[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 970ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 50 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

## Worker report (2026-11-03)

**What changed** (commits 394ee41 repro, 7babce8 fix; DRAFT filed as 1554398):
- `ceilings` (src/brig/domain/jail_types/bwrap.py): `fs_write` is read from the compiled mounts (`_beneath_writable`): any mount that is not writable whose nearest mount above is writable (a deny, a mask, a nested readable root, brig's tmpfs over a state directory inside a writable root) makes it BEST_EFFORT; pins (writable over writable) do not count. `channel_exclusivity`: VIOLATED for a writable path shared beyond the declared channels or a visible SOCKET_DIRECTORIES entry (unchanged); otherwise BEST_EFFORT while the jail sees any readable or writable root (`_sees_host_paths`; a file root counts too, since the host can rename a socket over it); ENFORCED only with no root, which `interpreter_refusal` never lets through, so no bwrap jail states it today. `network` is never stronger than `channel_exclusivity`. Claim texts for fs_write, network and channel_exclusivity say this; `Grade`'s docstring widens BEST_EFFORT to "unless the host changes what the jail sees".
- The repro (tests/e2e/test_ceiling_host_change_battery.py) is AC #1's and #2's e2e: the host renames a nested readable root away and makes a new one and the jail writes into it; a socket under the home directory (outside every listed place) is dialled; and for network, that socket relays the jail's bytes to a host TCP listener. Each holds the report to at most BEST_EFFORT when the host's help got the violation through. It needed the host to wait for the jail's first write before renaming: renaming before bwrap had mounted made bwrap bind the new directory, and the jail could not write (measured).
- AC #3: `test_network_is_never_stronger_than_channel_exclusivity` in tests/unit/test_report_ceilings.py, over policies that reach all three of ENFORCED, BEST_EFFORT and VIOLATED.
- AC #4: decision-0008 has a dated note (2026-11-03). The backlog CLI can edit only a decision's status, so the body was edited by hand as earlier amendments were. The draft is "A kernel mechanism to earn channel_exclusivity and network back from best-effort" (type design): Landlock measured ABI 7 here (abstract sockets only); candidate a supervisor-held listening fd per channel plus seccomp on socket(AF_UNIX).
- Spec: law 1 (ENFORCED needs a kernel mechanism), law 9 (any root leaves channel_exclusivity best-effort), the domain section's ceilings paragraph.

**Batteries held to the new ceilings** (the change itself, not a weakening):
- tests/e2e/test_report_battery.py, the narrow-policy socket case: the report now says BEST_EFFORT for channel_exclusivity, not ENFORCED. The battery still measures the dial into /tmp blocked there; the claim now also covers sockets no list names, which the new battery dials.
- tests/unit/test_report_ceilings.py: the default policy's network is VIOLATED (it shows /run and /tmp); the two no-listed-socket-place cases (readable /usr and /etc; / with the socket places masked) are BEST_EFFORT. New cases for nested readable roots, masks inside a writable root, writable over writable, a mask outside writable roots (fs_write stays ENFORCED), and the no-root ENFORCED case.
- tests/e2e/test_pin_rename_battery.py needed no edit: its at_most check holds with BEST_EFFORT.

**What an embedder sees** (computed with ceilings): a writable project, the system read-only (readable /), credentials masked (~/.ssh, ~/.aws): fs_write ENFORCED, fs_read BEST_EFFORT, network VIOLATED (was ENFORCED), env ENFORCED, channel_exclusivity VIOLATED. The same with a write deny in the project (.git/hooks): fs_write BEST_EFFORT. A narrow system (/usr, /etc, home) with a writable project: the same as the first. A read-only project with a narrow system and no writable root: fs_write ENFORCED, fs_read ENFORCED, network BEST_EFFORT, env ENFORCED, channel_exclusivity BEST_EFFORT. network follows channel_exclusivity literally (AC #3), so a writable shared root alone makes network VIOLATED; a reviewer may prefer to cap network only by the socket half of the rule (VIOLATED for a visible socket place, BEST_EFFORT for any root), which this change does not do.

**Not verified**: the fs_write host rename on another filesystem than ext4 or another kernel than 6.18 (here it moves the mount with the entry, as the review measured); a socket renamed over a file root; any kernel mechanism for the draft.

Lead, 2026-11-03: finish moved twice, both by me. (1) I wrote the criteria in a separate edit after promoting the draft. (2) Criterion 3 as first written ('network never stronger than channel_exclusivity') made network VIOLATED for every embedder with a writable project, because channel_exclusivity is VIOLATED for any writable shared root, which carries files and not a route out. Replaced by the socket-half rule above.

Check `uv run just done` exited 0

(270 earlier lines omitted)
```text
[2m18:22:52.295[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m18:22:52.298[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m18:22:52.300[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m18:22:54.792[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.60s
[2m18:22:54.809[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m18:22:54.816[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.7s[39m[0m

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
INFO    -  Building documentation to directory: /home/user/brig-pins/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-pins/docs
INFO    -  Documentation built in 6.57 seconds

== architecture validate: PASS ==
[2m18:22:56.745[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m18:22:56.761[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m18:22:56.793[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m18:22:56.794[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m18:22:57.266[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m18:22:57.607[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m18:22:57.608[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 863ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 50 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```

## Worker report, network revision (2026-11-03)

Commit ffcd071. `ceilings` now computes `_socket_reach` (VIOLATED for a visible SOCKET_DIRECTORIES place, BEST_EFFORT while any readable or writable root is seen, ENFORCED with none). `network` is exactly that; `channel_exclusivity` is that unless a writable path is shared beyond the declared channels, which makes it VIOLATED. A writable shared root alone no longer lowers `network`. AC #4's unit cases are in tests/unit/test_report_ceilings.py: `test_network_is_violated_where_a_socket_place_is_visible`, `test_network_is_at_most_best_effort_while_any_host_root_is_seen`, `test_a_writable_shared_root_alone_does_not_lower_network`; the no-root ENFORCED case is in `test_only_a_jail_that_sees_no_host_path_keeps_exclusivity_enforced`. The earlier ordering test is gone. The NETWORK_CLAIM text, the spec's domain section and decision-0008's 2026-11-03 note say the same; the recorded repro file was not touched and still passes.

Grades a typical embedder now gets (computed with `ceilings`):
- writable project, readable /, ~/.ssh and ~/.aws masked: fs_write ENFORCED, fs_read BEST_EFFORT, network VIOLATED (/ shows /run and /tmp), env ENFORCED, channel_exclusivity VIOLATED.
- the same with a write deny on .git/hooks: fs_write BEST_EFFORT, otherwise the same.
- writable project, readable /usr, /etc and the home directory, ~/.ssh masked: fs_write ENFORCED, fs_read BEST_EFFORT, network BEST_EFFORT, env ENFORCED, channel_exclusivity VIOLATED.
- read-only project with /usr and /etc, nothing writable: fs_write ENFORCED, fs_read ENFORCED, network BEST_EFFORT, env ENFORCED, channel_exclusivity BEST_EFFORT.

Check `uv run just done` exited 0

(276 earlier lines omitted)
```text
[2m18:27:34.593[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:react/[39m[95marchitecture[39m[0m
[2m18:27:34.595[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:model/[39m[95marchitecture[39m[0m
[2m18:27:34.646[0m [1m[32mINFO [0m [1m[36mlikec4.vite[0m [2mgenerating [22m[35mlikec4:icons/[39m[95marchitecture[39m[0m
[2m18:27:37.019[0m [1m[32mINFO [0m [1m[36mlikec4.vite.webcomponent[0m ✓ built in 2.52s
[2m18:27:37.041[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [2mgenerated[22m /home/user/brig-pins/site/assets/mkdocs_likec4/likec4_views.js[0m
[2m18:27:37.044[0m [1m[32mINFO [0m [1m[36mlikec4.c4:codegen[0m [32mdone in 3.7s[39m[0m

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
INFO    -  Building documentation to directory: /home/user/brig-pins/site
INFO    -  mkdocs-likec4: Generating web component for default project from /home/user/brig-pins/docs
INFO    -  Documentation built in 6.40 seconds

== architecture validate: PASS ==
[2m18:27:39.037[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mlayout[22m wasm[0m
[2m18:27:39.053[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m /home/user/brig-pins/docs/architecture[0m
[2m18:27:39.101[0m [1m[32mINFO [0m [1m[36mlikec4.server.projects[0m add [32m'architecture'[39m
[2m18:27:39.102[0m [1m[32mINFO [0m [1m[36mlikec4.server.workspace[0m loaded [33m1[39m projects
[2m18:27:39.642[0m [1m[32mINFO [0m [1m[36mlikec4.lang[0m [2mworkspace:[22m found 37 source files[0m
[2m18:27:40.018[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32m✓ Valid[39m[2m (37 files)[22m[0m
[2m18:27:40.018[0m [1m[32mINFO [0m [1m[36mlikec4.c4:validate[0m [32mvalidate 983ms[39m[0m
npx -y likec4@1.60.0 validate docs/architecture

== architecture lint: PASS ==

c4lint: 0 error(s), 0 warning(s) across 30 elements, 50 relationships, 5 views
uv run python3 scripts/c4lint.py docs/architecture
warning: The `UV_NATIVE_TLS` environment variable is deprecated and will be removed in a future release. Use `UV_SYSTEM_CERTS` instead.

done: all steps passed
```
<!-- SECTION:NOTES:END -->
