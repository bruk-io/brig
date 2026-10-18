"""brig's own gate rules for pypeeker: decision-0001's rules 1-7, 12 and 14.

Written against ``pypeeker.dsl.register_dsl_rule`` — the only plugin surface
still alive on pypeeker's ``main`` after its DSL rewrite deleted the legacy
``pypeeker.check.rules.register_rule`` API. A rule here is a selection plus a
``str.format`` message template; nothing registers at import time beyond the
calls below, by the same rule ``import-time-side-effects`` polices everywhere
else.

One confirmed, load-bearing limitation up front, because it shapes
``brig-class-forms`` below: this DSL's ``symbols()`` universe exposes no base
class / inheritance facts as a *row field* — ``pypeeker.models.symbols.Symbol``
carries no ``bases`` field, ``pypeeker.dsl.columns.COLUMNS`` is a closed table
with no ``register_column``, and ``Opaque.evaluate`` calls ``self.fn(ctx.row)``
with no corpus access, so a ``where()`` clause alone cannot ask "does this
class inherit from X". ``pypeeker.analysis.hierarchy.Hierarchy`` (the one
place pypeeker computes class hierarchy with full cross-module resolution)
stays out of reach the same way: it needs the file's source text through a
``read_source`` callback, and the corpus/resolver it resolves against, that a
``register_dsl_rule`` build function is never handed.

There **is** a way around the row-field surface, confirmed empirically
(TASK-0001.04): ``pypeeker.analysis.register_trait``'s provider signature,
``(file_index, symbol_id) -> Trait``, hands a hand-written provider the whole
``FileIndex`` — not a row's declared fields — and ``trait_of(name).value`` is
a real ``where()``-clause read of it (``pypeeker.dsl.TraitRead``). A class's
declared-base reference sits in the class's *parent* scope with a location
inside the class's own scope span (a class's ``scope_id`` equals its
``symbol_id`` — the discriminator ``hierarchy.py`` documents), and that
reference's ``symbol_id`` already resolves within one file: to
``<builtins>.Exception`` for a bare ``Exception`` base, or to the same-file
``IMPORT`` symbol for ``Protocol``/``Enum``/``StrEnum``, whose own
``imported_from`` names the qualified origin — no source-text parsing, no
cross-module resolver needed. ``brig-class-forms`` below uses exactly this
for the inheritance restriction. It is still single-file-only: a base
reached through an attribute chain (``import typing as t; class C(t.Protocol)``)
or a dynamic one resolves to neither shape and is conservatively *not*
flagged (never a guessed violation, since a guessed ``True`` would fail
``--strict`` on conforming code, not just report it at lower confidence) —
a narrow, accepted gap of the same kind ``brig-one-writer``'s
aliased-module-import gap already documents: it misses a real violation
reached through that one path, rather than reporting one that is not there.

A base *re-exported* through another project module is **not** that case,
despite what this docstring claimed before TASK-0001.19: it resolves to a
real same-file ``IMPORT`` whose ``imported_from`` names the re-exporting
module (``brig.domain.shim.Protocol``), which is not in
``_EXEMPT_BASE_IMPORT_ORIGINS``, so it lands in ``disallowed`` and *fires* on
a genuinely exempt base. Within one file that fact is indistinguishable from
a genuine project base (``brig.domain.base.Mixin``), which must fire, so the
two cannot be told apart here at all. Verified empirically both ways
(TASK-0002 review); brig declares no such re-exported base today, so the gate
is clean by conformance rather than by suppression. Tracked as TASK-0001.19.

That "cannot tell" verdict needs a channel of its own, separate from
"resolves to an exempt shape" — ``brig-class-forms``'s stateful-class check
(rule 7's fifth shape) asks "is this class exempt from *that* check", and
reads the same unresolved base as its answer. Collapsing "cannot tell" into
a plain ``value=False`` there, consumed through ``not_(...eq(True))``, reads
as "confirmed not exempt" and *fires* a finding out of a base this binder
simply never resolved — manufacturing a violation rather than suppressing
one, the opposite of this gap's accepted shape (TASK-0001.18 review, fixed
by splitting the single disallowed/exempt walk three ways: ``disallowed``,
``exempt``, and ``ambiguous`` — see ``_classify_header_bases``). The
inheritance-restriction check above stays a two-way, false-negative-only
gap; the stateful-class check needs the third bucket because it is
consulted by negation.
"""

from collections.abc import Mapping
from typing import Any

from pypeeker.analysis import Trait, register_trait
from pypeeker.dsl import (
    DslRule,
    MultiPartRule,
    RulePart,
    Selection,
    all_of,
    any_of,
    imports,
    not_,
    opaque,
    references,
    register_dsl_rule,
    row,
    symbols,
    trait_of,
)
from pypeeker.models import Confidence, FileIndex, ReferenceKind, ScopeKind, SymbolKind

_DEFAULT_ROOT = "src/brig"


def _dotted(path: str) -> str:
    """'src/brig/domain' -> 'brig.domain'. The layout's one source root is 'src'."""
    return path.removeprefix("src/").replace("/", ".")


# ---------------------------------------------------------------------------
# rule 1: brig-layers
# ---------------------------------------------------------------------------


def _layers_allow(options: Mapping[str, Any]) -> Mapping[str, list[str]]:
    return options.get("allow") or {}


