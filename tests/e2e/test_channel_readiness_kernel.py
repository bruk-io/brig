"""TASK-0001.27 AC#5 (reworded 2026-10-25): on a kernel without `SO_PEERPIDFD`
(Linux before 6.5), `channel_ready` refuses with a typed reason and never falls back
to `SO_PEERCRED` alone.

No real pre-6.5 kernel is available to this project's own CI (`ubuntu-latest` is
always 6.5+), and decision-0001 rule 5 forbids patching the kernel or the `socket`
module to fake one -- the owner's own ruling (@bruk, 2026-10-25, in response to the
reviewer confirming the original wording was unsatisfiable by any run this project
will ever execute) was to prove the refusal *logic* instead, by injecting the one
piece of kernel-dependent data `channel_ready` reads: the `SOL_SOCKET` option number
for the peer-pidfd lookup (`channel_ready`'s own `so_peerpidfd` parameter, this
module's own seam). A socket option number no real kernel defines makes the real
`getsockopt` call -- against a real, live, in-namespace listener -- fail exactly the
way a genuine missing `SO_PEERPIDFD` would: `getsockopt` cannot tell "this number is
unassigned" apart from "this number is assigned but this kernel predates it", so the
`OSError` this test gets and the `OSError` a pre-6.5 kernel's real `SO_PEERPIDFD`
would raise are the same shape, reaching the identical `except OSError` arm inside
`channel_ready`. This is determinism entering as data, not by patching (this repo's
own Python rule) -- real sockets, a real subprocess, nothing mocked.

Runs on every *Linux* host this suite runs on -- including `ubuntu-latest` in CI,
regardless of its kernel actually having `SO_PEERPIDFD` or not, which is the whole
point of the injected seam. Still skips on macOS, but no longer for the original,
unfixable reason (needing a literal pre-6.5 kernel): measured directly, on this
macOS host `channel_ready`'s *first* lookup, `SO_PEERCRED`, already fails before
this test's own injected option is ever reached -- `socket.SO_PEERCRED` does not
exist here, and its hardcoded numeric fallback (`17`, Linux's own assignment) names
nothing meaningful in macOS's own `SOL_SOCKET` option space, so `getsockopt` raises
there regardless of `so_peerpidfd`. That is decision-0005 item 7's own point, not a
gap this task introduces or should paper over: `SO_PEERCRED`/`SO_PEERPIDFD` are
Linux's PID-namespace mechanism; macOS has no PID namespace, and its own equivalent
(`LOCAL_PEERTOKEN`, a different struct entirely) is a separate, unmeasured task.
"""

import contextlib
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator

import pytest

from brig.infra import sockets

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="SO_PEERCRED has no macOS equivalent by this name or number "
    "(decision-0005 item 7); channel_ready fails before this test's own injected "
    "SO_PEERPIDFD seam is ever reached, for an unrelated, already-documented "
    "reason -- this is not what AC#5 pins",
)

_LISTENER = r"""
import socket, sys
listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
listener.bind(sys.argv[1])
listener.listen(8)
print("up", flush=True)
while True:
    connection, _ = listener.accept()
    connection.close()
"""

_NO_REAL_KERNEL_DEFINES_THIS = 0x7FFFFFFF
"""A `SOL_SOCKET` option number reserved by no kernel this project targets: Linux's
own option numbers are small, densely assigned integers (`SO_PEERPIDFD` is 77), so a
32-bit signed max is never going to collide with a real one -- on any kernel, this
`getsockopt` call fails the same way a genuinely absent `SO_PEERPIDFD` would.
"""


@contextlib.contextmanager
def _short_socket_dir() -> Iterator[str]:
    """A throwaway directory under `/tmp` directly, not pytest's own `tmp_path`.

    `AF_UNIX` bind/connect paths are limited to roughly 104 bytes
    (`sizeof(sockaddr_un.sun_path)`), and pytest's own `tmp_path` nests under
    `tempfile.gettempdir()` (on macOS, a per-user path under `/var/folders/...`)
    plus `pytest-of-<user>/pytest-<N>/<test name>/` -- long enough on its own,
    before this test's own socket filename, to exceed that limit (measured:
    `OSError: AF_UNIX path too long`, not a path that happens not to exist).
    `/tmp` itself is four bytes; everything this module's own sockets need fits
    comfortably under the limit built from here instead.
    """
    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        yield directory


