"""Assembles the egress proxy's one file (decision-0009 item 2): the version guard the supervisor's
file has (`supervisor.assemble.guard`), then the egress decision's source and the log envelope's
(`infra/log.py`), each run as a module of its own, then `program.py`'s, run as the file's main
code with both handed to it.

The decision is `domain/policy/egress.py`, which this layer cannot import (decision-0001 rule 1):
it arrives as source text, read by the presentation layer, so the proxy decides with exactly the
module the domain's tests hold. Both sources are base64-encoded and `exec`'d once the guard
passes, as the supervisor's are; the decision's and the envelope's into modules registered in
`sys.modules` under `program.DECISION_MODULE` and `program.LOG_MODULE` first, since a dataclass
looks its own module up there.
"""

import base64
from pathlib import Path

from brig.infra import log
from brig.infra.proxy import program
from brig.infra.supervisor import assemble


def _blob(source: str) -> str:
    return repr(base64.b64encode(source.encode("utf-8")))


def _module(name: str, source: str, label: str) -> str:
    """The lines that run `source` as a fresh module `name`, registered in `sys.modules`."""
    return (
        f"_module = types.ModuleType({name!r})\n"
        + f"sys.modules[{name!r}] = _module\n"
        + f'exec(compile(base64.b64decode({_blob(source)}).decode("utf-8"), '
        + f'"<{label}>", "exec"), _module.__dict__)\n'
        + "del _module\n"
    )


def assembled_source(decision_source: str) -> str:
    """The assembled proxy file, from `decision_source` (`egress.py`'s text), and `log.py` and
    `program.py` as they are now. An `OSError` reading either propagates."""
    program_source = Path(program.__file__).read_text(encoding="utf-8")
    log_source = Path(log.__file__).read_text(encoding="utf-8")
    return (
        assemble.guard("egress proxy")
        + "import base64\n"
        + "import types\n"
        + _module(program.DECISION_MODULE, decision_source, "brig-egress-decision")
        + _module(program.LOG_MODULE, log_source, "brig-log")
        + f'exec(compile(base64.b64decode({_blob(program_source)}).decode("utf-8"), '
        + '"<brig-egress-proxy>", "exec"))\n'
    )