def _layers_package(options: Mapping[str, Any]) -> str:
    return _dotted(options.get("root", _DEFAULT_ROOT))


def _layers_forbidden_edges(package: str, allow: Mapping[str, list[str]]) -> list[Any]:
    """One clause per layer: it imports a declared layer the allow table draws no edge to."""
    layers = tuple(allow)
    clauses = []
    for layer in layers:
        denied = [other for other in layers if other != layer and other not in allow[layer]]
        if denied:
            clauses.append(
                all_of(
                    row.module.is_within(f"{package}.{layer}"),
                    any_of(
                        *(row.imported_from.is_within(f"{package}.{other}") for other in denied)
                    ),
                )
            )
    return clauses


def _layers_crossings(options: Mapping[str, Any]) -> Selection | None:
    """Imports along an edge ``[tool.pypeeker.brig-layers.allow]`` does not draw."""
    allow = _layers_allow(options)
    if not allow:
        return None
    edges = _layers_forbidden_edges(_layers_package(options), allow)
    if not edges:
        return None
    return imports().where(all_of(row.imported_from.is_true(), any_of(*edges)))


def _layers_undeclared(options: Mapping[str, Any]) -> Selection | None:
    """Modules under the root that belong to no declared layer, in strict mode."""
    allow = _layers_allow(options)
    if not allow or not options.get("strict"):
        return None
    package = _layers_package(options)
    return symbols().where(
        all_of(
            row.kind.is_in(SymbolKind.MODULE, SymbolKind.PACKAGE),
            row.module.is_within(package),
            not_(row.module.eq(package)),
            *(not_(row.module.is_within(f"{package}.{layer}")) for layer in allow),
        )
    )


register_dsl_rule(
    MultiPartRule(
        rule_id="brig-layers",
        parts=(
            RulePart(
                build=_layers_crossings,
                message=(
                    "'{module}' may not import '{imported_from}': decision-0001's "
                    "layer table draws no such edge. If the layering really changed, "
                    "add the edge to [tool.pypeeker.brig-layers.allow] with the reason"
                ),
            ),
            RulePart(
                build=_layers_undeclared,
                message=(
                    "'{module}' is in no declared layer; a new layer gets a row in "
                    "[tool.pypeeker.brig-layers.allow] saying what it may import"
                ),
            ),
        ),
    )
)


# ---------------------------------------------------------------------------
# rule 2: brig-pure-domain (the deterministic half; no-impure-functions with
# include=["brig.domain*"] is enabled separately in pyproject.toml for the
# heuristic half)
# ---------------------------------------------------------------------------

_DEFAULT_BANNED_IMPORTS = (
    "os",
    "subprocess",
    "socket",
    "signal",
    "select",
    "time",
    "threading",
    "shutil",
    "resource",
    "tempfile",
    "logging",
)


def _pure_domain_imports(options: Mapping[str, Any]) -> Selection:
    """Imports of an I/O module anywhere under the domain root.

    ``pathlib`` is deliberately not on this denylist — decision-0001 rule 2
    allows it for ``PurePath``. Restricting it to *only* ``PurePath`` is a
    usage-level question (which names a module's imports are actually used
    for) that this import-level rule cannot ask; a domain module importing
    ``pathlib.Path`` for filesystem I/O is not caught here and remains a
    review concern.
    """
    root = _dotted(options.get("root", f"{_DEFAULT_ROOT}/domain"))
    banned = tuple(options.get("banned-imports") or _DEFAULT_BANNED_IMPORTS)
    return imports().where(
        all_of(
            row.module.is_within(root),
            any_of(*(row.imported_from.is_within(name) for name in banned)),
        )
    )


register_dsl_rule(
    DslRule(
        rule_id="brig-pure-domain",
        build=_pure_domain_imports,
        message=(
            "'{module}' imports '{imported_from}': the domain does no I/O "
            "(decision-0001 rule 2). Facts, time and identity enter as data"
        ),
    )
)


# ---------------------------------------------------------------------------
# rule 3: brig-slices
# ---------------------------------------------------------------------------

_SLICE_PREFIXES = (
    f"{_dotted(_DEFAULT_ROOT)}.domain.jail_types.",
    f"{_dotted(_DEFAULT_ROOT)}.presentation.drivers.",
)


def _slice_name(dotted: str) -> str | None:
    """The jail-type leaf name of a dotted module under a slice package, or None.

    ``imported_from`` carries the imported *name* too (``from a.b import c`` ->
    ``"a.b.c"``, the binder's own documented shape) as well as a bare module
    import, so only the first segment past the slice prefix is taken -- not a
    requirement that nothing follow it.
    """
    for prefix in _SLICE_PREFIXES:
        if dotted.startswith(prefix):
            rest = dotted[len(prefix) :]
            if rest:
                return rest.split(".", 1)[0]
    return None


def _slice_crossings(options: Mapping[str, Any]) -> Selection:
    """Imports between two different jail types' domain/presentation modules."""
    del options

    @opaque("brig-slice-importer-type", reads=("module",))
    def _importer_type(record: Any) -> str | None:
        return _slice_name(record.module)

    @opaque("brig-slice-imported-type", reads=("imported_from",))
    def _imported_type(record: Any) -> str | None:
        return _slice_name(record.imported_from or "")

    return (
        imports()
        .with_field("importer_type", _importer_type)
        .with_field("imported_type", _imported_type)
        .where(
            all_of(
                row.importer_type.is_true(),
                row.imported_type.is_true(),
                not_(row.importer_type.eq(row.imported_type)),
            )
        )
    )


