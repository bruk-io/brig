---
id: decision-0010
title: >-
  A Seatbelt jail on Darwin compiles FsPolicy and EgressPolicy into an SBPL
  profile, isolates the supervisor with PT_DENY_ATTACH, verifies channel peers
  with LOCAL_PEERTOKEN, and states measured ceilings per claim
date: '2026-11-10 20:05'
status: accepted
---
## Context

TASK-0061 (for TASK-0001's Seatbelt slice on Darwin): an embedder running on macOS needs the same
supervisor, request channels, `FsPolicy`, `EnvPolicy`, `EgressPolicy`, and honest per-claim
report (`jail.report`) that `bwrap` provides on Linux, backed by `/usr/bin/sandbox-exec` and XNU's
Seatbelt MAC policy.

Four design questions had to be settled by measurement on Darwin before writing code:
1. **How `FsPolicy` compiles to SBPL.** Seatbelt has no mount namespace; XNU evaluates SBPL rules
   against resolved vnode paths in last-matching-rule-wins order after `(version 1)`,
   `(deny default)`, and `(import "system.sb")`.
2. **How the supervisor is protected inside the jail on Darwin.** Linux uses `PR_SET_DUMPABLE=0`
   plus an unshared user/PID namespace with all capabilities dropped (decision-0006), and closes
   inherited fds 3, 4, and 5 before spawning children. Darwin has no `prctl` and no PID namespace.
3. **How channel readiness and peer verification work on Darwin.** Linux uses `SO_PEERCRED` plus
   `/proc/<pid>/ns/pid` (decision-0005). Darwin has no `/proc` and no PID namespace.
4. **What grade ceilings Seatbelt reaches per claim (`fs_write`, `fs_read`, `network`, `env`,
   `channel_exclusivity`), held to empirical e2e measurement on Darwin.**

## Decision

1. **SBPL compilation (`brig.domain.jail_types.seatbelt`) and template-string rendering (decision-0001 rule 16).**
   - **Header:** `(version 1)`, `(deny default)`, `(import "system.sb")`, `(allow process*)`,
     `(allow signal (target same-sandbox))`, `(allow sysctl-read)`, `(allow mach-lookup)`,
     `(allow ipc-posix-shm-read*)`.
   - **Read and write roots (shallowest-first by path depth, emitting both unresolved and
     resolved paths when symlinks such as `/var -> /private/var` or `/tmp -> /private/tmp` differ):**
     - `(import "system.sb")` on macOS grants `file-read*` only on system paths (`/System`,
       `/usr/lib`, `/usr/share`, `/Library/Apple`, `/private/etc/passwd`, `/dev/null`, etc.), not
       on arbitrary host paths.
     - For every root (`readable` or `writable`), emit `(allow file-read-metadata (literal "<dir>"))`
       on each ancestor directory from `/` down to the root's parent (and on the unresolved root
       path itself when it is a symlink) so `execvp` and `realpath` traversal into roots work
       without opening ancestor directories for reading or listing.
     - Each `readable` root emits `(deny file-write* (subpath "<root>"))` followed by
       `(allow file-read* (subpath "<root>"))`. Emitting `deny file-write*` on readable roots lets
       a nested readable root inside a shallower writable root carve out read-only access.
     - Each `writable` root emits `(allow file-read* file-write* (subpath "<root>"))`.
   - **Carve-outs after roots:**
     - Each `write_denies` entry emits `(deny file-write* (subpath "<path>"))`.
     - Each `masks` entry emits `(deny file-read* file-write* (subpath "<path>"))`.
     - `state_dir` is masked with `(deny file-read* file-write* (subpath "<state_dir>"))` followed
       by `(allow file-read* (literal "<supervisor_script>"))`, so the initial `python -I` process
       can read `supervisor.py` while supervised commands cannot read or write anything else in
       `state_dir` (including `profile.sb`).
     - When `channel_directory` is present, emit `(allow file-read-metadata (literal ...))` on its
       ancestors and `(allow file-read* file-write* (subpath "<channel_directory>"))`.
   - **Directory pins (`deny file-write-unlink`) and absent-target placeholders:**
     - Measured on Darwin: `(allow file-write* (subpath "/w"))` permits `rmdir("/w")` unless `/w`
       itself is pinned, and permits renaming an intermediate directory `/w/a` on the way to a
       carve-out `/w/a/b/secret` unless `/w/a` and `/w/a/b` are pinned.
     - Furthermore, if an intermediate directory `/w/a` does not exist when the jail starts, a
       jailed command can `rename("/w/planted", "/w/a")`, which XNU evaluates as `file-write-create`
       on `/w/a` rather than `file-write-unlink`, bypassing the deny on `/w/a/secret`!
     - Therefore:
       1. `placeholders_for` holds absent carve-out targets (and their intermediate directories)
          inside writable roots before the jail starts, tagged with Darwin extended attributes
          (`user.brig.placeholder`) and cleaned up by `placeholders.release` / `placeholders.sweep`.
       2. Every writable root `!= "/"` and every strict ancestor directory between a writable root
          and a carve-out (`write_denies`, `masks`, a nested `readable` root, or `state_dir`) is
          pinned with `(deny file-write-unlink (literal "<dir>"))`.
   - **Network rules in SBPL:**
     - Emit `(deny network* (with no-log))` to override `(import "system.sb")`'s unix-socket grants.
     - Measured on Darwin: XNU's Sandbox MAC hook checks `network-outbound` and `network-bind` on
       `AF_UNIX` sockets as well as IP sockets. Under `(deny network* (with no-log))`, `connect()`
       and `bind()` to any Unix socket outside `channel_directory` fail with `EPERM`, even when the
       socket file sits inside a readable or writable root.
     - When `channel_directory` is present, emit `(allow network-bind (subpath "<channel_dir>"))`
       and `(allow network-outbound (subpath "<channel_dir>"))`.
     - When an `EgressPolicy` is present with `bridge_port`, emit
       `(allow network-bind (local tcp "localhost:<port>"))`,
       `(allow network-inbound (local tcp "localhost:<port>"))`, and
       `(allow network-outbound (remote tcp "localhost:<port>"))` so the supervisor can bind its
       loopback bridge and jailed commands can connect only to port `<port>`.
   - **Template-string rendering:** `render_profile` and atom helpers accept only Python 3.15
     `string.templatelib.Template` (`t"..."`) and reject plain `str` by type (`mypy --strict`),
     escaping `\` and `"` inside every interpolated value and rejecting NUL bytes (`\x00`).

