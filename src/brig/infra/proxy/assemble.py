"""Assembles the egress proxy's one file (decision-0009 item 2): the version guard the supervisor's
file has (`supervisor.assemble.guard`), then the egress decision's source, run as a module of its
own, then `program.py`'s, run as the file's main code with the decision handed to it.

The decision is `domain/policy/egress.py`, which this layer cannot import (decision-0001 rule 1):
it arrives as source text, read by the presentation layer, so the proxy decides with exactly the
module the domain's tests hold. Both sources are base64-encoded and `exec`'d once the guard
passes, as the supervisor's are; the decision's into a module registered in `sys.modules` under
`program.DECISION_MODULE` first, since a dataclass looks its own module up there.
"""

import base64
from pathlib import Path

from brig.infra.proxy import program
from brig.infra.supervisor import assemble


def _blob(source: str) -> str:
    return repr(base64.b64encode(source.encode("utf-8")))


def assembled_source(decision_source: str) -> str:
    """The assembled proxy file, from `decision_source` (`egress.py`'s text) and `program.py`
    as it is now. An `OSError` reading `program.py` propagates."""
    program_source = Path(program.__file__).read_text(encoding="utf-8")
    module = program.DECISION_MODULE
    return (
        assemble.guard("egress proxy")
        + "import base64\n"
        + "import types\n"
        + f"_decision = types.ModuleType({module!r})\n"
        + f"sys.modules[{module!r}] = _decision\n"
        + f'exec(compile(base64.b64decode({_blob(decision_source)}).decode("utf-8"), '
        + '"<brig-egress-decision>", "exec"), _decision.__dict__)\n'
        + "del _decision\n"
        + f'exec(compile(base64.b64decode({_blob(program_source)}).decode("utf-8"), '
        + '"<brig-egress-proxy>", "exec"))\n'
    )
