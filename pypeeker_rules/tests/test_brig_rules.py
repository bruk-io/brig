"""One planted-violation test per custom rule in ``pypeeker_rules/brig.py``.

Each test writes a synthetic fixture tree into ``tmp_path``, configures that
fixture's ``pyproject.toml`` to run exactly one brig rule, and runs
``pypeeker index`` + ``pypeeker check --strict`` as a subprocess (see
``conftest.py``) -- demanding the rule's own id in the output, by name, never
by message text (message wording is explicitly not a contract).

These are meta-tests of the lint config, not of brig, so they live beside the
plugin rather than under the repository's own ``tests/`` -- which
``brig-test-layers`` polices for brig's domain/integration/e2e suites, a
different concern entirely.
"""

from __future__ import annotations

from pathlib import Path

from pypeeker_rules.tests.conftest import assert_rule_clean, assert_rule_fires, build_fixture


def test_brig_layers_fires_on_a_cross_layer_import(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-layers",
        src=("src",),
        files={
            "src/brig/domain/bad.py": "from brig.infra import helper\n",
            "src/brig/infra/helper.py": "X = 1\n",
        },
        rule_config=(
            "[tool.pypeeker.brig-layers]\n"
            'root = "src/brig"\n'
            "[tool.pypeeker.brig-layers.allow]\n"
            "domain = []\n"
            "infra = []\n"
        ),
    )
    assert_rule_fires(project, "brig-layers", src=("src",))


def test_brig_pure_domain_fires_on_an_io_import(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-pure-domain",
        src=("src",),
        files={"src/brig/domain/bad.py": "import subprocess\n"},
    )
    assert_rule_fires(project, "brig-pure-domain", src=("src",))


def test_brig_slices_fires_on_a_cross_type_import(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-slices",
        src=("src",),
        files={
            "src/brig/domain/jail_types/bwrap.py": (
                "from brig.domain.jail_types.seatbelt import X\n"
            ),
            "src/brig/domain/jail_types/seatbelt.py": "X = 1\n",
        },
    )
    assert_rule_fires(project, "brig-slices", src=("src",))


def test_brig_test_layers_fires_on_a_unit_test_importing_infra(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-test-layers",
        src=("tests",),
        files={"tests/unit/test_bad.py": "from brig.infra import helper\n"},
    )
    assert_rule_fires(project, "brig-test-layers", src=("tests",))


def test_brig_no_patching_fires_on_a_monkeypatch_parameter(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-no-patching",
        src=("tests",),
        files={"tests/unit/test_bad.py": "def test_x(monkeypatch):\n    pass\n"},
    )
    assert_rule_fires(project, "brig-no-patching", src=("tests",))


