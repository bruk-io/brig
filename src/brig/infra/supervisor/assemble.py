"""Assembles `wire.py` and `program.py` into the one stdlib-only file
decision-0001 rule 17 requires: whatever `presentation/api.py` drops as PID 1
inside the jail's own namespace (decision-0002) must be exactly those two
files' own source, nothing else, and must refuse to run under an interpreter
older than this project's own floor (3.15) -- naming it, rather than failing
with a bare `SyntaxError` partway through parsing `wire.py`'s own
`type Event = ...` statement (3.12+ syntax) before any guard code the
assembled file might contain has had a chance to run at all.

`assembled_source` renders the result: a small preamble, written in syntax a
Python 2.7 interpreter can still parse (a plain `sys.version_info` comparison,
`sys.stderr.write`, `sys.exit`, string concatenation with `+` -- no f-strings,
no walrus, no `match`), followed by `wire.py`'s own source plus `program.py`'s
own source, concatenated, base64-encoded as one blob, and
`exec(compile(...))`'d -- but only once the preamble's own guard has already
passed. This ordering is the whole point: Python parses an entire module
before executing any statement in it, so a plain top-level concatenation of
the two files' real source would `SyntaxError` under an old interpreter
before any version check in it ever ran; deferring the decode and the exec
until after the guard is what actually makes "refuses an older interpreter,
saying which it needs" (rule 17) true. Base64 avoids a second hazard: both
files carry their own triple-quoted docstrings, which embedding their text
directly as a string literal would have to escape around; a base64 blob has
no quoting of its own to escape.

This module itself is not part of what gets assembled -- it runs on the host,
building the artifact `presentation/api.py` drops into the jail, never inside
one -- but stays stdlib-only regardless: reading `wire.__file__`/
`program.__file__` plus `base64`/`pathlib` is the whole of what it touches.
"""

import base64
from pathlib import Path

from brig.infra.supervisor import program, wire

_REQUIRED_VERSION = (3, 15)
"""decision-0001 rule 17's own floor: the interpreter brig itself runs on, and
the one the assembled file refuses to run under anything older than.
"""

_MESSAGE_PREFIX = "brig's supervisor requires Python 3.15 or later; this interpreter is "
"""The one piece of text `refusal_message` and `_preamble`'s own generated
guard both build from, so the message a genuinely old interpreter prints and
the one `refusal_message` returns for a synthetic version tuple in a test can
never read differently for the same version -- `_preamble` embeds this by
`repr`, never retyped as a second copy.
"""


def refusal_message(installed: tuple[int, ...]) -> str:
    """The message an interpreter older than `_REQUIRED_VERSION` sees on
    stderr before the assembled file exits, naming what it actually got
    (`installed`) against what rule 17 requires.

    Pure, and testable directly with a synthetic `installed` -- no real old
    interpreter required to confirm `(3, 9, 0)` mentions "3.15". A caller
    never calls this for an `installed` that already clears
    `_REQUIRED_VERSION`: the assembled file's own guard would not have fired.
    """
    return _MESSAGE_PREFIX + ".".join(str(part) for part in installed)


def _preamble() -> str:
    """Render the guard that runs before anything else in the assembled file:
    refuses to proceed under an interpreter older than `_REQUIRED_VERSION`,
    written in syntax a Python 2.7 interpreter can still parse. This text is
    parsed -- not only executed -- by whatever interpreter loads the
    assembled file, including one old enough that the base64 body beneath it
    would never otherwise get the chance to explain why it refused, which is
    why it stays this plain: a bare `sys.version_info` comparison,
    `sys.stderr.write`, `sys.exit`, string concatenation with `+`.

    Embeds `_MESSAGE_PREFIX` by `repr`, not retyped, so this function's own
    output and `refusal_message`'s cannot read differently for the same
    installed version.
    """
    return (
        "import sys\n"
        f"if sys.version_info < {_REQUIRED_VERSION!r}:\n"
        "    sys.stderr.write(\n"
        f"        {_MESSAGE_PREFIX!r}\n"
        '        + ".".join(str(part) for part in sys.version_info[:3])\n'
        '        + "\\n"\n'
        "    )\n"
        "    sys.exit(1)\n"
    )


def assembled_source() -> str:
    """Render the one file decision-0001 rule 17 requires: `_preamble`'s
    version guard, followed by `wire.py`'s own source plus `program.py`'s own
    source -- concatenated, base64-encoded as one blob, and
    `exec(compile(...))`'d only once the guard above has already passed.

    Reads both modules' source fresh from `wire.__file__`/`program.__file__`
    every call, rather than caching a second, checked-in copy: the moment
    either file changes without this function re-running, the artifact this
    builds stops matching them -- exactly what the e2e test covering this
    function's own byte-exact claim exists to catch.
    """
    wire_source = Path(wire.__file__).read_text(encoding="utf-8")
    program_source = Path(program.__file__).read_text(encoding="utf-8")
    body = base64.b64encode((wire_source + program_source).encode("utf-8"))
    return (
        _preamble()
        + "import base64\n"
        + f'exec(compile(base64.b64decode({body!r}).decode("utf-8"), '
        + '"<brig-supervisor>", "exec"))\n'
    )
