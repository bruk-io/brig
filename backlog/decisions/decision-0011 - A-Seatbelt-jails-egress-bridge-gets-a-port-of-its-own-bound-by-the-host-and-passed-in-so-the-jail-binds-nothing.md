---
id: decision-0011
title: >-
  A Seatbelt jail's egress bridge gets a port of its own, bound by the host and
  passed in, so the jail binds nothing
date: '2026-11-12 05:04'
status: proposed
---
## Context

TASK-0063. On Darwin a Seatbelt jail shares the host's network stack, and decision-0010 gave
every jail with egress the same bridge port, 3128, which the supervisor bound inside the jail
under `(allow network-bind network-inbound (local tcp "localhost:3128"))`. Measured in TASK-0061's
review and again here: only one egress jail could run per host (a second's supervisor could not
bind and its command never started), and the bind rule let a jailed command listen on
`0.0.0.0:3128` with `SO_REUSEADDR`, reachable from the LAN. bh-02 starts two jails with egress
(its Python REPL and its extensions process), so on a Mac the second never started.

**Whose choice this is.** The orchestrator chose a port per jail on Bruk's behalf, as it had
recommended in TASK-0061's review; Bruk has not confirmed it. This record is `proposed` until he
does.

## Decision

1. **A port per jail, picked by the kernel and bound by the host.** `create_seatbelt_jail` binds
   `127.0.0.1:0` and `[::1]` at the port the kernel hands out (another is tried if a program
   already holds `[::1]` there), each with no address-reuse option, and listens
   (`infra.sockets.bridge_listeners`). The proxy variables and the profile name that port.
2. **The jail binds nothing.** The host passes both listeners to the supervisor as
   `wire.BRIDGE_LISTENER_FDS` (6 and 7; the exec request says `bridge_inherited`). The supervisor
   marks them close-on-exec before it starts anything and accepts on them. The profile's one
   network rule for egress is `(allow network-outbound (remote tcp "localhost:<port>"))`; no
   `network-bind`, no `network-inbound`. Measured: accepting on listeners passed in needs neither,
   and with only the outbound rule every bind in the jail is `EPERM`.
3. **bwrap is unchanged.** Its supervisor binds 3128 in the jail's own network namespace, where no
   other jail or host program can hold it.

4. **The port is held at every local address.** *Amended 2026-11-12, DRAFT-0036.* SBPL's
   `localhost` matches every local address, and holding only the two loopbacks left the port
   free elsewhere: measured by the review, a plain bind with no reuse option succeeded at the
   LAN address, at `fe80::1%lo0` and at the Wi-Fi link-local address, and a jailed connect to
   `localhost:<port>` reached all three. So `bridge_listeners` also binds the port, with no
   reuse option and without listening, at every other address `getifaddrs` lists at create,
   IPv4 and IPv6, link-local included (another port is tried if any program holds it at one).
   Measured: each later squatter there, plain, `SO_REUSEADDR` or `SO_REUSEPORT`, then fails
   `EADDRINUSE`; a wildcard squatter with `SO_REUSEADDR` binds, but a connect to the LAN
   address at the port does not reach it. The host holds the listeners and the reservations on
   the `Jail` until `destroy_jail` (released once the jail is verified gone), so the port
   stays the jail's after its supervisor has exited while any process of it may live.

Rejected: a single wildcard reservation of the port. Measured: it refuses a plain bind at the LAN
address but not one with `SO_REUSEADDR` or `SO_REUSEPORT`, so it gives no guarantee; a
reservation at each specific address does.

## Consequences

- Jails with egress run side by side on one Mac (`test_two_jails_with_egress_run_at_once`, which
  fails with a fixed port).
- A jailed command cannot listen anywhere, so nothing off the host connects to it
  (`test_a_jailed_command_cannot_listen_for_a_connection_from_off_the_host`, which fails with the
  TASK-0061 rule restored); the command holds neither listener
  (`test_the_command_holds_none_of_the_bridge_s_listeners`, which fails without the
  close-on-exec).
- `network` with egress stays `BEST_EFFORT` on Darwin, for one reason now: an address that
  appears after create (a DHCP change, a VPN coming up) is not held, and a program that binds the
  jail's port there is reached past the proxy. Not measured here: adding an address needs root.
  `test_a_host_program_cannot_take_the_jails_port_at_another_local_address` holds the rest,
  beside an unjailed control (with only the loopbacks held, every squatter binds) and fails
  without the reservations. decision-0010 item 4 is amended to match.
- The wire gains `BRIDGE_LISTENER_FDS` and `bridge_inherited`; Linux's requests carry
  `bridge_inherited: false` and behave as before.
