---
id: TASK-0043
title: Three ceilings claim ENFORCED where only a list of places backs them
status: In Progress
assignee:
  - '@claude'
created_date: '2026-11-03T17:47:00Z'
updated_date: '2026-11-03T17:57:00Z'
labels:
  - brig
  - grades
  - size-3
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Architecture review 2026-11-03. (a) fs_write is ENFORCED with a readable root nested in a writable root; demonstrated: the host renamed W/vendor and made a new one, and the jail then wrote W/vendor/lib.py. ceilings (domain/jail_types/bwrap.py) counts only write_denies and masks; compute it from the mounts (any READ_ONLY under WRITABLE caps it). (b) channel_exclusivity is ENFORCED while the jail reaches a host agent socket outside SOCKET_DIRECTORIES; demonstrated with a gpg-agent socket under a home directory. (c) network stays ENFORCED when a socket the jail can dial gives it the network (reasoned). Principle proposed: a ceiling reaches ENFORCED only when a kernel mechanism holds the claim, never because a path list found nothing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 fs_write's ceiling is computed from the compiled mounts: any read-only mount beneath a writable one (a deny, a mask, a nested readable root) caps it at BEST_EFFORT; e2e: the host replaces a nested readable root and the jail writes into it, and the ceiling it reported allowed for that
- [ ] #2 channel_exclusivity is at most BEST_EFFORT whenever the jail sees any host path a socket could sit in beyond its own channel directory (a list of places is not a mechanism); VIOLATED stays for a visible SOCKET_DIRECTORIES entry or a writable shared root; e2e plants a socket outside the listed places and dials it
- [ ] #3 network is never stronger than channel_exclusivity, since a dialable host socket can carry the network; a unit test pins the ordering
- [ ] #4 decision-0008 is amended (a dated note) with the rule that ENFORCED needs a kernel mechanism, and a draft names the mechanism that could earn channel_exclusivity and network back (Landlock here is ABI 7: abstract sockets only; a supervisor-held listening fd plus a seccomp filter on socket(AF_UNIX) is the candidate)
<!-- AC:END -->

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
<!-- SECTION:NOTES:END -->
