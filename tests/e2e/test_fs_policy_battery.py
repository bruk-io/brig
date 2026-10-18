"""E2E battery for the filesystem policy (TASK-0001.16 AC#3).

`create_bwrap_jail`'s new `policy` parameter (`domain/policy/paths.py`'s `FsPolicy`)
names exactly which host paths a jail sees; anything it does not name should be
unreachable inside the jail, regardless of whether the host process running this
test can see it. This battery plants one such path -- a file under a fresh `/tmp`
directory this test creates for itself -- and grades the actual claim through the
public API (`create_bwrap_jail`/`run_jail`/`destroy_jail`), with a positive control
proving the exact same path *is* reachable under `WHOLE_HOST_READ_ONLY`, the
default every jail got before this parameter existed (rule 11: evidence, not a
happy path alone). A second pair of tests grades `Bind.writable` the same way:
AC#3's own text asks for "unreadable/unwritable", and translating `writable` into
`--bind` (`tests/unit/test_bwrap_compile.py`) is not evidence that flag changes
what the jail can actually do.

The narrowed policy the read/unreadable pair builds is not the single planted path
alone: a policy that bound only that one path would trivially deny it for the
wrong reason (nothing else would be reachable either, including the interpreter
and this repository the jail's own supervisor needs to start at all --
`JailSpawnFailed` or `JailExitUnknown` would be the honest outcome, ambiguous the
same way DRAFT-0010 is for a jailed command's own stdio, and rule 11 exists to
rule exactly that out). Instead it mirrors `WHOLE_HOST_READ_ONLY`'s own practical
coverage -- binding every top-level entry of the host's own root, read-only, the
same thing a single `--ro-bind / /` already covers -- except the one entry
(`/tmp`) this test's own secret lives under, so the interpreter and this
repository (wherever either actually live under `/`) stay reachable and only the
planted path is withheld. Virtual filesystems (`/proc`, `/sys`, `/dev`, `/run`)
are left out of the mirror entirely, needed by nothing this battery's probes do.
Even so, the probe itself also checks a second, known-bound control path (the
interpreter running it) every time, and reports a result distinct from "denied"
if that one is missing too -- so a host where the mirror's assumption happens to
be wrong fails loudly, as a broken jail, rather than silently passing as a denial
that was never actually exercised.

Every real-jail test here needs a real bwrap jail, so each is guarded the same way
every other real-jail battery in this suite is: skipped cleanly where bwrap is not
installed (macOS), run for real in CI on Linux.
"""

import os
import shutil
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest

from brig import WHOLE_HOST_READ_ONLY, Bind, FsPolicy, create_bwrap_jail, destroy_jail, run_jail

_VIRTUAL_FILESYSTEMS = frozenset({"proc", "sys", "dev", "run"})
"""Top-level entries `_mirror_policy_excluding` never binds, mirror or not: none of
them is a plain, bindable directory of host files the way the rest of `/`'s
top-level entries are, and this battery's probes need none of them to run.
"""

_PLANTED_CONTENT = "brig-fs-policy-battery-secret"

