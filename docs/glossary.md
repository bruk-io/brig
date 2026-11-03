# Glossary

**channel**
: A named request channel an embedder declares for its jail: one file, usually a socket, in the jail's own channel directory (`domain/channels.py`, decision-0002).

**claim**
: A statement made by a jail type's compile about what its jail enforces (decision-0001 rule 11).

**driver**
: What performs the effects a domain generator yields: `presentation/driver.py`, shared by every jail type, beside each type's own `presentation/drivers/<type>.py` (decision-0001 rule 10, decision-0007).

**effect**
: A value yielded by an operation or teardown generator for a driver to perform and report back from (examples: `StartSupervisedCommand`, `AwaitSupervisorDone`, `Verify`, `SignalGroup`, `Release`; decision-0001 rule 10).

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

**plan**
: What a jail type's compile produces: the command its supervisor runs and its candidate environment (`domain/plan.py`, decision-0001 rule 9).

**process**
: A started process's identity (pid and pgid), enough to signal, verify or release it later (`domain/effects.py`, decision-0001 rule 10).

**readiness**
: A verified connect to a reservation's `bound_path`: ready when a process in the jail's own PID namespace called `listen()` on the socket that answered (decision-0005). `await_channel_ready`'s `ChannelReady` carries that connection, open; the embedder uses it, owns it and closes it, and never dials the path, since the jail can replace its socket with a symbolic link to a host socket once readiness has passed (TASK-0001.34).

**reservation**
: A channel's place in the jail's channel directory, made before the jail's process starts: its `bound_path` on the host and its `endpoint` inside the jail, which the embedder passes to the jailed command in argv, never env (`domain/channels.py`, decision-0002). The embedder never dials `bound_path`: it talks over the connection readiness hands back (TASK-0001.34).

**step**
: Each effect a generator yields during an operation or teardown; examples include starting the jail's supervisor, awaiting its report, signalling its process group, or verifying it is gone (decision-0001 rule 10).

**supervisor**
: The process with PID 1 inside a jail, running in `infra/supervisor/program.py`, that coordinates the jail's operations; known historically as "agent" but called supervisor in this design (decision-0001 rule 12).
