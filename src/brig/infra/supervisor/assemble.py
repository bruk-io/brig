"""Assembles `wire.py` and `program.py` into the one stdlib-only supervisor file (decision-0001
rule 17), which refuses an interpreter older than 3.15 by name.

The file is a guard in syntax Python 2.7 can parse, then the two sources base64-encoded and
`exec`'d once the guard passes: Python parses a whole module before running any of it, so plain
concatenated source would fail with a bare `SyntaxError` on an old interpreter first.
"""

import base64
from pathlib import Path

from brig.infra.supervisor import program, wire

_REQUIRED_VERSION = (3, 15)
"""The oldest interpreter the supervisor runs under: brig's own floor."""

_MESSAGE_PREFIX = "brig's supervisor requires Python 3.15 or later; this interpreter is "
"""The refusal's text, shared by `refusal_message` and the guard `_preamble` writes."""


def refusal_message(installed: tuple[int, ...]) -> str:
    """The message an interpreter older than `_REQUIRED_VERSION` prints, naming `installed`."""
    return _MESSAGE_PREFIX + ".".join(str(part) for part in installed)


def _preamble() -> str:
    """The guard at the top of the assembled file, in syntax Python 2.7 can parse: below
    `_REQUIRED_VERSION` it writes the refusal to stderr and exits 1."""
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
    """The assembled supervisor file, from `wire.py` and `program.py` as they are now."""
    wire_source = Path(wire.__file__).read_text(encoding="utf-8")
    program_source = Path(program.__file__).read_text(encoding="utf-8")
    body = base64.b64encode((wire_source + program_source).encode("utf-8"))
    return (
        _preamble()
        + "import base64\n"
        + f'exec(compile(base64.b64decode({body!r}).decode("utf-8"), '
        + '"<brig-supervisor>", "exec"))\n'
    )