_READ_PROBE = """
import errno, os, sys

def _secret_or_errno(path):
    try:
        with open(path) as f:
            return f.read(), None
    except OSError as exc:
        return None, exc.errno

def _control_errno(path):
    try:
        os.stat(path)
        return None
    except OSError as exc:
        return exc.errno

secret_content, secret_errno = _secret_or_errno(sys.argv[1])
control_errno = _control_errno(sys.argv[2])
if control_errno is not None:
    sys.exit(4)  # the control path (the interpreter running this) is missing
                 # too -- this jail is broken for a reason unrelated to the
                 # claim this battery grades, not evidence of anything about
                 # the planted path
if secret_errno is None:
    sys.exit(0 if secret_content == sys.argv[3] else 5)  # 5: read, wrong content
sys.exit(2 if secret_errno == errno.ENOENT else 1)
"""
"""The probe command, run as `python -c <this> <secret> <control> <content>`:
reports what happened through its exit code alone -- never a pipe, since the
supervised command's own stdout is the supervisor's wire pipe now (DRAFT-0010;
this suite's other batteries, `_FSTAT_PROBE` and `_TIOCSTI_PROBE`, already follow
the same discipline for the same reason).

`sys.argv[2]`, the control path, is always `sys.executable` -- a path every
policy this file builds binds, by construction (the interpreter has to be
reachable merely for the supervisor to start it, before this probe ever runs).
Checking it from inside the probe itself, not only reasoning about the policy
from the test's own side, is what makes a result self-discriminating: `4` means
the jail itself is broken in a way this battery does not mean to grade, and
every other exit code below is only trustworthy once `4` has been ruled out.
`os.stat`, not `open().read()`: the interpreter's own binary is not text, and
decoding it as UTF-8 to check it exists was measured to fail with a
`UnicodeDecodeError` this battery does not care about -- existence is all the
control path needs to prove.

`0`: the secret path read back exactly `_PLANTED_CONTENT`, so it is genuinely
reachable, not merely open-able. `5`: it opened but did not read back that exact
content -- never expected, but distinct from `0` rather than silently treated as
a pass if it ever happened. `2`: `ENOENT` -- the secret path does not exist
inside the jail at all, exactly what an unbound path looks like under this
policy model's allow-list (nothing named is simply absent, not merely
permission-denied). `1`: some other `OSError` on the secret path, which this
battery never expects and would want to see distinctly from `2`.
"""

_WRITE_PROBE = """
import errno, sys

try:
    with open(sys.argv[1], "w") as f:
        f.write(sys.argv[2])
    sys.exit(0)
except OSError as exc:
    sys.exit(2 if exc.errno == errno.EROFS else 1)
"""
"""The probe command for the writable-bind pair: tries to write `sys.argv[2]` to
the path named by `sys.argv[1]` and reports the outcome through its exit code
alone, the same discipline `_READ_PROBE` follows. `0`: the write succeeded. `2`:
`EROFS` -- the bind covering this path is read-only, exactly what a `Bind` with
`writable=False` (or no bind naming `writable=True`) should produce. `1`: some
other `OSError`, which this battery never expects.
"""


def _mirror_policy_excluding(*excluded_names: str) -> FsPolicy:
    """An `FsPolicy` that binds every top-level entry of the host's own root,
    read-only, except `_VIRTUAL_FILESYSTEMS` and whatever `excluded_names` names.

    Reproduces `WHOLE_HOST_READ_ONLY`'s own practical coverage of the interpreter
    and this repository -- wherever either actually live under `/`, this test has
    no way to know from the public API alone (rule 4 forbids reaching past it to
    ask) -- while genuinely withholding `excluded_names`, by construction rather
    than by naming the specific paths the supervisor happens to need on this host.
    Skips a name bwrap could never bind anyway (a dangling symlink at the host's
    own root, say): `_READ_PROBE`'s own control-path check is this battery's real
    guard against a policy that quietly fails to cover what it needs to, not this
    filter -- this is only about not asking bwrap to bind something that is not
    there at all.
    """
    skip = _VIRTUAL_FILESYSTEMS | set(excluded_names)
    binds = tuple(
        Bind(host_path=f"/{name}", jail_path=f"/{name}")
        for name in sorted(os.listdir("/"))
        if name not in skip and os.path.exists(f"/{name}")
    )
    return FsPolicy(binds=binds)