def test_a_kernel_without_so_peerpidfd_refuses_with_a_typed_reason() -> None:
    """AC#5: no `SO_PEERPIDFD` means `ChannelRefused(KERNEL_UNSUPPORTED)` -- a value,
    not a raise, and not a ready verdict reached by trusting the `SO_PEERCRED` pid
    alone.

    A real listener accepts the connect and really is in this process's own PID
    namespace (it is this process's own child), so the *only* reason this refuses is
    the option this test injects. A `channel_ready` that fell back to `SO_PEERCRED`
    would find a live, legitimately-in-namespace peer and report ready -- exactly the
    fallback AC#5 forbids; this test's positive setup is what makes that fallback's
    absence the thing actually being pinned, not an accident of a dead listener.
    """
    with _short_socket_dir() as directory:
        listener_path = f"{directory}/svc.sock"
        listener = subprocess.Popen(
            [sys.executable, "-c", _LISTENER, listener_path], stdout=subprocess.PIPE
        )
        assert listener.stdout is not None
        assert listener.stdout.readline() == b"up\n"
        time.sleep(0.1)

        # Never dereferenced: `channel_ready` refuses before it ever reads this fd's
        # own path, so it does not have to name a real namespace -- `os.devnull` is
        # simply the shortest-lived, most innocuous fd to open and close on every
        # platform.
        placeholder_fd = os.open(os.devnull, os.O_RDONLY)
        try:
            outcome = sockets.channel_ready(
                listener_path, placeholder_fd, so_peerpidfd=_NO_REAL_KERNEL_DEFINES_THIS
            )
        finally:
            os.close(placeholder_fd)
            listener.kill()
            listener.wait()
            listener.stdout.close()

    assert outcome == sockets.ChannelRefused(sockets.KERNEL_UNSUPPORTED)


def test_the_real_so_peerpidfd_default_does_not_report_kernel_unsupported() -> None:
    """Positive control: with no override, `channel_ready` must never itself report
    `KERNEL_UNSUPPORTED` against a real, live, in-namespace peer on this (Linux,
    `pytestmark`-gated) host -- if it did, that would mean
    `_NO_REAL_KERNEL_DEFINES_THIS` collided with the real option after all, not that
    this host genuinely lacks `SO_PEERPIDFD`, which is exactly the false positive
    the test above would otherwise be unable to tell apart from a real refusal.

    Calls `channel_ready` itself, with no override -- the gap this replaces: an
    earlier version of this test only probed `getsockopt` directly and asserted
    `real_support in (True, False)`, which cannot fail and never calls the function
    this whole module is about.
    """
    with _short_socket_dir() as directory:
        listener_path = f"{directory}/svc.sock"
        listener = subprocess.Popen(
            [sys.executable, "-c", _LISTENER, listener_path], stdout=subprocess.PIPE
        )
        assert listener.stdout is not None
        assert listener.stdout.readline() == b"up\n"
        time.sleep(0.1)

        # The listener is this test's own direct child, in this process's own PID
        # namespace -- so, with the real `SO_PEERPIDFD`, the only two readings
        # `channel_ready` can honestly give are `ChannelReady` (this host supports
        # the option) or some other, non-kernel refusal; never `KERNEL_UNSUPPORTED`.
        namespace_fd = os.open(f"/proc/{os.getpid()}/ns/pid", os.O_RDONLY)
        try:
            outcome = sockets.channel_ready(listener_path, namespace_fd)
        finally:
            os.close(namespace_fd)
            listener.kill()
            listener.wait()
            listener.stdout.close()

    assert outcome != sockets.ChannelRefused(sockets.KERNEL_UNSUPPORTED)
