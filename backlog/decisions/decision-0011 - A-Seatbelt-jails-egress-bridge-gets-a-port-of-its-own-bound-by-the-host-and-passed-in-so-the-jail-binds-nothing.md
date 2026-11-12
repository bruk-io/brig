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

Rejected: a host wildcard reservation of the port on every address, to stop a host program from
binding it at the LAN address. Measured: it refuses a plain bind but not one with
`SO_REUSEADDR` or `SO_REUSEPORT`, which most servers set, so it would cost two sockets per jail
for a guarantee it does not give.

## Consequences

- Jails with egress run side by side on one Mac (`test_two_jails_with_egress_run_at_once`, which
  fails with a fixed port).
- A jailed command cannot listen anywhere, so nothing off the host connects to it
  (`test_a_jailed_command_cannot_listen_for_a_connection_from_off_the_host`, which fails with the
  TASK-0061 rule restored); the command holds neither listener
  (`test_the_command_holds_none_of_the_bridge_s_listeners`, which fails without the
  close-on-exec).
- `network` with egress stays `BEST_EFFORT` on Darwin, for one reason now: SBPL's `localhost`
  matches every local address, so a host program that binds the jail's own port at another local
  address is reached past the proxy (`test_a_host_program_on_the_jails_port_at_another_address_
  is_reached_past_the_proxy` pins it). decision-0010 item 4 is amended to match.
- The wire gains `BRIDGE_LISTENER_FDS` and `bridge_inherited`; Linux's requests carry
  `bridge_inherited: false` and behave as before.
