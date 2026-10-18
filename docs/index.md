# brig

brig is a standalone sandbox library: it jails a program's processes and grades how well each
part of the jail is enforced. It imports the standard library only, and it knows nothing of the
programs that embed it — this documentation never names one, and refers to it only as the
generic "Embedder" the [architecture view](architecture/index.md) below also uses.

brig is built in three layers, each with its own import rule: **domain** (pure, no I/O),
**infra** (plain data in and out, no brig types), and **presentation** (the only layer that
knows both of the others, and the only one that raises). `src/brig/__init__.py` re-exports
presentation's public surface — `Jail`, `create_bwrap_jail`, `run_jail`, `destroy_jail`, and
brig's own exceptions — and nothing from `domain` or `infra` directly; that surface is what the
[Reference](reference.md) page documents.

## Where to go next

- **[Glossary](glossary.md)** — every term brig's docs and code use, defined once, each entry
  pointing back to the decision record that settled it.
- **[SPEC](spec/index.md)** — brig's normative spec: the ten laws, carried verbatim from the old
  SPEC with their amendments folded in, then one section per layer.
- **[Architecture](architecture/index.md)** — the LikeC4 System Context view: brig as a single
  software system and the generic Embedder that creates, supervises, and tears down jails
  through it.
- **[Reference](reference.md)** — brig's public API, generated from its own docstrings at build
  time; this page is never committed, only built.

## Where the work starts

The board is the source: `backlog task list --plain` for the open work, and
`backlog/decisions/` for the decisions already made — in particular decision-0001, which lays
out this three-layer rebuild and the rule behind each layer boundary.
