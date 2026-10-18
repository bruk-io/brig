# Glossary

**claim**
: A statement made by a jail type's compile about what its jail enforces (decision-0001 rule 11).

**driver**
: A module in `presentation/drivers/` that performs effects yielded by domain operations, specific to each jail type (decision-0001 rule 10).

**effect**
: A value yielded by an operation or teardown generator for a driver to perform and report back from (examples: `Spawn`, `Reap`, `Verify`, `SignalGroup`; decision-0001 rule 10).

**embedder**
: A program that embeds brig as a library to create, run, and tear down jails (decision-0001 rule 1).

**evidence**
: Results from an e2e battery that plants a violation to verify a claim; paired with claims to produce a grade (decision-0001 rule 11).

**grade**
: The result of `grade(claims, evidence)`: the only producer of a report stating whether a jail enforces its claims (decision-0001 rule 11).

**jail**
: A jailed process or set of processes confined and controlled by a jail type: for bwrap, the jail is exactly its one process (decision-0001, `presentation/api.py`).

**jail type**
: A slice containing `domain/jail_types/<type>.py` and `presentation/drivers/<type>.py` (examples: bwrap, seatbelt); adding a type touches no other (decision-0001 rule 3).

**plan**
: What a jail type's compile produces: the argv its one process runs and which file descriptors it may inherit (`domain/plan.py`, decision-0001 rule 9).

**process**
: A spawned process's identity (pid and pgid) sufficient to reap, signal, or verify it later (`domain/effects.py`, decision-0001 rule 10).

**step**
: Each effect a generator yields during an operation or teardown; examples include spawning the jail's process, reaping its exit code, signaling its process group, or verifying it is gone (decision-0001 rule 10).

**supervisor**
: The process with PID 1 inside a jail, running in `infra/supervisor/program.py`, that coordinates the jail's operations; known historically as "agent" but called supervisor in this design (decision-0001 rule 12).