2. **Supervisor protection on Darwin (`brig.infra.supervisor.program`).**
   - At startup, `_make_undumpable()` on Darwin calls `ptrace(PT_DENY_ATTACH, 0, 0, 0)`
     (`PT_DENY_ATTACH = 31` via `libSystem.dylib`). Measured: inside `sandbox-exec`, a child
     process calling `ptrace(PT_ATTACH, ppid, ...)` receives `SIGSEGV` from XNU and `ptrace` fails
     with `EBUSY`.
   - The supervisor closes inherited control/handshake/proxy fds `3`, `4`, and `5` before spawning
     any command, and Darwin has no `/proc/<pid>/fd` through which a child could reopen fds held by
     its parent.
   - `sandbox-exec -f <profile.sb> python -I <supervisor.py>` calls `sandbox_init` and `execvp`s
     Python in place, so the supervisor is the root process of the jail and leads its own process
     group (`start_new_session=True`).

3. **Channel readiness and peer verification on Darwin (`brig.infra.sockets`).**
   - `open_directory` uses `O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW` on Darwin (where Linux
     adds `O_PATH`), and verifies the directory fd's path via `fcntl(F_GETPATH)`.
   - Before `connect()`, `channel_ready` stats `<directory_fd>/<name>` with `follow_symlinks=False`
     and verifies `S_ISSOCK(st_mode)`, refusing symlinks or non-sockets before any connection is
     made (and again after `connect()` verifies `st_dev`/`st_ino` match).
   - After `connect()`, Darwin reads the peer's kernel audit token via
     `getsockopt(SOL_LOCAL=0, LOCAL_PEERTOKEN=0x006, 32)`, unpacking
     `(auid, euid, egid, ruid, rgid, pid, asid, pidversion)`:
     - `ENOPROTOOPT` returns `ChannelRefused(KERNEL_UNSUPPORTED)`.
     - `EINVAL` (which XNU returns on `LOCAL_PEERTOKEN` when the `listen()` caller has exited and
       been reaped, whereas `LOCAL_PEERPID` still returns the dead PID) or `ENOTCONN` (when the
       peer closed before `getsockopt`, old SPEC decisions 209/210) returns
       `ChannelRefused(PEER_LOOKUP_FAILED)`.
     - `euid != expected_uid` returns `ChannelRefused(UID_MISMATCH)`.
   - Darwin then queries `libproc` (`proc_pidinfo` with `PROC_PIDTBSDINFO = 3` and
     `PROC_PIDUNIQIDENTIFIERINFO = 17`) for `peer_pid`:
     - If `proc_pidinfo` fails or `pbi_status == SZOMB (5)`, returns
       `ChannelRefused(PEER_LOOKUP_FAILED)`.
     - If `p_idversion != peer_pidversion`, the PID was recycled since the token was minted;
       returns `ChannelRefused(NAMESPACE_MISMATCH)`.
     - Compares `pbi_pgid` against the jail's process group recorded in `jail_namespace_fd` (which
       on Darwin holds an open fd containing the jail supervisor's pgid after verifying the
       supervisor is alive and not a zombie); if they differ, returns
       `ChannelRefused(NAMESPACE_MISMATCH)`.

