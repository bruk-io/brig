---
id: decision-0005
title: >-
  Channel readiness compares the listen() caller's PID namespace with the jail's
  own, inside a same-uid trust boundary
date: '2026-10-19 12:59'
status: accepted
---
## Context

Decision-0002 item 2 says a channel is ready when "a connect that succeeds *and* is confirmed
to be the process's own listener, never path existence". It does not say how that
confirmation works. Under `--unshare-all` the jail has its own PID namespace, so a peer pid
read off the socket on the host is a host pid and is not directly comparable to anything the
jail reports about itself. TASK-0001.24 was the spike that measured an answer on real bwrap
(0.9.0, kernel 6.12.76-linuxkit, Python 3.12.3, a `--privileged` Docker container standing in
for the host). Two skeptics then re-ran it and attacked it.

What was measured:

- The in-jail PID 1 is bwrap's direct child whose `/proc/<pid>/status` `NSpid` ends in `1`.
  Its `/proc/<pid>/ns/pid` is the jail's PID namespace. bwrap's own `ns/pid` is the host's,
  so bwrap is the wrong reference.
- A verified check (connect, then read the peer's pid with `SO_PEERPIDFD`/`SO_PEERCRED`,
  readlink `/proc/<pid>/ns/pid`, confirm the pidfd's fdinfo `Pid:` still equals that pid,
  compare with the jail's namespace) read READY for the jail's own listener, and refused a
  jail-planted symlink to a host listener (2a), a co-tenant-planted symlink (2b) and a
  co-tenant's real socket bound at the reserved path (2c). A path with nothing listening
  (stale socket, regular file, dangling symlink) read not ready because connect itself
  failed. A listener in a PID namespace nested under the jail's was refused (case 4).
- The path-based alternative (lstat, refuse a symlink, require `S_ISSOCK`) accepted 2c: a
  real socket inode says nothing about who is listening. uid cannot tell them apart either:
  the outside listener had the jail's uid in every run.
- Skeptic B (attack lens) refuted the spike's threat model with two same-uid bypasses, both
  measured READY:
  1. A same-uid host co-tenant opens the jail's `ns/pid`, takes its owning (outer) user
     namespace with `ioctl(NS_GET_USERNS)`, calls `setns` for the user and PID namespaces,
     forks, and listens at the reserved path from the host mount namespace. The verified
     check, strict and nested walk alike, read READY with the jail's namespace, and the
     connection was answered by the co-tenant. Going through the inner user namespace,
     `setns` into the PID namespace fails with EPERM; going through the outer one works.
     Measured as uid 1000 and as uid 0.
  2. A jail process calls `listen()` and passes the listening fd to a host process over
     `SCM_RIGHTS`. Readiness reads READY and the host process answers, because
     `SO_PEERCRED` and `SO_PEERPIDFD` name the process that called `listen()`, not the one
     that accepts. A variant where the `listen()` caller hands off the fd and exits (left an
     unreaped zombie under the jail's PID 1) also read READY (case C2).
- Skeptic B also measured three attacks the check survives: a co-tenant hard-linking its
  socket inode at the reserved path (refused), the jail hard-linking an outside socket into
  the channel directory (EXDEV across the bind, so not ready), and a sibling jail listening
  at the victim's reserved path (refused, different PID namespace).
- Skeptic A (reproduction lens) reproduced every verdict and found that its uid-1000
  co-tenant got EPERM (`reassociate to namespace 'ns/pid' failed`), but that came from
  `nsenter --user` into the inner user namespace. The outer path above works for the same
  uid, and a root co-tenant using `nsenter` read READY. A listener under a different uid
  fails closed: run as uid 1000 against a uid-2000 listener (set up as root), the check
  could not read its namespace (`rejected(peer-gone EACCES)`). Whether a different-uid
  co-tenant can join the jail's namespaces was not measured.
- Both skeptics measured that when the `listen()` caller has exited and been reaped while a
  child keeps the socket, `getsockopt(SO_PEERPIDFD)` raises EINVAL. It does not hand back a
  pidfd whose fdinfo says `Pid: -1`, as the spike guessed, and the spike's probe let the
  error escape. Kernels before 6.5 have no `SO_PEERPIDFD`, and the `SO_PEERCRED`-only
  fallback the spike proposed reopens exactly that pid-reuse window.

## Decision

**Readiness compares the PID namespace of the process that called `listen()` on the socket
that answered the connect against the PID namespace of the jail's in-jail PID 1. It never
compares the path, and it never compares uid.**

1. **The mechanism on Linux (bwrap).** At jail start the host finds bwrap's child whose
   `NSpid` ends in `1`, reads its `/proc/<pid>/ns/pid`, and holds an fd open on that
   namespace for the jail's lifetime so the nsfs inode cannot be recycled. Readiness then
   connects to the reserved path. ENOENT or ECONNREFUSED means not ready. On success it
   reads the peer through `SO_PEERPIDFD` on the connected socket, reads the peer's
   `/proc/<pid>/ns/pid`, and re-checks the pidfd so a reused pid cannot pass. Ready only if
   the two namespaces are equal. The check runs on the connected socket, not the path, so a
   swap between any pre-check and the connect cannot change the outcome. Readiness is a
   property of that one connection; a consumer that reconnects must verify again.
2. **Strict equality.** A listener in a namespace nested under the jail's is refused. The
   `NS_GET_PARENT` walk that would accept it was measured and rejected as the default: it
   adds an ioctl loop and no security, and nothing needs nested namespaces today.
3. **The threat-model boundary, per the owner's ruling.** Same-uid host processes are inside
   the jail's trust boundary. Such a process holds `CAP_SYS_ADMIN` over the jail's user
   namespace and can usually ptrace it, so no socket-level check can defend against it.
   Both measured same-uid bypasses (the `NS_GET_USERNS` plus `setns` listener, and the
   `SCM_RIGHTS` hand-off of a listening fd) are therefore out of scope, and named here so
   no grade or document claims otherwise. Only a per-jail uid would close them, and that is
   not being done. A listener under a different uid fails closed, as measured: its
   `ns/pid` cannot be read (EACCES), so readiness refuses. Whether a different-uid
   co-tenant can join the jail's namespaces was not measured.
4. **What readiness proves.** It proves that a process in the jail's PID namespace called
   `listen()` on the socket that answered this connect. It does not prove that process is
   the one accepting, that it is still alive, or that it is the process the embedder
   meant. Documentation, errors and grades say exactly that.
5. **Every peer-lookup OSError is a refusal.** Any error from `SO_PEERPIDFD`, the
   `ns/pid` readlink or the pidfd re-check (EINVAL from a reaped peer, EACCES from a
   different-uid peer, ESRCH, anything else) yields a typed refusal value. It is never
   raised out of the readiness primitive, and it never falls back to the bare
   `SO_PEERCRED` pid.
6. **Kernels without `SO_PEERPIDFD` (before 6.5) fail closed.** Readiness refuses with a
   typed reason saying the kernel cannot verify the peer. It does not fall back to
   `SO_PEERCRED` alone.
7. **Seatbelt, stated and not measured.** macOS has no PID namespace. The check there would
   read the peer's audit token with `LOCAL_PEERTOKEN` (pid plus pidversion, which closes
   pid reuse) and walk ancestry through `proc_pidinfo(PROC_PIDTBSDINFO)` to the Seatbelt
   supervisor. That is weaker than the Linux check: there is no namespace boundary, an
   orphan reparented to launchd fails the walk (closed), and the walk races reparenting.
   It must be measured before a Seatbelt readiness task claims it.

This **refines, not reverses**, decision-0002 item 2. "Confirmed to be the process's own
listener" now has a precise meaning (item 4) and a stated trust boundary (item 3). The shape
decision-0002 set (`domain/channels.py`, `infra/sockets.py`, a readiness primitive behind
`presentation/ports.py`, the reservation passed in argv) is unchanged.

## Consequences

- TASK-0001.27 implements items 1, 2, 5 and 6, and its acceptance criteria say so: every
  peer-lookup OSError is a refusal pinned by a test, and a kernel without `SO_PEERPIDFD`
  refuses with a typed reason. Its battery plants the confused deputy (2a, 2b, 2c) and the
  positive control; it does not try to defend against the same-uid bypasses.
- The jail's namespace identity (an open fd on it) has to be threaded from where infra
  spawns bwrap to the readiness primitive. The readiness API hands back the verified
  connected socket, or requires verification on every connect.
- The `channel_exclusivity` grade (TASK-0001.28) cannot claim protection against a same-uid
  host process. Its evidence covers different-uid listeners and planted paths only.
- The kernel floor for verified readiness on Linux is 6.5. Older kernels get a refusal, not
  a weaker check.
- Not measured, and open until a task measures them: a different-uid co-tenant trying to
  join the jail's namespaces, a bare-metal host, setuid bwrap,
  `--disable-userns`, the `/proc/<bwrap>/task/*/children` lookup, a symlink swapped during
  connect, and Seatbelt.

## Acceptance

Accepted by the owner (@bruk) in conversation, 2026-10-19: same-uid host processes are
inside the jail's trust boundary, and readiness means "a process in the jail's PID namespace
called listen() on the socket that answered this connect".