register_dsl_rule(
    DslRule(
        rule_id="brig-slices",
        build=_slice_crossings,
        message=(
            "'{module}' (jail type '{importer_type}') imports '{imported_from}' "
            "(jail type '{imported_type}'): a jail type's domain and presentation "
            "modules may not import another type's (decision-0001 rule 3)"
        ),
    )
)


# ---------------------------------------------------------------------------
# rule 4: brig-test-layers
# ---------------------------------------------------------------------------


def _unit_test_violations(options: Mapping[str, Any]) -> Selection:
    """tests/unit imports from brig outside brig.domain."""
    del options
    return imports().where(
        all_of(
            row.file_path.startswith("tests/unit/"),
            row.imported_from.is_within("brig"),
            not_(row.imported_from.is_within("brig.domain")),
        )
    )


def _integration_test_violations(options: Mapping[str, Any]) -> Selection:
    """tests/integration imports anything from brig but the public API, or from
    tests but tests.integration.fakes.

    ``imported_from`` is ``"brig.X"`` for the ordinary ``from brig import X``
    public-API form, not bare ``"brig"`` -- comparing it to the literal string
    ``"brig"`` would flag every normal public-API import. The public API is
    instead *everything not reaching past it into a named layer*: a direct
    ``brig.domain``/``brig.infra``/``brig.presentation`` import is the
    violation, by the same reasoning rule 1's layer check uses.
    """
    del options
    return imports().where(
        all_of(
            row.file_path.startswith("tests/integration/"),
            any_of(
                row.imported_from.is_within("brig.domain"),
                row.imported_from.is_within("brig.infra"),
                row.imported_from.is_within("brig.presentation"),
                all_of(
                    row.imported_from.is_within("tests"),
                    not_(row.imported_from.is_within("tests.integration.fakes")),
                ),
            ),
        )
    )


def _e2e_test_violations(options: Mapping[str, Any]) -> Selection:
    """tests/e2e imports anything from brig but the public API or an infra module."""
    del options
    return imports().where(
        all_of(
            row.file_path.startswith("tests/e2e/"),
            any_of(
                row.imported_from.is_within("brig.domain"),
                row.imported_from.is_within("brig.presentation"),
            ),
        )
    )


register_dsl_rule(
    MultiPartRule(
        rule_id="brig-test-layers",
        parts=(
            RulePart(
                build=_unit_test_violations,
                message=(
                    "'{module}' (tests/unit) imports '{imported_from}': unit tests "
                    "import only brig.domain (decision-0001 rule 4)"
                ),
            ),
            RulePart(
                build=_integration_test_violations,
                message=(
                    "'{module}' (tests/integration) imports '{imported_from}': "
                    "integration tests import brig's public API ('brig') or "
                    "tests.integration.fakes (decision-0001 rule 4)"
                ),
            ),
            RulePart(
                build=_e2e_test_violations,
                message=(
                    "'{module}' (tests/e2e) imports '{imported_from}': e2e tests "
                    "import brig's public API ('brig') or a brig.infra module "
                    "(decision-0001 rule 4)"
                ),
            ),
        ),
    )
)


# ---------------------------------------------------------------------------
# rule 5: brig-no-patching
# ---------------------------------------------------------------------------

_MOCK_MODULES = ("unittest.mock", "mock", "pytest_mock")


def _mock_imports(options: Mapping[str, Any]) -> Selection:
    del options
    return imports().where(any_of(*(row.imported_from.is_within(name) for name in _MOCK_MODULES)))


def _monkeypatch_parameters(options: Mapping[str, Any]) -> Selection:
    """A function or fixture parameter literally named 'monkeypatch', anywhere.

    ``SymbolKind.PARAMETER`` rows carry ``name`` directly, so the fixture
    parameter is caught exactly, not just the mock-library imports.
    """
    del options
    return symbols().where(all_of(row.kind.eq(SymbolKind.PARAMETER), row.name.eq("monkeypatch")))


register_dsl_rule(
    MultiPartRule(
        rule_id="brig-no-patching",
        parts=(
            RulePart(
                build=_mock_imports,
                message=(
                    "'{module}' imports '{imported_from}': brig uses fakes, never "
                    "patches (decision-0001 rule 5)"
                ),
            ),
            RulePart(
                build=_monkeypatch_parameters,
                message=(
                    "'{symbol_id}' takes a 'monkeypatch' parameter: brig uses fakes, "
                    "never patches (decision-0001 rule 5)"
                ),
            ),
        ),
    )
)


# ---------------------------------------------------------------------------
# rule 7: brig-class-forms
# ---------------------------------------------------------------------------