@contextmanager
def _fresh_tmp_dir() -> Generator[str]:
    """A fresh directory of its own beneath `/tmp`, removed again once the
    caller is done with it -- a fresh directory, not a fixed name, so a previous
    run's (or another test's) leftover can never be what a jail actually reads
    or writes back.
    """
    path = tempfile.mkdtemp(dir="/tmp")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_a_path_outside_the_policy_is_unreadable_in_a_real_bwrap_jail() -> None:
    """TASK-0001.16 AC#3's planted violation: a path under `/tmp`, which this
    narrowed policy never binds, cannot be read from inside a real bwrap jail --
    `--ro-bind`/`--bind` name an allow-list, so a path outside it is not merely
    permission-denied, it does not exist in the jail's own mount namespace at all
    (`ENOENT`, this battery's probe's own exit code `2`). Exit code `4` would mean
    the jail itself never got far enough to prove anything about the secret path
    at all -- distinct from `2`, and checked first by the probe itself.
    """
    with _fresh_tmp_dir() as secret_dir:
        secret_path = Path(secret_dir) / "secret.txt"
        secret_path.write_text(_PLANTED_CONTENT)
        policy = _mirror_policy_excluding("tmp")

        jail = create_bwrap_jail(
            (sys.executable, "-c", _READ_PROBE, str(secret_path), sys.executable, _PLANTED_CONTENT),
            policy=policy,
        )
        exit_code = run_jail(jail)
        destroy_jail(jail)

    assert exit_code == 2  # ENOENT: /tmp was never bound under this policy


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_positive_control_the_same_path_is_readable_under_the_default_policy() -> None:
    """Rule 11's positive control: change nothing but the policy -- the exact
    same freshly planted path, read by the exact same probe -- and it reads back
    under `WHOLE_HOST_READ_ONLY`, the default every jail gets when it names no
    policy of its own. Proof the probe above can see a reachable path and would
    have reported it, so the battery above's `ENOENT` is evidence this policy's
    own allow-list withheld `/tmp`, not an artifact of a probe that could never
    have detected a reachable one in the first place.
    """
    with _fresh_tmp_dir() as secret_dir:
        secret_path = Path(secret_dir) / "secret.txt"
        secret_path.write_text(_PLANTED_CONTENT)

        jail = create_bwrap_jail(
            (sys.executable, "-c", _READ_PROBE, str(secret_path), sys.executable, _PLANTED_CONTENT),
            policy=WHOLE_HOST_READ_ONLY,
        )
        exit_code = run_jail(jail)
        destroy_jail(jail)

    assert exit_code == 0  # reachable: the default policy binds the whole host root


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_a_read_only_bind_refuses_a_write_from_inside_the_jail() -> None:
    """AC#3's other half: a path bound without `writable=True` (every bind
    `WHOLE_HOST_READ_ONLY` names, by definition) cannot be written to from
    inside a real bwrap jail -- `EROFS`, this battery's write probe's own exit
    code `2`.
    """
    with _fresh_tmp_dir() as target_dir:
        target_path = Path(target_dir) / "out.txt"

        jail = create_bwrap_jail(
            (sys.executable, "-c", _WRITE_PROBE, str(target_path), _PLANTED_CONTENT),
            policy=WHOLE_HOST_READ_ONLY,
        )
        exit_code = run_jail(jail)
        destroy_jail(jail)

        assert exit_code == 2  # EROFS: this path's bind is read-only
        assert not target_path.exists()


@pytest.mark.skipif(
    shutil.which("bwrap") is None,
    reason="bwrap is not available; test skips on macOS, runs in CI on Linux",
)
def test_positive_control_a_writable_bind_lets_the_jail_write_back_to_the_host() -> None:
    """Rule 11's positive control for the write half: change nothing but
    `writable` on the one `Bind` covering this exact path -- added on top of
    `WHOLE_HOST_READ_ONLY`'s own read-only binds, the realistic shape of "mostly
    read-only, a few paths writable" -- and the identical probe, writing the
    identical content to the identical path, now succeeds and leaves that
    content readable back on the host. Proof the probe above can see a
    successful write and would have reported it, so the battery above's `EROFS`
    is evidence of this path's bind being read-only, not an artifact of a probe
    that could never have detected a successful write in the first place.
    """
    with _fresh_tmp_dir() as target_dir:
        target_path = Path(target_dir) / "out.txt"
        policy = FsPolicy(
            binds=(
                *WHOLE_HOST_READ_ONLY.binds,
                Bind(host_path=target_dir, jail_path=target_dir, writable=True),
            )
        )

        jail = create_bwrap_jail(
            (sys.executable, "-c", _WRITE_PROBE, str(target_path), _PLANTED_CONTENT),
            policy=policy,
        )
        exit_code = run_jail(jail)
        destroy_jail(jail)

        assert exit_code == 0
        assert target_path.read_text() == _PLANTED_CONTENT
