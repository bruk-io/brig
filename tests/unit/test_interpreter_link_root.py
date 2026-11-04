"""TASK-0052 AC#5: a policy whose readable root is the venv's interpreter link itself reaches the
interpreter. bwrap binds what a root leads to at the root's own path, so inside the jail that
path is the interpreter, not a link, and the links after it on the host are never followed there.
"""

from brig.domain.policy.paths import FsPolicy, InterpreterUnreachable, interpreter_refusal

_CHAIN = (
    "/r/.venv/bin/python3",
    "/r/.venv/bin/python",
    "/u/cpython-3.15/bin/python3.15",
    "/u/cpython-3.15.0b4/bin/python3.15",
)
"""A uv venv's `python3 -> python -> <uv>/cpython-3.15/bin/python3.15`, where `cpython-3.15` is
itself a link to the full version's install."""


def test_a_root_that_is_the_interpreter_link_itself_is_not_refused() -> None:
    """The root is the first path of the chain: the jail sees the interpreter there."""
    assert interpreter_refusal(FsPolicy(readable=("/usr", "/r/.venv/bin/python3")), _CHAIN) is None


def test_a_root_that_is_a_later_path_on_the_way_is_not_refused_once_the_earlier_ones_are() -> None:
    """Both venv links are inside `.venv`, and the path the second leads to, through the
    version's link, is a root of its own: bwrap binds the interpreter there."""
    policy = FsPolicy(readable=("/r/.venv", "/u/cpython-3.15/bin/python3.15"))

    assert interpreter_refusal(policy, _CHAIN) is None


def test_a_root_on_a_later_link_does_not_excuse_an_earlier_one() -> None:
    """`python` alone is a root, but the lookup starts at `python3`, which no root mounts."""
    assert interpreter_refusal(FsPolicy(readable=("/r/.venv/bin/python",)), _CHAIN) == (
        InterpreterUnreachable("/r/.venv/bin/python3")
    )


def test_a_mask_over_the_root_still_refuses() -> None:
    """A mask over the interpreter link hides what bwrap mounted there."""
    policy = FsPolicy(readable=("/r/.venv/bin/python3",), masks=("/r/.venv/bin",))

    assert interpreter_refusal(policy, _CHAIN) == InterpreterUnreachable("/r/.venv/bin/python3")