def _non_frozen_dataclasses(options: Mapping[str, Any]) -> Selection:
    """Classes decorated ``@dataclass`` without ``frozen=True``, under ``root``.

    decision-0001 rule 7 names four allowed class shapes (frozen dataclass,
    Protocol, Enum/StrEnum, Exception subclass) plus a stateful class
    confined to ``infra/``, and forbids inheritance but from
    Exception/Enum/Protocol. This part checks the frozen half of the first
    shape, through the ``decorators`` field every symbol carries (raw
    decorator source text, per the binder). "A stateful class only in
    infra/" needs no base-class fact at all -- it is a question about *where
    a class lives* and *whether it declares a member*, not what it inherits
    -- and is checked separately below, by ``_stateful_outside_infra``.
    """
    root = options.get("root", _DEFAULT_ROOT)

    @opaque("brig-class-forms-unfrozen-dataclass", reads=("decorators",))
    def _unfrozen(record: Any) -> bool:
        for decorator in record.decorators:
            name = decorator.split("(", 1)[0].strip()
            if name in ("dataclass", "dataclasses.dataclass"):
                return "frozen=True" not in decorator.replace(" ", "")
        return False

    return symbols().where(
        all_of(row.kind.eq(SymbolKind.CLASS), row.file_path.startswith(f"{root}/"), _unfrozen)
    )


_EXEMPT_BASE_IMPORT_ORIGINS = ("typing.Protocol", "enum.Enum", "enum.StrEnum", "typing.TypedDict")
"""``imported_from`` values a header base may resolve to without violating
decision-0001 rule 7's inheritance restriction, beyond a bare ``Exception``/
``BaseException`` (handled separately: those resolve to ``<builtins>.*``, no
import involved).

``typing.TypedDict`` joins this list with TASK-0001.15 step 2
(``infra/supervisor/wire.py``'s message shapes): rule 7's own text names only
``Exception``/``Enum``/``Protocol`` as allowed bases, but rule 8 separately
*requires* ``TypedDict`` for every JSON shape, and ``TypedDict`` is the same
kind of ``typing`` construct as ``Protocol`` -- it states a structural shape,
not a real is-a relationship -- so it is exempted here on the same footing,
not inherited from the two rules having already agreed."""

_EXEMPT_BUILTIN_BASES = ("<builtins>.Exception", "<builtins>.BaseException")


def _pos(position: Any) -> tuple[int, int]:
    return (position.line, position.column)


def _header_base_refs(file_index: FileIndex, class_symbol: Any) -> list[Any]:
    """A class's candidate declared-base references.

    The discriminator ``pypeeker.analysis.hierarchy`` documents: a base
    reference lives in the class's *parent* scope (``class_symbol.parent_scope_id``)
    while its location falls inside the class's own scope span -- and a
    class's ``scope_id`` equals its ``symbol_id``, so that span is looked up
    directly rather than through any resolver. This also catches a
    ``metaclass=...`` keyword's value, which sits in the same place; brig's
    own rule 7 never uses one, so that is a known, accepted imprecision
    rather than a path worth the source-text parsing
    ``hierarchy._bases_for_class`` does to exclude it.
    """
    scope = next((s for s in file_index.scopes if s.scope_id == class_symbol.symbol_id), None)
    if scope is None:
        return []
    start, end = _pos(scope.span.start), _pos(scope.span.end)
    return [
        ref
        for ref in file_index.references
        if ref.in_scope_id == class_symbol.parent_scope_id
        and start <= _pos(ref.location.span.start) <= end
    ]


