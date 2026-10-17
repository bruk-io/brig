---
id: decision-0001
title: 'Rebuild brig from empty in three layers: domain, infra and presentation'
date: '2026-10-17 19:05'
status: accepted
---
## Context

The old brig (about 18,000 lines, 63 modules, a 3,950-line SPEC) is layered by stage,
`core -> mech -> stack -> run -> probe`, with `runtime`, `proxy` and `trampoline` beside them. A
jail type is spread over four packages, pure decisions sit inside the code that does I/O, grades are
stated before anything proves them, one role has two names (supervisor and "agent"), and the
supervisor program is written to an older Python than the rest. About half of what it ships, its one
embedder never uses. Its gate checks the stage DAG; most of its other rules are convention carried
by review.

The intent (the board's root task) asks for it rewritten with a focus on architecture, in the owner's
Python approach, in a repository of its own that knows nothing of the programs that embed it, with no
backwards compatibility. This record is its design, settled with the owner in conversation on
2026-10-17: the layout, what to cut, testing, tooling and logs.

What does not change: brig's ten laws (the old SPEC, section 2). They are the security properties,
not the structure, and every rule below serves them. The measured facts in the old SPEC's rulings
(what bwrap covers as root, why carve-outs need pins, the seal, `mount_too_revealing`, Docker's
seccomp) are evidence the rebuild reuses, cited as "old SPEC decision-NNN".

## Decision

### Where it is built

In this repository, from empty, on `main`. The old brig is read-only reference kept outside the
repository (`~/ref/brig-v1`); nothing of it is copied in. Embedders keep running on the old brig
until the new one can jail what they run, and each moves in its own repository.

### The layout

```
justfile                every command the work runs, each written once (rule 15)
pyproject.toml          the package, ruff, mypy, pytest, and the pypeeker gate (the rules below)
pypeeker_rules/brig.py  brig's custom pypeeker rules
scripts/                affected-test selection for `just check`; the step runner for `just done`
mkdocs.yml
src/brig/
  __init__.py           re-exports presentation's api: the whole public surface
  domain/               pure: no I/O, imports nothing outside domain/
    spec.py  facts.py  plan.py  claims.py  grades.py  records.py  identity.py
    effects.py          what an operation asks for, and what it observes
    operations.py       create, start, stop, destroy: generators of effects
    teardown.py         the verified kill ladder, a generator of effects
    egress.py           is this destination allowed
    policy/             env.py, paths.py
    jail_types/         bwrap.py, seatbelt.py (oci.py when it is unpaused)
  infra/                imports nothing from brig: plain data in and out
    processes.py        spawn, signal a group, read an identity, reap
    files.py            read and write beneath a root, through no link
    tether.py  sockets.py  sandbox_exec.py
    log.py              the one log envelope and its encoder (rule 14)
    supervisor/         wire.py (the messages), program.py (PID 1), link.py (the host's end)
    proxy/server.py     the egress server, given an allowed() callable
  presentation/         the only layer that knows both
    api.py  errors.py  report.py
    ports.py            Protocols for the infra presentation calls
    drivers/            bwrap.py, seatbelt.py, dry_run.py: perform a generator's effects
    proxy_main.py       the egress process's entry point
tests/
  unit/                 one pure function each, nothing mocked
  integration/          brig's parts together, the world faked at its edge; fakes.py
  e2e/                  the real world: whole journeys and the batteries, or one infra module
docs/                   index, glossary, spec/, the generated reference, and architecture/ (LikeC4)
```

### The rules

Each rule names the check that enforces it. Every boundary is a pypeeker rule in this repository's
gate, run by `just gates` (index first, then `check --strict`: a bare `check` against a missing
index passes silently), and every new pypeeker rule lands with a test that plants a violation and
sees the rule report it.

1. **Three layers.** `domain` imports nothing outside `domain`. `infra` imports nothing from brig.
   `presentation` imports both. Nothing in brig imports `presentation` but `brig/__init__.py`.
   (pypeeker: `brig-layers`, strict, its allow table `domain = []`, `infra = []`,
   `presentation = ["domain", "infra"]`.)
2. **The domain does no I/O.** No import of `os`, `subprocess`, `socket`, `signal`, `select`,
   `time`, `threading`, `shutil`, `resource`, `tempfile` or `logging` under `domain/`; `pathlib`
   for `PurePath` only. Facts, time and identity enter as data. (pypeeker: `brig-pure-domain`, the
   module list in its options; `no-impure-functions` with an empty budget for `domain`.)
3. **A jail type is a slice.** `domain/jail_types/<type>.py` and `presentation/drivers/<type>.py`
   are one jail type's; no module of one type imports another type's. Adding a type touches no
   other. (pypeeker: `brig-slices`.)
4. **Tests are layered by where the mocks start** (the owner's test rules). `tests/unit/` imports
   only `brig.domain`; `tests/integration/` imports brig's public API and
   `tests/integration/fakes.py`; `tests/e2e/` imports the public API, or one `brig.infra` module
   for a gateway test. (pypeeker: `brig-test-layers`.)
5. **Fakes, never patches.** Doubles live only in `tests/integration/`, as fakes of the world at
   infra's edge, and a test asserts on their state. No `unittest.mock`, no `monkeypatch`, no mock
   library anywhere; time, randomness and the host enter as data. The integration suite runs twice
   in one process. (pypeeker: `brig-no-patching`; `just done` runs the integration suite twice.)
6. **The house rules.** A package `__init__.py` only re-exports; no reaching into another module's
   `_names`; a public name only its own module uses is private; importing a module has no side
   effects; no import cycles. (pypeeker: `init-reexport-only`, `under-exposed-access`,
   `over-exposed-module-symbol`, `import-time-side-effects`, `no-import-cycles`.)
7. **Four uses of `class`.** A frozen dataclass for shape, a `Protocol` for a port, an `Enum` or
   `StrEnum` for a closed set, an `Exception` subclass for a failure. A class holding changing state
   only in `infra/`, its invariant in its docstring. No inheritance but from `Exception`, `Enum` and
   `Protocol`. (pypeeker: `brig-class-forms`.)
8. **Data says what it is.** Tuples in domain types; `frozendict` for mappings; `StrEnum` for every
   persisted or sent value; a closed `TypedDict` for every JSON shape; `sentinel` where a fact is
   unknown. (mypy strict; a unit test that every JSON shape is closed.)
9. **What happens next is a value.** A deciding function returns an `Enum` member or a union of
   frozen dataclasses, matched to `assert_never`. Compile returns `Plan | Refused`; only `api`
   raises. (mypy strict.)
10. **Effects are yielded where decisions and I/O alternate.** Operations and teardown are
    generators of effect values; a driver per jail type performs them; a dry-run driver prints a
    plan. (Unit tests drive the generators by hand and pin the order: verify before signalling, TERM
    before KILL, verify after.)
11. **Grades come only from evidence.** A jail type's compile produces claims, never grades;
    `grade(claims, evidence)` is the one producer of a report; evidence comes from an e2e battery
    that plants the violation with a positive control (law 10). (A test that every claim of every
    jail type has a battery, and a claim without evidence grades `unenforced`.)
12. **One word, one thing.** The glossary in `docs/` names each term once: jail, jail type,
    process, step, plan, claim, evidence, grade, supervisor (never agent), driver, effect, embedder.
    (pypeeker: `brig-vocabulary` refuses `agent` in a name under `src/brig`.)
13. **Errors say what to do.** One `Exception` subclass per failure, every raise in its docstring
    (ruff DOC501 and DOC502, preview on), context added with `add_note` at infra's edge.
14. **brig's processes log JSON lines; the library logs nothing.** Every line the supervisor
    program, the egress proxy and its decisions write is one JSON object in one envelope, encoded by
    `infra/log.py`. The library writes no log: what it knows comes back to the embedder as data.
    The envelope's fields are a design task's (the intent's open question). (pypeeker:
    `brig-one-writer` refuses `print` and writes to stdout or stderr outside `infra/log.py` and the
    supervisor's wire; an e2e test parses every line the e2e runs capture.)
15. **`just` is the entry point.** `just check` runs the unit and integration tests the change
    reaches; `just done` runs ruff, mypy, every pypeeker rule, every test in every layer, the docs
    build and the architecture lint, each reported whole; CI runs `just done`.
16. **Templates for spliced languages.** The Seatbelt profile is rendered from a t-string; its
    renderer refuses a plain `str` by type. (mypy strict.)
17. **Python 3.15, every file.** The supervisor program included: it runs only under 3.15 or
    later, the interpreter brig itself runs on, and is assembled from `infra/supervisor/wire.py` and
    `program.py`, stdlib only. (A test that the delivered file is exactly those two and imports
    nothing else, and one that it refuses an older interpreter, saying which it needs.)
18. **The SPEC follows the layers.** `docs/spec/`: the ten laws carried verbatim with their
    amendments folded in, then one section per layer. A behaviour change is a SPEC change first;
    new rulings are this board's decisions, and the old SPEC's are cited as "old SPEC
    decision-NNN", so no number means two things.

### What is kept, cut and paused

The intent's criteria are the list. Kept: the filesystem policy, environment scrubbing, channels,
the supervisor, the verified teardown and its report, grades, egress through the allowlisting proxy
(its one helper process, started and stopped as part of the jail), and the interpreter checks. Cut:
resource limits and the trampoline, rebuilding a jail in another process, probes as public API,
events and denial signatures, exec fidelity, the mechanism stack and its compatibility matrix, the
fake runtime, and the general helper machinery. Paused: oci, which keeps its place in the layout
(`jail_types/oci.py`, `drivers/oci.py`, `infra/docker.py`) and is built later; until then nothing may
assume a process has a host pid or that a jail has a supervisor program, since `docker exec` stands
in for one.

### The order, outside-in

Each step is a task under the intent, sized when filed:

1. Scaffolding: the uv project, the justfile and its scripts, the empty layers, the pypeeker rules
   above with their planted-violation tests, and CI. (The settings file is the seed's first commit.)
2. Docs and the architecture model: `docs/` with the generated reference, the glossary, the SPEC's
   start, and the LikeC4 model with a System Context view.
3. The walking skeleton: the thinnest journey through every layer (create a bwrap jail through the
   API, run `true`, see exit 0, tear it down, verified), with one unit, one integration and one e2e
   test.
4. Slices, each starting from an integration test at the API and working inward: the filesystem
   policy, the environment, channels, the teardown ladder in full, grades and their batteries, the
   log envelope, egress, then Seatbelt.

## Consequences

- Every security decision is pure and reviewable in one layer; the real-world suites shrink to e2e
  journeys, batteries and gateway tests.
- Every boundary in the layout is a pypeeker rule, so a change that crosses one fails `just done`,
  not a review.
- A jail type is a slice: oci, a microVM or an ssh host is its own modules, touching no other.
- A grade cannot be written without evidence; the honesty law is structural.
- brig knows nothing of its embedders; each moves to the new API in its own repository.
- The old SPEC's decision numbers stay valid as citations of measured facts.

## Acceptance

Accepted by the owner in conversation, 2026-10-17, after the brainstorm this record sets down, with
one addition: the boundaries are enforced with pypeeker. Rules 1 to 7, 12 and 14 name the pypeeker
rules that do it.