def test_brig_class_forms_fires_on_an_unfrozen_dataclass(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/shapes.py": (
                "import dataclasses\n\n\n@dataclasses.dataclass\nclass Bad:\n    x: int\n"
            )
        },
    )
    assert_rule_fires(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_fires_on_disallowed_inheritance(tmp_path: Path) -> None:
    """A class inheriting from a plain local class -- not Exception, Enum/StrEnum
    or Protocol -- violates decision-0001 rule 7's inheritance restriction.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/shapes.py": ("class Base:\n    pass\n\n\nclass Bad(Base):\n    pass\n")
        },
    )
    assert_rule_fires(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_fires_on_disallowed_inheritance_via_import(tmp_path: Path) -> None:
    """The cross-file counterpart of the test above: a genuine disallowed base
    reached through an import (``from brig.domain.base import Mixin``), not a
    same-file class. ``_classify_header_bases`` reports this ``ambiguous``
    (TASK-0001.19) rather than ``disallowed``, so this is pinned by the
    project-reach rule part (``_reexported_base_disallowed``), not by
    ``_disallowed_inheritance`` -- the shape AC#2 names.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/base.py": "class Mixin:\n    pass\n",
            "src/brig/domain/q.py": (
                "from brig.domain.base import Mixin\n\n\nclass Thing(Mixin):\n    pass\n"
            ),
        },
    )
    assert_rule_fires(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_a_protocol_re_exported_through_a_project_module(
    tmp_path: Path,
) -> None:
    """TASK-0001.19's own planted violation: a project module re-exports an
    exempt stdlib base (``brig.domain.shim`` does ``from typing import
    Protocol``), and a class inherits from it through that re-export. Within
    one file this is the same fact as the genuine-disallowed-base test above
    (a same-file import of unresolved origin); the project-reach rule part
    tells them apart by resolving the import across files.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/shim.py": "from typing import Protocol\n",
            "src/brig/domain/p.py": (
                "from brig.domain.shim import Protocol\n\n\n"
                "class Port(Protocol):\n    def do(self) -> None: ...\n"
            ),
        },
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_a_protocol_re_export_with_state(tmp_path: Path) -> None:
    """The re-exported-Protocol fixture above, with the class also assigning
    ``self.x = 1`` -- the stateful-class check (rule 7's fifth shape) must
    not manufacture a finding out of this base either, the same "cannot
    tell, from this file alone" treatment TASK-0001.18 already pins for an
    attribute-chain base: ``_classify_header_bases`` reports this base
    ``ambiguous``, not ``exempt``, so ``_stateful_outside_infra`` must read
    that as "cannot tell", not "confirmed not exempt".
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/shim.py": "from typing import Protocol\n",
            "src/brig/domain/p.py": (
                "from brig.domain.shim import Protocol\n\n\n"
                "class Port(Protocol):\n"
                "    def __init__(self) -> None:\n"
                "        self.x = 1\n"
            ),
        },
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_a_protocol_subclass(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/ports.py": (
                "from typing import Protocol\n\n\n"
                "class Port(Protocol):\n    def do(self) -> None: ...\n"
            )
        },
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_an_exception_subclass(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={"src/brig/domain/errors.py": "class BadInput(Exception):\n    pass\n"},
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_an_enum_subclass(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/kinds.py": (
                "from enum import Enum\n\n\nclass Kind(Enum):\n    A = 1\n"
            )
        },
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_a_protocol_subclass_via_attribute_chain(tmp_path: Path) -> None:
    """A base reached through an attribute chain (``t.Protocol``) does not resolve
    to the same-file ``IMPORT`` shape ``_declares_disallowed_base`` reads -- it must
    not be flagged as a guessed violation (a regression would fail the gate on
    conforming code under --strict).
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/ports.py": (
                "import typing as t\n\n\nclass Port(t.Protocol):\n    def do(self) -> None: ...\n"
            )
        },
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_a_protocol_subclass_via_attribute_chain_with_state(
    tmp_path: Path,
) -> None:
    """The same attribute-chain base as the test above, but with the class body
    also assigning ``self.<name> = ...`` -- the shape TASK-0001.18's review
    found firing the stateful-class check (rule 7's fifth shape) solely
    because the attribute-chain base could not be resolved to the exempt
    shape it actually is. An unresolved base must stay "cannot tell", never
    "confirmed not exempt": this must come back clean, not as a stateful-class
    finding.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/ports.py": (
                "import typing as t\n\n\n"
                "class Port(t.Protocol):\n    def __init__(self) -> None:\n        self.x = 1\n"
            )
        },
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_an_enum_subclass_via_attribute_chain_with_state(
    tmp_path: Path,
) -> None:
    """The ``enum`` counterpart of the ``typing`` case above -- the exact shape
    TASK-0001.18's review verified empirically against the real rule:
    ``import enum`` / ``class Signal(enum.Enum)`` with the stdlib-blessed
    ``def __init__(self, number, label): self.number = number`` pattern.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/signal.py": (
                "import enum\n\n\n"
                "class Signal(enum.Enum):\n"
                "    RED = (1, 'red')\n\n"
                "    def __init__(self, number: int, label: str) -> None:\n"
                "        self.number = number\n"
                "        self.label = label\n"
            )
        },
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_fires_on_a_stateful_class_outside_infra(tmp_path: Path) -> None:
    """A bare class with instance state, outside infra/, violates decision-0001
    rule 7's fifth shape -- a stateful class confined to infra/.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/cache.py": (
                "class Cache:\n    def __init__(self) -> None:\n        self.items = {}\n"
            )
        },
    )
    assert_rule_fires(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_a_stateful_class_in_infra(tmp_path: Path) -> None:
    """The same bare, stateful class is exactly rule 7's allowed fifth shape
    when it lives in infra/.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/infra/cache.py": (
                "class Cache:\n    def __init__(self) -> None:\n        self.items = {}\n"
            )
        },
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_an_exception_subclass_with_instance_state(
    tmp_path: Path,
) -> None:
    """An Exception subclass's own 'self.<name> = ...' in __init__ is rule 7's
    typed failure shape, not the stateful-class shape confined to infra/ --
    the real pattern in brig's own presentation/errors.py, and the false
    positive the stateful check must not reproduce.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={
            "src/brig/domain/errors.py": (
                "class BadInput(Exception):\n"
                "    def __init__(self, value: int) -> None:\n"
                "        super().__init__(str(value))\n"
                "        self.value = value\n"
            )
        },
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_class_forms_accepts_a_class_level_field_outside_infra(tmp_path: Path) -> None:
    """A plain class-level field (`class Registry: DEFAULT = 1`) is a VARIABLE
    member of the class scope too, the same as a `self.x = ...` instance
    attribute -- but assigned directly in the class body, not from inside a
    method, so it is not the 'instance state' the stateful-class check means
    and must not fire on it.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-class-forms",
        src=("src",),
        files={"src/brig/domain/registry.py": "class Registry:\n    DEFAULT = 1\n"},
    )
    assert_rule_clean(project, "brig-class-forms", src=("src",))


def test_brig_vocabulary_fires_on_a_banned_name(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-vocabulary",
        src=("src",),
        files={"src/brig/domain/agent_thing.py": "AGENT_NAME = 1\n"},
    )
    assert_rule_fires(project, "brig-vocabulary", src=("src",))


def test_brig_one_writer_fires_on_a_print_call(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-one-writer",
        src=("src",),
        files={"src/brig/presentation/writer.py": "def report() -> None:\n    print('hi')\n"},
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_one_writer_fires_on_a_from_import_stream_write(tmp_path: Path) -> None:
    """``from sys import stdout; stdout.write(...)`` -- a different receiver-chain
    shape than ``sys.stdout.write(...)``, caught through the import's recorded
    ``imported_from`` rather than the local name it was bound to.
    """
    project = build_fixture(
        tmp_path,
        rule_id="brig-one-writer",
        src=("src",),
        files={
            "src/brig/presentation/writer.py": (
                "from sys import stdout\n\n\ndef report() -> None:\n    stdout.write('hi')\n"
            )
        },
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_one_writer_fires_on_an_aliased_from_import_stream_write(tmp_path: Path) -> None:
    """The same gap, with the imported name itself aliased on the way in."""
    project = build_fixture(
        tmp_path,
        rule_id="brig-one-writer",
        src=("src",),
        files={
            "src/brig/presentation/writer.py": (
                "from sys import stdout as out\n\n\ndef report() -> None:\n    out.write('hi')\n"
            )
        },
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_pure_domain_heuristic_fires_on_an_impure_function(tmp_path: Path) -> None:
    """The no-impure-functions heuristic half of decision-0001 rule 2, configured
    with include=["brig.domain*"], fires on a domain function that calls time.sleep.
    """
    project = build_fixture(
        tmp_path,
        rule_id="no-impure-functions",
        src=("src",),
        files={
            "src/brig/domain/impure.py": (
                "import time\n\n\ndef do_work() -> None:\n    time.sleep(0.1)\n"
            )
        },
        rule_config='[tool.pypeeker.no-impure-functions]\ninclude = ["brig.domain*"]\n',
    )
    assert_rule_fires(project, "no-impure-functions", src=("src",))


# ---------------------------------------------------------------------------
# TASK-0033: the shapes an architecture review planted that the gate let through
# ---------------------------------------------------------------------------


def _no_patching_fixture(
    tmp_path: Path, source: str, *, at: str = "tests/unit/test_bad.py"
) -> Path:
    return build_fixture(tmp_path, rule_id="brig-no-patching", src=("tests",), files={at: source})


def test_brig_no_patching_fires_on_monkeypatch_context(tmp_path: Path) -> None:
    """``pytest.MonkeyPatch.context()`` patches without a ``monkeypatch`` parameter."""
    project = _no_patching_fixture(
        tmp_path,
        "import pytest\nimport brig\n\n\ndef test_x() -> None:\n"
        "    with pytest.MonkeyPatch.context() as patch:\n"
        "        patch.setattr(brig, 'x', 1)\n",
    )
    assert_rule_fires(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_fires_on_monkeypatch_through_an_aliased_pytest(tmp_path: Path) -> None:
    project = _no_patching_fixture(
        tmp_path, "import pytest as pt\n\n\ndef test_x() -> None:\n    pt.MonkeyPatch()\n"
    )
    assert_rule_fires(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_fires_on_importing_monkeypatch_by_name(tmp_path: Path) -> None:
    project = _no_patching_fixture(
        tmp_path, "from pytest import MonkeyPatch\n\n\ndef test_x() -> None:\n    MonkeyPatch()\n"
    )
    assert_rule_fires(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_accepts_other_pytest_attributes(tmp_path: Path) -> None:
    """The clean case: ``pytest.raises`` and ``pytest.mark`` are not patchers."""
    project = _no_patching_fixture(
        tmp_path,
        "import pytest\n\n\n@pytest.mark.parametrize('n', [1])\ndef test_x(n: int) -> None:\n"
        "    with pytest.raises(ValueError):\n        int('x')\n",
    )
    assert_rule_clean(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_fires_on_setattr_of_an_imported_module(tmp_path: Path) -> None:
    project = _no_patching_fixture(
        tmp_path,
        "import brig\n\n\ndef test_x() -> None:\n    setattr(brig, 'create_bwrap_jail', None)\n",
    )
    assert_rule_fires(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_fires_on_a_multi_line_delattr_of_an_import(tmp_path: Path) -> None:
    project = _no_patching_fixture(
        tmp_path,
        "from brig import infra\n\n\ndef test_x() -> None:\n"
        "    delattr(\n        infra.files,\n        'read_beneath',\n    )\n",
    )
    assert_rule_fires(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_fires_on_an_attribute_assigned_through_an_import(
    tmp_path: Path,
) -> None:
    """``brig.x = f`` is ``setattr(brig, 'x', f)`` with no call."""
    project = _no_patching_fixture(
        tmp_path, "import brig\n\n\ndef test_x() -> None:\n    brig.create_bwrap_jail = None\n"
    )
    assert_rule_fires(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_accepts_setattr_on_a_local_object(tmp_path: Path) -> None:
    """The clean case: setattr and attribute assignment on an object the test made
    itself -- here proving a frozen dataclass refuses it -- patch nothing, even with
    an import handed in as a later argument."""
    project = _no_patching_fixture(
        tmp_path,
        "import dataclasses\nimport brig\nimport pytest\n\n\n"
        "@dataclasses.dataclass(frozen=True)\nclass Point:\n    x: int\n\n\n"
        "def test_x() -> None:\n"
        "    point = Point(1)\n"
        "    with pytest.raises(dataclasses.FrozenInstanceError):\n"
        "        setattr(point, 'x', brig)\n"
        "    holder = type('Holder', (), {})()\n"
        "    holder.value = brig\n",
    )
    assert_rule_clean(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_fires_on_a_fake_dataclass_in_e2e(tmp_path: Path) -> None:
    project = _no_patching_fixture(
        tmp_path,
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True)\nclass FakeClock:\n    now: float\n",
        at="tests/e2e/test_bad.py",
    )
    assert_rule_fires(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_fires_on_a_private_stub_in_unit(tmp_path: Path) -> None:
    project = _no_patching_fixture(
        tmp_path, "class _stub_processes:\n    pass\n", at="tests/unit/test_bad.py"
    )
    assert_rule_fires(project, "brig-no-patching", src=("tests",))


def test_brig_no_patching_accepts_a_fake_in_integration_and_a_real_helper_in_e2e(
    tmp_path: Path,
) -> None:
    """The clean case: a fake where rule 5 puts doubles, and an e2e helper whose
    name says what it is (a word merely containing 'fake'/'mock' is not one)."""
    project = build_fixture(
        tmp_path,
        rule_id="brig-no-patching",
        src=("tests",),
        files={
            "tests/integration/fakes.py": (
                "from dataclasses import dataclass\n\n\n"
                "@dataclass\nclass FakeProcesses:\n    spawned: list[str]\n"
            ),
            "tests/e2e/test_ok.py": (
                "from dataclasses import dataclass\n\n\n"
                "@dataclass(frozen=True)\nclass _DirectoryIn:\n    root: str\n\n\n"
                "class _Mockingbird:\n    pass\n"
            ),
        },
    )
    assert_rule_clean(project, "brig-no-patching", src=("tests",))


_ONE_WRITER_ALLOW = '[tool.pypeeker.brig-one-writer]\nallow = ["brig.infra.supervisor.program"]\n'


def _one_writer_fixture(tmp_path: Path, files: dict[str, str]) -> Path:
    return build_fixture(
        tmp_path,
        rule_id="brig-one-writer",
        src=("src",),
        files=files,
        rule_config=_ONE_WRITER_ALLOW,
    )


def test_brig_one_writer_fires_on_os_write_to_stdout_in_infra(tmp_path: Path) -> None:
    project = _one_writer_fixture(
        tmp_path,
        {"src/brig/infra/noisy.py": "import os\n\n\ndef say() -> None:\n    os.write(1, b'hi')\n"},
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_one_writer_fires_on_os_write_to_stderr_through_an_alias(tmp_path: Path) -> None:
    project = _one_writer_fixture(
        tmp_path,
        {
            "src/brig/presentation/noisy.py": (
                "import os as o\n\n\ndef say() -> None:\n    o.write(2, b'hi')\n"
            )
        },
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_one_writer_fires_on_os_write_imported_by_name(tmp_path: Path) -> None:
    project = _one_writer_fixture(
        tmp_path,
        {
            "src/brig/presentation/noisy.py": (
                "from os import write\n\n\ndef say() -> None:\n    write(2, b'hi')\n"
            )
        },
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_one_writer_fires_on_a_stdout_buffer_write(tmp_path: Path) -> None:
    project = _one_writer_fixture(
        tmp_path,
        {
            "src/brig/infra/noisy.py": (
                "import sys\n\n\ndef say() -> None:\n    sys.stdout.buffer.write(b'hi')\n"
            )
        },
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_one_writer_fires_on_logging_in_infra(tmp_path: Path) -> None:
    project = _one_writer_fixture(
        tmp_path,
        {
            "src/brig/infra/noisy.py": (
                "import logging\n\n\ndef say() -> None:\n    logging.getLogger('b').info('hi')\n"
            )
        },
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_one_writer_fires_on_logging_in_presentation_by_name(tmp_path: Path) -> None:
    project = _one_writer_fixture(
        tmp_path, {"src/brig/presentation/noisy.py": "from logging import getLogger\n"}
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_one_writer_fires_on_logging_even_in_the_supervisors_wire(tmp_path: Path) -> None:
    """The allow list names who may write, not who may log: the wire writes its own JSON."""
    project = _one_writer_fixture(
        tmp_path, {"src/brig/infra/supervisor/program.py": "import logging\n"}
    )
    assert_rule_fires(project, "brig-one-writer", src=("src",))


def test_brig_one_writer_accepts_the_wires_os_write_and_other_os_calls(tmp_path: Path) -> None:
    """The clean case: the supervisor's wire is the one raw writer, and the rest of
    brig may use ``os`` for anything but writing a descriptor."""
    project = _one_writer_fixture(
        tmp_path,
        {
            "src/brig/infra/supervisor/program.py": (
                "import os\n\n\ndef emit(fd: int) -> None:\n    os.write(fd, b'{}\\n')\n"
            ),
            "src/brig/infra/processes.py": (
                "import os\n\n\ndef close(fd: int) -> None:\n    os.close(fd)\n    os.read(fd, 1)\n"
            ),
            "src/brig/infra/link.py": ("def send(pipe) -> None:\n    pipe.write(b'x')\n"),
        },
    )
    assert_rule_clean(project, "brig-one-writer", src=("src",))


def _frozen_data_fixture(
    tmp_path: Path, source: str, *, at: str = "src/brig/domain/spec.py"
) -> Path:
    return build_fixture(
        tmp_path,
        rule_id="brig-frozen-data",
        src=("src",),
        files={at: source},
        rule_config='[tool.pypeeker.brig-frozen-data]\nroot = "src/brig/domain"\n',
    )


def test_brig_frozen_data_fires_on_a_list_field(tmp_path: Path) -> None:
    project = _frozen_data_fixture(
        tmp_path,
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True)\nclass Spec:\n    argv: list[str]\n",
    )
    assert_rule_fires(project, "brig-frozen-data", src=("src",))


def test_brig_frozen_data_fires_on_a_dict_field(tmp_path: Path) -> None:
    project = _frozen_data_fixture(
        tmp_path,
        "import dataclasses\n\n\n"
        "@dataclasses.dataclass(frozen=True)\nclass Spec:\n    env: dict[str, str]\n",
    )
    assert_rule_fires(project, "brig-frozen-data", src=("src",))


def test_brig_frozen_data_fires_on_a_list_nested_in_a_tuple(tmp_path: Path) -> None:
    project = _frozen_data_fixture(
        tmp_path,
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True)\nclass Spec:\n    steps: tuple[list[str], ...] = ()\n",
    )
    assert_rule_fires(project, "brig-frozen-data", src=("src",))


def test_brig_frozen_data_accepts_tuples_frozendicts_and_non_fields(tmp_path: Path) -> None:
    """The clean case: immutable fields, a ClassVar, a list inside a method body,
    a TypedDict (a JSON shape, not a dataclass), and a list field outside domain/."""
    project = build_fixture(
        tmp_path,
        rule_id="brig-frozen-data",
        src=("src",),
        files={
            "src/brig/domain/spec.py": (
                "from dataclasses import dataclass\n"
                "from typing import ClassVar, TypedDict\n\n\n"
                "@dataclass(frozen=True)\nclass Spec:\n"
                "    argv: tuple[str, ...]\n"
                "    env: frozendict[str, str]\n"
                "    names: frozenset[str] = frozenset()\n"
                "    KINDS: ClassVar[list[str]] = []\n\n"
                "    def joined(self) -> str:\n"
                "        parts: list[str] = list(self.argv)\n"
                "        return ' '.join(parts)\n\n\n"
                "class Message(TypedDict):\n    argv: list[str]\n"
            ),
            "src/brig/infra/buffer.py": (
                "from dataclasses import dataclass\n\n\n"
                "@dataclass(frozen=True)\nclass Lines:\n    lines: list[str]\n"
            ),
        },
        rule_config='[tool.pypeeker.brig-frozen-data]\nroot = "src/brig/domain"\n',
    )
    assert_rule_clean(project, "brig-frozen-data", src=("src",))


_STANDALONE_CONFIG = (
    "[tool.pypeeker.brig-standalone-programs]\n"
    'modules = ["brig.infra.proxy.program", "brig.domain.policy.egress"]\n'
)


def test_brig_standalone_programs_fires_on_a_listed_module_importing_brig(
    tmp_path: Path,
) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-standalone-programs",
        src=("src",),
        files={
            "src/brig/infra/proxy/program.py": "from brig.infra import helper\n",
            "src/brig/infra/helper.py": "X = 1\n",
        },
        rule_config=_STANDALONE_CONFIG,
    )
    assert_rule_fires(project, "brig-standalone-programs", src=("src",))


def test_brig_standalone_programs_fires_on_a_plain_import_of_brig(tmp_path: Path) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-standalone-programs",
        src=("src",),
        files={
            "src/brig/domain/policy/egress.py": "import brig.domain.claims\n",
            "src/brig/domain/claims.py": "X = 1\n",
        },
        rule_config=_STANDALONE_CONFIG,
    )
    assert_rule_fires(project, "brig-standalone-programs", src=("src",))


def test_brig_standalone_programs_is_clean_for_the_stdlib_and_unlisted_modules(
    tmp_path: Path,
) -> None:
    project = build_fixture(
        tmp_path,
        rule_id="brig-standalone-programs",
        src=("src",),
        files={
            "src/brig/infra/proxy/program.py": "import socket\nimport threading\n",
            "src/brig/infra/proxy/launch.py": "from brig.infra import helper\n",
            "src/brig/infra/helper.py": "X = 1\n",
        },
        rule_config=_STANDALONE_CONFIG,
    )
    assert_rule_clean(project, "brig-standalone-programs", src=("src",))
