---
id: decision-0009
title: >-
  Egress is enforced through one route: the jail keeps only loopback, the
  supervisor bridges it to a host-side proxy that allows granted hostnames and
  IP addresses per port
date: '2026-11-03T19:26:00Z'
status: proposed
---
## Context

TASK-0048, for TASK-0001's criterion 5 ("egress through the allowlisting proxy") and its open
question (cooperative, or enforced by relaying the jail's only route out through the supervisor).
An embedder asks for more than either answer gave before: its person approves network access per
hostname and/or IP address plus port, once or always, and a destination approved mid-session
should not cost the jail.

What exists:
- A bwrap jail is created with `--unshare-net`. Inside, the only interface is loopback. A program
  can reach nothing off-host, and it can resolve no name, because there is no resolver.
- The old brig ran a per-jail proxy outside the jail. The workload was pointed at it through
  `HTTPS_PROXY`, and `connect_proxy` graded `cooperative` because the workload could ignore it
  (old SPEC decisions 133, 134 and 170). Its host matcher was a pure function, unit-tested apart
  from the server. Its denials answered `403` with the destination named.
- The supervisor is PID 1 in the jail. It is non-dumpable, and the command holds no capabilities
  over it (decision-0006). It keeps a wire to its host-side link.
- TASK-0043 (decision-0008's note of 2026-11-03): `network` is capped by the socket half of
  `channel_exclusivity`. A host socket the jail can dial is a route out no proxy sees. That cap
  stays until DRAFT-0028's mechanism exists.
- Landlock on the target kernels is ABI 7. It scopes abstract Unix sockets only, so it cannot be
  the egress mechanism.

## Decision

1. **One route out.** The jail keeps `--unshare-net`. The supervisor listens on `127.0.0.1:<port>`
   inside the jail's network namespace, and on `[::1]` when the namespace has it. It bridges each
   accepted connection to the host-side proxy:
   - it makes a socketpair per connection;
   - it sends one end to the proxy over an fd it inherited at start, with SCM_RIGHTS;
   - it relays between the other end and the accepted connection.

   No path is involved, so nothing in the jail's view of the filesystem names the proxy.
   A program that ignores the proxy settings reaches nothing, because there is no other route.
   That makes egress enforced, not cooperative.
2. **The proxy.** It is a host-side program per jail, the old brig's shape:
   - **Imports and decisions:** standard library only, and it imports nothing of brig, which a gate
     row enforces. The allow/deny decision is a pure module, tested exhaustively in the unit tier.
   - **Lifetime:** it starts with the jail and ends with it. `destroy_jail` ends it (law 7).
   - **Protocols:** it speaks HTTP `CONNECT host:port` (TLS passes through, opaque), absolute-form
     plain HTTP, and SOCKS5 `CONNECT`. SOCKS5 covers raw TCP to a hostname (`socks5h`) or an IP
     literal.
3. **The policy.** `EgressPolicy(allow: tuple[Destination, ...])`:
   - **A destination is a host and a port.** The port is always required, and there are no port
     wildcards.
   - **The host is one of three forms:**
     - an exact hostname;
     - `*.suffix`, which matches any name under the suffix and not the suffix itself;
     - an exact IPv4 or IPv6 literal. CIDR ranges are not accepted.
   - **An empty `allow` is the default:** the jail gets loopback and nothing else.
4. **Names are resolved by the proxy, never by the jail.**
   - **A hostname grant:** applies to a request that names the host (`CONNECT`, an absolute URL,
     or `socks5h`). The proxy resolves it and connects to what it got back, so the program never
     picks the address.
   - **An IP grant:** applies only to a request that names that literal.
   - **Private addresses:** a hostname that resolves into loopback, link-local (169.254.169.254
     and its v6 equivalents), RFC 1918, unique-local, or the jail's own host addresses is refused.
     Only an IP-literal grant naming that address allows it. This keeps a rebinding name from
     reaching the host's own services.
5. **Grants can change during the jail's life.**
   - **Adding:** `allow_egress(jail, destination)` adds to the running proxy's allow list. It
     reaches the proxy over the same link as the per-connection fds. The jail is not restarted,
     because nothing inside it changes.
   - **Removing:** `revoke_egress(jail, destination)` removes an entry, and connections not yet
     made are refused.
   - **The report:** it states the policy as created and every change since.
6. **A refusal comes back to the embedder as data.**
   - **To the program:** the proxy answers `403` with a body naming the destination (the old
     signature, `brig: egress denied by policy: host:port`), or SOCKS reply `0x02`.
   - **To the embedder:** `egress_decisions(jail)` yields one value per decision (allowed or
     refused, destination, time), so it can ask its person about a refused destination and call
     `allow_egress`.
   - **To the log:** the proxy also writes each decision as one JSON line in brig's envelope
     (criterion 15). The library itself logs nothing.
7. **The environment.** brig sets `HTTP_PROXY`, `HTTPS_PROXY` and `ALL_PROXY` (and their lower-case
   forms), with `ALL_PROXY=socks5h://127.0.0.1:<port>`. It sets `NO_PROXY=` and `no_proxy=` empty,
   overriding the embedder's `EnvPolicy` for these names only (old decision-170). An `EnvPolicy`
   that names them is refused rather than silently overridden.
8. **The grade.**
   - **No egress policy:** `network` is computed as today.
   - **With an `EgressPolicy`:** the claim reads "reaches only the destinations the policy grants,
     and only through the proxy". Its ceiling is the socket-half cap of TASK-0043. The proxy route
     itself is enforced, so the residual is the host-socket gap DRAFT-0028 owns, and nothing more.
   - **Gaps the claim text names:**
     - HTTP `CONNECT` authority versus TLS SNI (domain fronting through a granted CDN);
     - the bytes inside a granted connection, which the proxy does not inspect.

## Consequences

- **New code:**
  - the domain's `EgressPolicy` and its compile (the supervisor's bridge arguments and the
    environment);
  - the bridge in the supervisor program;
  - the proxy program and its gate row;
  - `allow_egress`, `revoke_egress` and `egress_decisions` in the public API.
- **Batteries, each held to the ceiling:**
  - a program that ignores the proxy settings reaches nothing;
  - a granted hostname works over HTTP `CONNECT` and over SOCKS5;
  - an ungranted one is refused, and the refusal reaches `egress_decisions`;
  - a name resolving to 127.0.0.1 or 169.254.169.254 is refused without an IP grant;
  - a destination allowed mid-life works on the next connection without a restart;
  - `destroy_jail` leaves no proxy process or thread.
- **No UDP.** QUIC and HTTP/3 fail, and clients fall back to TCP. A program that does its own DNS
  fails: it has no resolver, which is the honest result.
- **Cost:** one proxy process per jail with a network policy, and none without one.
- **Not decided here:**
  - **IPv6 when the namespace lacks `::1`:** the bridge listens on IPv4 only, and that is stated.
  - **Seatbelt's equivalent:** Seatbelt can restrict network to a local port, so it can share the
    proxy and policy. That is left to TASK-0001's Seatbelt slice.
  - **Domain fronting:** a check that the SNI matches the `CONNECT` host is a possible later
    tightening. It needs no change to the policy.
- **For the embedder** (bh-02's capability-grants intent):
  - **What a grant is:** a network grant is a `Destination`.
  - **Once versus always:** both are `allow_egress` calls. "Always" is the embedder's to remember
    and pass in the `EgressPolicy` at the next create.
  - **No restart:** a mid-session approval costs no restart.
