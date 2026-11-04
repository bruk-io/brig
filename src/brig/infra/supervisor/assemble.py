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


def _message_prefix(program: str) -> str:
    """The refusal's text before the version, shared by `refusal_message` and `guard`."""
    return f"brig's {program} requires Python 3.15 or later; this interpreter is "


def refusal_message(installed: tuple[int, ...], program: str = "supervisor") -> str:
    """The message `program`'s file prints under an interpreter older than
    `_REQUIRED_VERSION`, naming `installed`."""
    return _message_prefix(program) + ".".join(str(part) for part in installed)


def guard(program: str) -> str:
    """The guard at the top of an assembled file of brig's (`program`: the supervisor, the egress
    proxy), in syntax Python 2.7 can parse: below `_REQUIRED_VERSION` it writes the refusal to
    stderr and exits 1."""
    return (
        "import sys\n"
        f"if sys.version_info < {_REQUIRED_VERSION!r}:\n"
        "    sys.stderr.write(\n"
        f"        {_message_prefix(program)!r}\n"
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
        guard("supervisor")
        + "import base64\n"
        + f'exec(compile(base64.b64decode({body!r}).decode("utf-8"), '
        + '"<brig-supervisor>", "exec"))\n'
    )