def _classify_header_bases(file_index: FileIndex, class_symbol: Any) -> tuple[bool, bool, bool]:
    """Classify ``class_symbol``'s declared-base references in one walk.

    Returns ``(disallowed, exempt, ambiguous)``, each independent (a compound
    header can set more than one):

    - ``disallowed``: at least one base resolves -- to a builtin other than
      ``Exception``/``BaseException``, a same-file import whose
      ``imported_from`` is not in ``_EXEMPT_BASE_IMPORT_ORIGINS``, or another
      class this same file declares -- to something that is not one of rule
      7's four typed shapes.
    - ``exempt``: at least one base resolves to ``Exception``/``BaseException``,
      or a same-file import of ``Protocol``/``Enum``/``StrEnum``.
    - ``ambiguous``: at least one base is a reference this file's own binder
      could not resolve to either of the above *within this one file* -- an
      attribute-chain base (``t.Protocol``) or a dynamic one. A base
      re-exported through another project module does *not* land here: it is
      a real same-file import, so it goes to ``disallowed`` (see the module
      docstring and TASK-0001.19). Never set by a class that simply declares no
      base at all (``refs`` is then empty), which is the plain "no base"
      case ``_stateful_outside_infra``'s fifth-shape check depends on
      telling apart from "an unresolvable one".

    A hand-written ``register_trait`` provider rather than a composed
    ``pypeeker.dsl.trait()``: the composed form only ever quantifies over the
    symbols universe's declared row fields (and refuses a ``project:`` reach
    outright), neither of which carries header-reference facts. This
    provider's signature -- ``(file_index, symbol_id) -> Trait`` -- hands the
    whole ``FileIndex`` instead: see the module docstring for the confirmed
    shape a header reference's ``symbol_id`` already resolves to within one
    file.

    Every ``disallowed``/``exempt`` verdict this walk reaches names its base
    outright (a builtin, a same-file import's recorded ``imported_from``, or
    a same-file class) -- never a guess. A base the walk cannot place in
    either bucket is reported through ``ambiguous`` instead of being folded
    into ``disallowed`` (which would reject conforming code, since a
    ``HEURISTIC`` finding still fails ``--strict`` same as ``DECLARED``) or
    into ``exempt`` (which would hide a real violation from the inheritance
    check *and* manufacture one in the stateful-class check, by telling it
    "not exempt" when the honest answer is "cannot tell"). An attribute-chain
    or dynamic base reaches no bucket and stays a false negative on the
    inheritance check -- the same accepted gap ``brig-one-writer``'s
    aliased-module-import gap already documents -- but no longer misfires
    the stateful-class check the way an unresolved
    attribute-chain base used to (confirmed empirically, TASK-0001.18
    review: ``import enum`` / ``class Signal(enum.Enum)`` with a
    stdlib-blessed ``self.number = number`` in ``__init__``, and ``import
    typing`` / ``class Port(typing.Protocol)`` with ``self.x = 1``, both of
    rule 7's own exempt shapes, used to fire the stateful-class check solely
    because the attribute-chain base could not be resolved).
    """
    imports_by_id = {s.symbol_id: s for s in file_index.symbols if s.kind is SymbolKind.IMPORT}
    local_class_ids = {s.symbol_id for s in file_index.symbols if s.kind is SymbolKind.CLASS}

    refs = _header_base_refs(file_index, class_symbol)
    # An attribute-chain base (`t.Protocol`) is two references in the same
    # scope span, not one: a plain read of `t` plus an unresolved attribute
    # access on it (`<unresolved>.Protocol`, `receiver_root_symbol_id` set to
    # `t`'s own symbol_id). `t` is a real same-file IMPORT symbol -- without
    # this filter it is itself mistaken for a declared base. A reference
    # consumed as another reference's receiver root is a sub-expression of
    # the real base, never the base itself. Filtered by symbol_id, not by
    # the specific reference instance: a compound header that both inherits
    # a name directly *and* uses that same name as a receiver root
    # (``class Bad(Base, Base.Mixin)``) also loses the direct ``Base`` base
    # this way -- a further instance of the same false-negative gap this
    # function's own docstring names, not a new one.
    receiver_roots = {ref.receiver_root_symbol_id for ref in refs if ref.receiver_root_symbol_id}

    disallowed = False
    exempt = False
    ambiguous = False
    for ref in refs:
        if ref.symbol_id in receiver_roots:
            continue
        if ref.symbol_id in _EXEMPT_BUILTIN_BASES:
            exempt = True
            continue
        imported = imports_by_id.get(ref.symbol_id)
        if imported is not None:
            if imported.imported_from in _EXEMPT_BASE_IMPORT_ORIGINS:
                exempt = True
            else:
                disallowed = True
            continue
        if ref.symbol_id in local_class_ids or ref.symbol_id.startswith("<builtins>."):
            disallowed = True
            continue
        # Not a builtin, not a same-file import, not a same-file class: an
        # attribute-chain base, a dynamic one, or one this file's own binder
        # could not resolve. Cannot tell whether it would resolve to an
        # exempt or a disallowed form through another module -- neither
        # bucket is set.
        ambiguous = True

    return disallowed, exempt, ambiguous


def _declares_disallowed_base(file_index: FileIndex, symbol_id: str) -> Trait:
    """Trait provider: does ``symbol_id`` (a class) declare a base that is not
    ``Exception``, ``Enum``/``StrEnum`` or ``Protocol`` (decision-0001 rule 7's
    inheritance restriction)?

    See ``_classify_header_bases`` for the shared walk and its conservatism.
    Reports ``Confidence.DECLARED`` always: every ``value=True`` here names
    its base outright, never a guess.
    """
    provenance = (
        f"pypeeker_rules.brig: declared-base references for '{symbol_id}' in {file_index.file_path}"
    )
    class_symbol = next((s for s in file_index.symbols if s.symbol_id == symbol_id), None)
    if class_symbol is None or class_symbol.kind is not SymbolKind.CLASS:
        return Trait(value=False, confidence=Confidence.DECLARED, provenance=provenance)

    disallowed, _, _ = _classify_header_bases(file_index, class_symbol)
    return Trait(value=disallowed, confidence=Confidence.DECLARED, provenance=provenance)


register_trait("brig-class-forms-disallowed-base")(_declares_disallowed_base)


def _disallowed_inheritance(options: Mapping[str, Any]) -> Selection:
    root = options.get("root", _DEFAULT_ROOT)
    return symbols().where(
        all_of(
            row.kind.eq(SymbolKind.CLASS),
            row.file_path.startswith(f"{root}/"),
            trait_of("brig-class-forms-disallowed-base").value.eq(True),
        )
    )


