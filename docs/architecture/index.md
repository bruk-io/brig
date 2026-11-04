# Architecture

brig's architecture is modeled in LikeC4, under this directory (`docs/architecture/`),
following the c4-architecture plugin's layout: software systems under `models/`,
cross-system wiring under `models/landscape.c4`, and views under `views/`.

## System Context

brig is jailed behind one boundary: the program that embeds it. The System Context
view below shows brig as a single software system and the generic "Embedder" that
creates, supervises, and tears down jails through it — brig knows nothing more
specific about who embeds it than that — and the network destinations a jail with
an egress policy may reach, only those its embedder granted (decision-0009).

```likec4-view
brigContext
```

Source: [`views/brig/context.c4`](views/brig/context.c4),
[`models/landscape.c4`](models/landscape.c4).

## Containers

brig has three containers. The **library** is what an embedder links, running
inside the embedder's own process -- there is no separate library process. The
**supervisor** is the one file the library assembles from
`infra/supervisor/wire.py` and `program.py` (decision-0001 rule 17) and starts,
inside bwrap, as PID 1 of each jail's own PID namespace (decision-0002): it
makes itself non-dumpable before anything else (decision-0006), runs the
command as its child, reaps everything reparented to it, and reports one
outcome over its wire. `link.py`, the host's end of that wire, stays in the
library (its Supervisor Link component), on the host side of the boundary. The
**egress proxy** is one host-side process per jail with an egress policy
(decision-0009): the library assembles it from `infra/proxy/program.py` with the
domain's egress decision inlined as source, never imported, and starts it from its
stdin (its Proxy Link component); the supervisor hands it each connection accepted
on the jail's loopback, the jail's one route out, and it reaches only what the
decision allows. It ends with the jail.

```likec4-view
brigContainers
```

Source: [`views/brig/containers.c4`](views/brig/containers.c4),
[`models/brig/library.c4`](models/brig/library.c4),
[`models/brig/supervisor.c4`](models/brig/supervisor.c4),
[`models/brig/egress-proxy.c4`](models/brig/egress-proxy.c4),
[`models/brig/_relationships.c4`](models/brig/_relationships.c4).

## Components

The library container's components, one per module under
`src/brig/{domain,infra,presentation}/`, or one per tight group of modules
behind a single interface (the policy package; claims and grades; the
supervisor's host end). Each component's file names its modules. The grouping
shown is visual only (decision-0001 rule 1): domain's and infra's components
depend on neither presentation's nor each other's layer; presentation's
components depend on both. Every edge is an import in `src/brig`. The shared
**Driver** (`presentation/driver.py`) is the effect interpreter every jail
type uses; the **Bwrap Driver** (`presentation/drivers/bwrap.py`) is bwrap's
slice, `create_bwrap_jail`; the **API** (`presentation/api.py`) is what every
jail type shares, and **Jail** (`presentation/jail.py`) the value an embedder
holds and the real ports' wiring (decision-0007 item 5). The supervisor
container is not decomposed: it is one small program with no interface inside
it, so its parts are code, and it appears here only as the container the
Supervisor Link starts.

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
but deliberately left out of this view, as is every infra component -- a jail
type's infra primitive is real and correlated with that type, but it is not
part of rule 3's slice claim. The one edge drawn is inside bwrap's slice: its
driver compiling with its own jail type.

```likec4-view
brigJailTypes
```

Source: [`views/brig/jail-types.c4`](views/brig/jail-types.c4),
[`models/brig/library/seatbelt-jail-type.c4`](models/brig/library/seatbelt-jail-type.c4),
[`models/brig/library/seatbelt-driver.c4`](models/brig/library/seatbelt-driver.c4),
[`models/brig/library/oci-jail-type.c4`](models/brig/library/oci-jail-type.c4),
[`models/brig/library/oci-driver.c4`](models/brig/library/oci-driver.c4),
[`models/brig/library/docker.c4`](models/brig/library/docker.c4) (modeled, not shown above).
