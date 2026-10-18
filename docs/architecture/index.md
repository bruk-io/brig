# Architecture

brig's architecture is modeled in LikeC4, under this directory (`docs/architecture/`),
following the c4-architecture plugin's layout: software systems under `models/`,
cross-system wiring under `models/landscape.c4`, and views under `views/`.

## System Context

brig is jailed behind one boundary: the program that embeds it. The System Context
view below shows brig as a single software system and the generic "Embedder" that
creates, supervises, and tears down jails through it — brig knows nothing more
specific about who embeds it than that.

```likec4-view
brigContext
```

Source: [`views/brig/context.c4`](views/brig/context.c4),
[`models/landscape.c4`](models/landscape.c4).

## Containers

brig has exactly one container that is actually built today: the **library**
an embedder links, running inside the embedder's own process -- there is no
separate brig process yet. The **supervisor** box below is decision-0002's
design, not shipped code: none of `infra/supervisor/{wire,program,link}.py`
exist under `src/brig` as of this writing. Once built, `wire.py` and
`program.py` assemble into the one file dropped as PID 1 inside the jail
(decision-0001 rule 17) and cross into this container; `link.py` is the
host's end of that same wire protocol and stays in **library**, on the host
side of the boundary -- not depicted below, since this view shows containers,
not the components inside them. Whether `wire.py`'s own message format needs
sharing with `link.py` rather than crossing wholly into `supervisor` is still
open (DRAFT-0009), for whoever builds it. The supervisor box is drawn here,
tagged `#planned`, specifically so the boundary can be read and questioned
before anything is built against it -- do not mistake it for a built
container.

```likec4-view
brigContainers
```

Source: [`views/brig/containers.c4`](views/brig/containers.c4),
[`models/brig/library.c4`](models/brig/library.c4),
[`models/brig/supervisor.c4`](models/brig/supervisor.c4),
[`models/brig/_relationships.c4`](models/brig/_relationships.c4).

## Components

The library container's components, one per real module under
`src/brig/{domain,infra,presentation}/`. The grouping shown is visual only
(decision-0001 rule 1): domain's and infra's components depend on neither
presentation's nor each other's layer; presentation's components depend on
both. The supervisor has no components yet -- it has no code.

```likec4-view
brigLibraryComponents
```

Source: [`views/brig/components.c4`](views/brig/components.c4),
[`models/brig/library.c4`](models/brig/library.c4) (one component per file under
`models/brig/library/`).

## Jail types

The same components as above, grouped by jail type instead of by layer: bwrap
(built), Seatbelt (`#planned`, decision-0001's order puts it next), and oci
(`#paused` -- keeps its place in the layout, no order of work yet). Zero edges
between any two clusters is decision-0001 rule 3's own claim made visible ("a
jail type is a slice... no module of one type imports another's"), not
illustrative. Rule 3 names exactly two files per type (`domain/jail_types/<type>.py`,
`presentation/drivers/<type>.py`), so this view holds every type to that same
two-component shape; oci's own `infra/docker.py` is modeled (tagged `#paused`)
but deliberately left out of this view, the same way bwrap's own
`infra/processes.py` is -- a jail type's infra primitive is real and correlated
with that type, but it is not part of rule 3's slice claim.

```likec4-view
brigJailTypes
```

Source: [`views/brig/jail-types.c4`](views/brig/jail-types.c4),
[`models/brig/library/seatbelt-jail-type.c4`](models/brig/library/seatbelt-jail-type.c4),
[`models/brig/library/seatbelt-driver.c4`](models/brig/library/seatbelt-driver.c4),
[`models/brig/library/oci-jail-type.c4`](models/brig/library/oci-jail-type.c4),
[`models/brig/library/oci-driver.c4`](models/brig/library/oci-driver.c4),
[`models/brig/library/docker.c4`](models/brig/library/docker.c4) (modeled, not shown above).