def _declares_exempt_base(file_index: FileIndex, symbol_id: str) -> Trait:
    """Trait provider: does ``symbol_id`` (a class) declare a base that *is*
    one of rule 7's four typed shapes -- ``Exception``/``BaseException``,
    ``Enum``/``StrEnum`` or ``Protocol``?

    The positive counterpart of ``_declares_disallowed_base``, needed because
    that trait's ``value=False`` already covers two different cases --
    "declares no base at all" (a candidate for the *stateful*-class shape
    below) and "declares one of the four typed bases" (not a candidate, even
    though it may also assign ``self.<name> = ...``) -- and
    ``_stateful_outside_infra`` has to tell them apart. Confirmed against
    brig's own ``presentation/errors.py``: each of its four ``Exception``
    subclasses assigns ``self.<name>`` in ``__init__``, and must not be
    flagged by the stateful-class check for that.

    See ``_classify_header_bases`` for the shared walk. A base reached
    through an attribute chain, or a dynamic one, is
    ``ambiguous`` there, not ``exempt`` -- it is ``_declares_ambiguous_base``,
    not this trait's ``value=False``, that tells ``_stateful_outside_infra``
    apart from "declares no base at all". Reports ``Confidence.DECLARED``:
    every ``value=True`` here names an exempt base outright.
    """
    provenance = (
        f"pypeeker_rules.brig: exempt-base references for '{symbol_id}' in {file_index.file_path}"
    )
    class_symbol = next((s for s in file_index.symbols if s.symbol_id == symbol_id), None)
    if class_symbol is None or class_symbol.kind is not SymbolKind.CLASS:
        return Trait(value=False, confidence=Confidence.DECLARED, provenance=provenance)

    _, exempt, _ = _classify_header_bases(file_index, class_symbol)
    return Trait(value=exempt, confidence=Confidence.DECLARED, provenance=provenance)


register_trait("brig-class-forms-exempt-base")(_declares_exempt_base)


def _declares_ambiguous_base(file_index: FileIndex, symbol_id: str) -> Trait:
    """Trait provider: does ``symbol_id`` (a class) declare a base reference
    this file's own binder cannot resolve to either rule 7's exempt shapes or
    a positively-disallowed one -- an attribute-chain base (``t.Protocol``)
    or a dynamic one? (A base re-exported through another project module is
    a real same-file import and lands in ``disallowed`` instead, not here --
    TASK-0001.19.)

    Exists so ``_stateful_outside_infra`` can tell "cannot tell whether this
    base is exempt" apart from "declares no base at all": both left
    ``_declares_exempt_base`` at ``value=False`` before this trait existed,
    and consuming that alone through ``not_(...eq(True))`` silently treated
    "cannot tell" as "confirmed not exempt" -- manufacturing a stateful-class
    finding on a base this single-file binder simply could not resolve,
    rather than suppressing one (TASK-0001.18 review: verified empirically
    against ``import enum`` / ``class Signal(enum.Enum)`` with
    ``self.number = number`` in ``__init__``, and ``import typing`` /
    ``class Port(typing.Protocol)`` with ``self.x = 1`` -- both rule 7's own
    exempt shapes, both firing the stateful-class check on the attribute-chain
    base alone). See ``_classify_header_bases`` for the shared walk. Reports
    ``Confidence.DECLARED``: "this file's binder could not resolve it" is
    itself a fact the binder already settled, not a guess.
    """
    provenance = (
        f"pypeeker_rules.brig: ambiguous-base references for '{symbol_id}' in "
        f"{file_index.file_path}"
    )
    class_symbol = next((s for s in file_index.symbols if s.symbol_id == symbol_id), None)
    if class_symbol is None or class_symbol.kind is not SymbolKind.CLASS:
        return Trait(value=False, confidence=Confidence.DECLARED, provenance=provenance)

    _, _, ambiguous = _classify_header_bases(file_index, class_symbol)
    return Trait(value=ambiguous, confidence=Confidence.DECLARED, provenance=provenance)


register_trait("brig-class-forms-ambiguous-base")(_declares_ambiguous_base)


def _declares_instance_state(file_index: FileIndex, symbol_id: str) -> Trait:
    """Trait provider: does ``symbol_id`` (a class) declare an instance
    attribute -- some ``self.<name> = ...`` / ``cls.<name> = ...`` the binder
    recorded as a member of this class's own scope, assigned from *inside a
    method*?

    A class's ``scope_id`` equals its ``symbol_id`` (the discriminator the
    module docstring and ``_header_base_refs`` both already use), and
    ``self.<name> = ...`` anywhere in the class's body declares ``<name>`` as
    a ``SymbolKind.VARIABLE`` member of exactly that scope
    (``pypeeker.binder.assignments._declare_instance_attribute``), deduplicated
    to the first such assignment. But a plain class-level field
    (``class Registry: DEFAULT = 1``) is *also* a ``VARIABLE`` member of the
    same class scope -- ``visit_assignment`` binds it there through the same
    ``_bind_into`` the plain-local case uses, just with the class body as the
    current scope -- and is not what this trait means by "instance state"
    (confirmed empirically: a planted ``class Registry: DEFAULT = 1`` fixture
    triggered this trait before this span check was added). The two are told
    apart by where the assignment's own location falls: ``self.x = ...``'s
    location sits inside a ``ScopeKind.FUNCTION`` scope (a method body,
    however deeply nested within it), while a class-level field's does not --
    the same span-containment test ``_header_base_refs`` already does for
    base references, over ``file_index.scopes`` instead of ``.references``.

    That needs no source-text parsing and no project-wide reach -- a plain
    scan of this one file's own symbols and scopes -- which is exactly the
    row-field limitation the module docstring names for the *base-class*
    questions (no ``bases`` field, no project corpus from a ``where()``
    clause) not applying here: "does some other symbol in this file name me
    as its parent scope, from inside one of my methods" is answered by
    scanning ``file_index.symbols``/``.scopes`` directly, the same move
    ``_declares_disallowed_base`` makes for header references.

    Reports ``Confidence.DECLARED``: the binder already decided this is an
    instance attribute, so there is nothing here to guess. A class whose only
    mutation runs through ``object.__setattr__(self, ...)`` (a frozen
    dataclass's usual escape hatch) is not seen either way by this trait --
    brig's own frozen dataclasses never use it, and ``_stateful_outside_infra``
    exempts the frozen-dataclass shape before this trait is even consulted.
    """
    provenance = (
        f"pypeeker_rules.brig: instance-attribute members of '{symbol_id}' in "
        f"{file_index.file_path}"
    )
    class_symbol = next((s for s in file_index.symbols if s.symbol_id == symbol_id), None)
    if class_symbol is None or class_symbol.kind is not SymbolKind.CLASS:
        return Trait(value=False, confidence=Confidence.DECLARED, provenance=provenance)

    function_spans = [
        (_pos(scope.span.start), _pos(scope.span.end))
        for scope in file_index.scopes
        if scope.kind is ScopeKind.FUNCTION
    ]

    def _assigned_inside_a_method(symbol: Any) -> bool:
        point = _pos(symbol.location.span.start)
        return any(start <= point <= end for start, end in function_spans)

    has_state = any(
        symbol.kind is SymbolKind.VARIABLE
        and symbol.parent_scope_id == symbol_id
        and _assigned_inside_a_method(symbol)
        for symbol in file_index.symbols
    )
    return Trait(value=has_state, confidence=Confidence.DECLARED, provenance=provenance)


