# Glossary

**channel**
: A named request channel an embedder declares for its jail: one file, usually a socket, in the jail's own channel directory (`domain/channels.py`, decision-0002).

**claim**
: A statement made by a jail type's compile about what its jail enforces (decision-0001 rule 11).

**destination**
: A host and a port a jail may reach through its egress proxy, and what an embedder grants: an exact hostname, `*.suffix` (the names under it, never the suffix itself) or an exact IP literal, always with one port (`domain/policy/egress.py`, decision-0009 item 3).

**driver**
: What performs the effects a domain generator yields: `presentation/driver.py`, shared by every jail type, beside each type's own `presentation/drivers/<type>.py` (decision-0001 rule 10, decision-0007).

**effect**
: A value yielded by an operation or teardown generator for a driver to perform and report back from (examples: `StartSupervisedCommand`, `AwaitSupervisorDone`, `Verify`, `SignalGroup`, `Release`; decision-0001 rule 10).

**egress bridge**
: The supervisor's listener on `127.0.0.1:3128` inside a jail with an egress policy, the jail's one route out: each connection it accepts is handed to the egress proxy as one end of a socketpair, sent with `SCM_RIGHTS`, and relayed (`infra/supervisor/program.py`, decision-0009 item 1).

**egress change**
: One `allow_egress` or `revoke_egress` a running jail's egress proxy was sent: a kind, a destination, and when; it applies to the next connection the proxy takes, never to one already open, and the jail is not restarted (`EgressChange`, `domain/policy/egress_record.py`, decision-0009 item 5).

**egress decision**
: What a jail's egress proxy did with one request that named a destination: allowed or refused, the destination, the reason, the time and the proxy's count, handed back to the embedder as data by `egress_decisions` with the envelope line the proxy wrote (`EgressDecision`, decision-0009 item 6).

**egress limits**
: What a jail's egress route may hold of the host at once: the proxy's and the bridge's connection caps (256 each) and the handshake deadline (30 s in all to name a destination), named constants in the programs that a test lowers through `EgressLimits` and nothing raises (TASK-0049).

**egress policy**
: The destinations a jail's command may reach, `EgressPolicy(allow)`; the empty one, the default, is loopback and nothing else. A name it grants reaches only public addresses unless an IP-literal grant names the private one (`domain/policy/egress.py`, decision-0009 items 3 and 4).

**egress proxy**
: The host-side process, one per jail with an egress policy, that reads what each bridged connection asks for (HTTP `CONNECT`, absolute-form HTTP, SOCKS5 `CONNECT`), decides it with the egress decision, resolves granted names itself, and connects only where the decision allowed; it ends with the jail (`infra/proxy/`, decision-0009 item 2).


**egress record**
: A jail's egress grants as created and every egress change since, in order, which the report states (`EgressRecord`, `egress_record(jail)`, decision-0009 item 5).

**embedder**
: A program that embeds brig as a library to create, run, and tear down jails (decision-0001 rule 1).

**evidence**
: Results from an e2e battery that plants a violation to verify a claim; paired with claims to produce a grade (decision-0001 rule 11).

**grade**
: The result of `grade(claims, evidence)`: the only producer of a report stating whether a jail enforces its claims (decision-0001 rule 11).

**jail**
: The confined processes a jail type created: its supervisor, PID 1 inside it, and everything that supervisor starts (decision-0002, `presentation/jail.py`).

**jail type**
: A slice containing `domain/jail_types/<type>.py` and `presentation/drivers/<type>.py` (examples: bwrap, seatbelt); adding a type touches no other (decision-0001 rule 3).

**log envelope**
: The one shape of every line brig's own processes write: one JSON object, `time`, `level`, `source` and `event` first and in that order, then the event's own fields, made only by `infra/log.py`'s `encode` (decision-0001 rule 14, TASK-0001 criterion 15). The library itself writes no line.

**plan**
: What a jail type's compile produces: the command its supervisor runs and its candidate environment (`domain/plan.py`, decision-0001 rule 9).

**process**
: A started process's identity (pid and pgid), enough to signal, verify or release it later (`domain/effects.py`, decision-0001 rule 10).

**readiness**
: A verified connect to a reservation's socket, opened by its name beneath the fd the jail holds on its channel directory, through no link and without blocking (TASK-0045): ready when a process in the jail's own PID namespace called `listen()` on the socket that answered (decision-0005). `await_channel_ready`'s `ChannelReady` carries that connection, open; the embedder uses it, owns it and closes it, and never dials the path, since the jail can replace its socket with a symbolic link to a host socket once readiness has passed (TASK-0001.34).

**reservation**
: A channel's place in the jail's channel directory, made before the jail's process starts: its `bound_path` on the host and its `endpoint` inside the jail, which the embedder passes to the jailed command in argv, never env (`domain/channels.py`, decision-0002). The embedder never dials `bound_path`: it talks over the connection readiness hands back (TASK-0001.34).

**step**
: Each effect a generator yields during an operation or teardown; examples include starting the jail's supervisor, awaiting its report, signalling its process group, or verifying it is gone (decision-0001 rule 10).

**supervisor**
: The process with PID 1 inside a jail, running in `infra/supervisor/program.py`, that coordinates the jail's operations; known historically as "agent" but called supervisor in this design (decision-0001 rule 12).
