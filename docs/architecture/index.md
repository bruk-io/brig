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