4. **Measured grade ceilings on Darwin (`seatbelt.ceilings`).**
   - **`fs_write`:**
     - `Grade.ENFORCED` when no non-writable carve-out (`write_denies`, `masks`, nested `readable`
       root, or `state_dir`) lies beneath a writable root: XNU's Seatbelt MAC policy blocks writes
       outside writable roots, blocks `link(2)` targeting read-only files (`EPERM`), and pins
       writable roots against `rmdir`/`rename`.
     - `Grade.BEST_EFFORT` when any non-writable carve-out lies beneath a writable root: Seatbelt
       matches by path string rather than mounted vnode, so if the *host* renames a read-only
       carve-out directory inside a writable root to an unguarded name (or hardlinks a denied file
       to a second name inside the writable root), the jailed process can write through the new
       host path.
   - **`fs_read`:** `Grade.BEST_EFFORT` (never `ENFORCED`). Even when `policy.readable` names only
     a small allowlist of roots, `(import "system.sb")` grants `file-read*` on macOS system paths
     (`/System`, `/usr/lib`, `/usr/share`, `/private/etc/passwd`, etc.) outside `policy.readable`,
     and path-based masks do not follow host-side renames or hardlinks of masked files inside a
     readable root.
   - **`env`:** `Grade.ENFORCED` (the supervisor spawns every command with `env=dict(request.env)`).
   - **`channel_exclusivity`:**
     - `Grade.VIOLATED` when any undeclared writable path is shared with the host.
     - `Grade.ENFORCED` when no undeclared writable path is shared with the host: unlike Linux bwrap
       without a socket-scoping filter, XNU's `(deny network* (with no-log))` blocks `connect()` and
       `bind()` on every `AF_UNIX` socket outside `channel_directory` in the kernel, even inside
       readable roots or `/tmp`.
   - **`network`:**
     - Without `EgressPolicy`: `Grade.ENFORCED` (XNU blocks all IP and Unix-domain network traffic
       outside `channel_directory`).
     - With `EgressPolicy`: `Grade.BEST_EFFORT`. While XNU blocks arbitrary remote hosts/ports and
       blocks DNS resolution (`/var/run/mDNSResponder`), SBPL's
       `(remote tcp "localhost:<bridge_port>")` matches any local interface IP address owned by the
       host (e.g. a LAN IP `<host_ip>:<bridge_port>`), whereas the supervisor's bridge binds
       `127.0.0.1:<bridge_port>` and `[::1]:<bridge_port>` on the shared host network stack. If a
       host service listens on `<host_ip>:<bridge_port>` (or `0.0.0.0:<bridge_port>`), a jailed
       process can connect to `<host_ip>:<bridge_port>` directly without traversing the proxy.

## Consequences

- `brig.domain.jail_types.seatbelt` and `brig.presentation.drivers.seatbelt` implement the Darwin
  Seatbelt jail slice (`create_seatbelt_jail`), re-exported from `brig`.
- `brig.infra` works on both Linux and Darwin (`placeholders`, `sockets`, `supervisor`, `proxy`,
  `process`).
- Every Seatbelt ceiling in `jail.report` is held to empirical measurement on Darwin by e2e
  batteries (`test_seatbelt_*.py`).