register_trait("brig-class-forms-instance-state")(_declares_instance_state)


def _stateful_outside_infra(options: Mapping[str, Any]) -> Selection:
    """A class with instance state, outside a frozen dataclass or one of rule
    7's other three typed shapes, anywhere under ``root`` but ``infra/``.

    decision-0001 rule 7's fifth shape -- "a class holding changing state
    only in ``infra/``, its invariant in its docstring" -- is the one this
    module's own docstrings named as unchecked (TASK-0001.04). It turns out
    checkable without either of the two blocked paths the module docstring
    documents (a ``bases`` row field, or ``Hierarchy``'s cross-module
    resolution): "where a class lives" is a plain ``file_path`` comparison,
    and "whether it declares a member" is a same-file scan
    (``_declares_instance_state``), not a question about inheritance at all.

    A class exempted by one of the other three typed shapes
    (``_declares_exempt_base``: Exception/BaseException, Enum/StrEnum,
    Protocol) is not flagged even when it does assign ``self.<name> = ...`` --
    confirmed against brig's own ``presentation/errors.py``, whose four
    ``Exception`` subclasses do exactly that in ``__init__``. The
    frozen-dataclass shape is checked the same way ``_non_frozen_dataclasses``
    does, inline rather than through a trait, since both parts already read
    the same ``decorators`` field and brig's own frozen dataclasses hold no
    ``self.<name> = ...`` to begin with (their fields are class-level
    annotations, not assignments the binder would ever see here).

    A class whose base this single-file binder cannot resolve at all
    (``_declares_ambiguous_base``: an attribute-chain base, or a dynamic
    one) is not flagged either, for the same
    reason an unresolved base never fires ``_disallowed_inheritance``: this
    rule cannot tell such a base apart from one that would resolve to an
    exempt shape through another module, and firing here would manufacture a
    violation out of "cannot tell" rather than suppress one. Consuming only
    ``_declares_exempt_base``'s own ``value=False`` here, without this
    trait, previously collapsed that "cannot tell" into "confirmed not
    exempt" and fired wrongly on exactly that case (TASK-0001.18 review).
    """
    root = options.get("root", _DEFAULT_ROOT)
    infra_prefix = f"{root}/infra/"

    @opaque("brig-class-forms-lacks-frozen-shape", reads=("decorators",))
    def _not_a_frozen_dataclass(record: Any) -> bool:
        for decorator in record.decorators:
            name = decorator.split("(", 1)[0].strip()
            if name in ("dataclass", "dataclasses.dataclass"):
                return "frozen=True" not in decorator.replace(" ", "")
        return True

    return symbols().where(
        all_of(
            row.kind.eq(SymbolKind.CLASS),
            row.file_path.startswith(f"{root}/"),
            not_(row.file_path.startswith(infra_prefix)),
            _not_a_frozen_dataclass,
            not_(trait_of("brig-class-forms-exempt-base").value.eq(True)),
            not_(trait_of("brig-class-forms-ambiguous-base").value.eq(True)),
            trait_of("brig-class-forms-instance-state").value.eq(True),
        )
    )


register_dsl_rule(
    MultiPartRule(
        rule_id="brig-class-forms",
        parts=(
            RulePart(
                build=_non_frozen_dataclasses,
                message=(
                    "class '{symbol_id}' is decorated @dataclass without "
                    "frozen=True (decision-0001 rule 7)"
                ),
            ),
            RulePart(
                build=_disallowed_inheritance,
                message=(
                    "class '{symbol_id}' inherits from a base that is not "
                    "Exception, Enum/StrEnum or Protocol (decision-0001 rule 7). "
                    "Single-file check: a base reached through an attribute "
                    "chain, or a dynamic one, is not resolved and so cannot "
                    "trigger this; one re-exported through a project module "
                    "resolves to that module and does -- see the module "
                    "docstring"
                ),
            ),
            RulePart(
                build=_stateful_outside_infra,
                message=(
                    "class '{symbol_id}' declares instance state (a "
                    "'self.<name> = ...' assignment) but is not a frozen "
                    "dataclass, Protocol, Enum/StrEnum or Exception subclass: "
                    "decision-0001 rule 7 confines a stateful class to infra/, "
                    "its invariant in its docstring"
                ),
            ),
        ),
    )
)


