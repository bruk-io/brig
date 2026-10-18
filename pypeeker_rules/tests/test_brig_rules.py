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
