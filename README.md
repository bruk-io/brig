# brig

A standalone sandbox library: it jails a program's processes and grades how well each
part of the jail is enforced. It imports the standard library only, and it knows
nothing of the programs that embed it.

A channel's connection is the one readiness verified: `await_channel_ready` returns
`ChannelReady`, whose `connection` the embedder uses, owns and closes. An embedder never dials a
reservation's `bound_path` itself, since the jail can swap its socket there for a link to a host
socket once readiness has passed. `docs/spec/index.md` is the whole contract.

See `CLAUDE.md` for where the work starts.