# ---------------------------------------------------------------------------
# rule 12: brig-vocabulary
# ---------------------------------------------------------------------------


def _vocabulary_violations(options: Mapping[str, Any]) -> Selection:
    root = options.get("root", _DEFAULT_ROOT)
    banned = (options.get("banned-name") or "agent").lower()

    @opaque("brig-vocabulary-banned-name", reads=("name",))
    def _contains_banned(record: Any) -> bool:
        return banned in record.name.lower()

    return symbols().where(all_of(row.file_path.startswith(f"{root}/"), _contains_banned))


register_dsl_rule(
    DslRule(
        rule_id="brig-vocabulary",
        build=_vocabulary_violations,
        message=(
            "'{symbol_id}' names '{name}': the glossary names this role once and "
            "never 'agent' (decision-0001 rule 12)"
        ),
    )
)


# ---------------------------------------------------------------------------
# rule 14: brig-one-writer
# ---------------------------------------------------------------------------

_WRITE_STREAMS = (("sys", "stdout"), ("sys", "stderr"))
_DOTTED_WRITE_STREAMS = tuple(".".join(parts) for parts in _WRITE_STREAMS)
"""``_WRITE_STREAMS`` as the dotted names ``imported_from`` records them, e.g.
'sys.stdout' -- one source of truth, read both ways below."""


def _one_writer_allow(options: Mapping[str, Any]) -> tuple[str, ...]:
    """Modules decision-0001 rule 14 itself names as exempt: ``infra/log.py``
    (no findings to exempt there yet -- it writes through its own encoder,
    never ``print``/``sys.std*`` directly) and the supervisor's own wire
    (``infra/supervisor/program.py``, TASK-0001.15 step 2), configured per
    project since this is brig's own custom rule, not one of pypeeker's own
    options."""
    return tuple(options.get("allow") or ())


def _print_calls(options: Mapping[str, Any]) -> Selection:
    root = options.get("root", _DEFAULT_ROOT)
    allow = _one_writer_allow(options)
    return references().where(
        all_of(
            row.file_path.startswith(f"{root}/"),
            row.kind.eq(ReferenceKind.CALL),
            row.symbol_id.eq("<builtins>.print"),
            *((not_(row.module.is_in(*allow)),) if allow else ()),
        )
    )


def _stream_writes(options: Mapping[str, Any]) -> Selection:
    """A call through a 'sys.stdout'/'sys.stderr' receiver chain (e.g. '.write(...)').

    Two shapes, both from facts the binder already records on a reference:

    * the direct dotted form, ``sys.stdout.write(...)`` / ``sys.stderr.write(...)``
      -- matched on ``receiver_chain`` exactly, as before.
    * the ``from sys import stdout`` form -- ``stdout.write(...)`` (and any
      alias of it, ``from sys import stdout as out; out.write(...)``) has a
      one-name receiver chain, so it is caught instead through
      ``receiver_root_imported_from``: the same-file symbol the receiver root
      names carries ``imported_from`` set by the import binder (see
      ``_declare_import`` in ``pypeeker.binder.imports``) to the qualified
      name actually imported -- ``"sys.stdout"``/``"sys.stderr"`` -- no
      matter what local name it was bound to. This is the same "follow the
      import's recorded target, not the local name" move brig-pure-domain and
      brig-slices make on ``imported_from`` elsewhere in this file.

    A stream reached through an aliased *module* import instead
    (``import sys as s; s.stdout.write(...)``) produces a two-element
    receiver chain whose root's own ``imported_from`` is ``"sys"``, not
    ``"sys.stdout"`` -- neither shape above catches it, and it remains a
    known, narrower gap.
    """
    root = options.get("root", _DEFAULT_ROOT)
    allow = _one_writer_allow(options)
    return references().where(
        all_of(
            row.file_path.startswith(f"{root}/"),
            row.kind.eq(ReferenceKind.CALL),
            any_of(
                row.receiver_chain.is_in(*_WRITE_STREAMS),
                row.receiver_root_imported_from.is_in(*_DOTTED_WRITE_STREAMS),
            ),
            *((not_(row.module.is_in(*allow)),) if allow else ()),
        )
    )


register_dsl_rule(
    MultiPartRule(
        rule_id="brig-one-writer",
        parts=(
            RulePart(
                build=_print_calls,
                message=(
                    "'{module}' calls print(): brig's processes log JSON lines "
                    "through infra/log.py and the supervisor's wire, nothing else "
                    "writes (decision-0001 rule 14). Add it to "
                    "[tool.pypeeker.brig-one-writer].allow if it is one of those"
                ),
            ),
            RulePart(
                build=_stream_writes,
                message=(
                    "'{module}' writes to sys.stdout/sys.stderr directly: brig's "
                    "processes log JSON lines through infra/log.py and the "
                    "supervisor's wire, nothing else writes (decision-0001 rule 14). "
                    "Add it to [tool.pypeeker.brig-one-writer].allow if it is one of "
                    "those"
                ),
            ),
        ),
    )
)
