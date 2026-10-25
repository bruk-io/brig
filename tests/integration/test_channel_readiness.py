"""Integration tests for `await_channel_ready` (TASK-0001.27 AC#1): through brig's
public API, with the world faked at infra's edge, the polling loop retries a channel
that is not ready yet, stops the moment it is ready or refused, and reports the last
"not ready" once its own deadline passes.

`FakeChannelReadiness` scripts the sequence and records every `(path,
jail_namespace_fd)` it was asked about, so each assertion reads exactly what brig
asked the world. The `Jail` is built directly, the way
`tests/e2e/test_processes_gateway.py` builds one, rather than through
`create_bwrap_jail`: this layer is the loop's own logic, and a `Jail` built by hand
is the shortest path to a fabricated `channel_namespace_fd` -- no real socket, no
real `/proc`, and no real bwrap is involved in any test here.
"""

from dataclasses import dataclass
from typing import Any, cast

import pytest
from tests.integration.fakes import FakeChannelReadiness, FakeSupervisors

from brig import (
    Channel,
    ChannelNotReady,
    ChannelReadinessRefusal,
    ChannelReady,
    ChannelRefused,
    Jail,
    Reservation,
    await_channel_ready,
    reserve_channels,
)

_NAMESPACE_FD = 7
"""The fd a test's own `Jail` carries. The fake never dereferences it, so any number
works; naming it once makes "the jail's own fd reached every attempt" what the
assertions read.
"""


def _jail(namespace_fd: int | None = _NAMESPACE_FD) -> Jail:
    """A `Jail` built directly, outside `create_bwrap_jail`: a fabricated process
    identity, a fabricated supervisor port, and the namespace fd under test.

    `process` is cast rather than constructed because brig exports no `Process` type
    (decision-0001 rule 4: a driver never reads it, and nothing here does either) --
    the same way `tests/e2e/test_processes_gateway.py` builds a `Jail` by hand.
    """
    return Jail(
        process=cast(Any, _FabricatedProcess(pid=4242, pgid=4242)),
        supervisors=FakeSupervisors(),
        channel_namespace_fd=namespace_fd,
    )


@dataclass(frozen=True)
class _FabricatedProcess:
    """The two fields a `Jail`'s `process` is read for, named here so this module
    does not reach into `brig.infra` for them (a fake never imports past brig's
    public API).
    """

    pid: int
    pgid: int


def _reservation(name: str = "ctl") -> Reservation:
    """A reservation for `name`, built through domain's own `reserve` (via
    `reserve_channels`) so its `bound_path` is the real join rather than a string
    this test made up. Each call allocates a fresh channel directory, so a test that
    needs the same path twice keeps the one reservation it made.
    """
    reserved = reserve_channels((Channel(name),))
    assert not isinstance(reserved, ChannelRefused)
    (reservation,) = reserved.reservations
    return reservation


@pytest.mark.parametrize(
    "outcomes",
    [
        [ChannelNotReady(), ChannelNotReady(), ChannelReady()],
        [ChannelReady()],
    ],
    ids=["not-ready-twice-then-ready", "ready-first"],
)
def test_the_loop_keeps_asking_until_the_channel_reads_ready(
    outcomes: list[ChannelReady | ChannelNotReady | ChannelRefused],
) -> None:
    """`ChannelNotReady` is the only transient outcome: the loop keeps asking and
    reports ready once it arrives. `ChannelReady` is terminal, so a script of one
    costs exactly one attempt.
    """
    readiness = FakeChannelReadiness(outcomes=outcomes)
    reservation = _reservation()

    outcome = await_channel_ready(_jail(), reservation, readiness=readiness)

    assert outcome == ChannelReady()
    assert len(readiness.asked) == len(outcomes)
    assert {path for path, _fd in readiness.asked} == {reservation.bound_path}
    assert {fd for _path, fd in readiness.asked} == {_NAMESPACE_FD}


def test_a_refusal_stops_the_loop_at_once_and_is_never_retried() -> None:
    """A refusal is a security answer about *this* connection, not a transient state
    (decision-0005 item 1): the loop returns it immediately rather than polling on,
    even though the script would have handed back ready next.
    """
    readiness = FakeChannelReadiness(
        outcomes=[
            ChannelRefused(ChannelReadinessRefusal.PEER_OUTSIDE_JAIL),
            ChannelReady(),
        ]
    )

    outcome = await_channel_ready(_jail(), _reservation(), readiness=readiness)

    assert outcome == ChannelRefused(ChannelReadinessRefusal.PEER_OUTSIDE_JAIL)
    assert len(readiness.asked) == 1


def test_the_loop_gives_up_at_its_deadline_and_reports_the_last_not_ready() -> None:
    """Nothing ever becomes ready: once `timeout_s` passes, the last
    `ChannelNotReady` comes back -- never a raise, and never a fabricated ready. The
    deadline is the test's own, set short so the poll count stays small.
    """
    readiness = FakeChannelReadiness(outcomes=[ChannelNotReady()])

    outcome = await_channel_ready(_jail(), _reservation(), timeout_s=0.05, readiness=readiness)

    assert outcome == ChannelNotReady()
    assert len(readiness.asked) >= 1


@pytest.mark.parametrize(
    "reason",
    list(ChannelReadinessRefusal),
    ids=lambda reason: reason.value,
)
def test_every_refusal_reason_reaches_the_caller_unchanged(
    reason: ChannelReadinessRefusal,
) -> None:
    """Each of decision-0005's three reasons survives the trip, including
    `KERNEL_UNSUPPORTED`, which an embedder has to be able to tell apart from a peer
    that was actually seen and rejected (AC#5): the two call for different responses
    from a caller.
    """
    readiness = FakeChannelReadiness(outcomes=[ChannelRefused(reason)])

    outcome = await_channel_ready(_jail(), _reservation(), readiness=readiness)

    assert outcome == ChannelRefused(reason)
