"""The supervisor: `wire.py` and `program.py` assemble into the one stdlib-only
file dropped as PID 1 inside the jail's own namespace (decision-0001 rule 17).
`link.py`, the host's end of the same wire protocol, runs in the library's own
process instead and stays on this side of that boundary (decision-0002).
"""
