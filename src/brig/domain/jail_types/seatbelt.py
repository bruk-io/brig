"""The Seatbelt jail type's compile: pure, from a request to the SBPL profile and the argv that
starts the jail's supervisor under `/usr/bin/sandbox-exec` (decision-0001 rule 3; decision-0010).

`compile_rules` turns the embedder's `FsPolicy` (intent: readable and writable roots, write
denies, masks; decision-0007) and host facts (`HostPath`, symbolic link chains) into an ordered
tuple of `Rule`s, and everything else about the jail's profile and filesystem claims is read from
that one tuple: `render_profile` emits the SBPL profile from it through `_render_atom`
(decision-0001 rule 16: template strings `t"..."`, never string concatenation),
`_writable_shared_paths` grades `SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM` from it, and `ceilings` reads
`_beneath_writable` from it.

The order is the policy's meaning. Seatbelt evaluates rules in profile order, with the last
matching rule winning: entries emit shallowest target path first, and at one path a mask after a
write deny after a pin after a writable root after a readable one, so the more specific entry
wins where two overlap. Every writable root other than `"/"` and every directory strictly between
a writable root and a write deny, a mask, a nested readable root or brig's state directory is
pinned with `(deny file-write-unlink (literal ...))`, so the command cannot remove the writable
root or rename an intermediate directory to replace what it leads to. Then brig's own: a mask over
its state directory, metadata literals for the directories inside it leading to this jail's
supervisor script and channel directory, the supervisor script allowed read-only, the channel
directory allowed writable and for Unix-domain socket bind and connect, and (with an egress
policy) the loopback TCP bridge port.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from string.templatelib import Interpolation, Template

from brig.domain.channels import Reservations
from brig.domain.claims import Claim
from brig.domain.grades import Grade
from brig.domain.plan import Plan
from brig.domain.policy.env import proxy_environment
from brig.domain.policy.paths import FsPolicy, HostPath, PathKind, within

_SANDBOX_EXEC = "/usr/bin/sandbox-exec"
"""Darwin's userland entry point to the `com.apple.security.sandbox` kernel extension."""

_CHDIR_RUNNER = (
    "import os, runpy, sys; "
    "os.chdir(sys.argv[1]); "
    "sys.argv = sys.argv[2:]; "
    'runpy.run_path(sys.argv[0], run_name="__main__")'
)
"""Inline bootstrap when `cwd` is given: `/usr/bin/sandbox-exec` has no `--chdir` flag, so the
supervisor's interpreter changes to `cwd` before running the supervisor script in-process."""

_HEADER_LINES: tuple[str, ...] = (
    "(version 1)",
    "(deny default)",
    "(allow process-exec process-fork sysctl-read)",
    "(allow signal (target same-sandbox))",
    '(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo"))',
    '(allow file-read-data file-read-metadata (literal "/"))',
    (
        '(allow file-read* file-write-data (literal "/dev/null") (literal "/dev/zero") '
        '(literal "/dev/stdin") (literal "/dev/stdout") (literal "/dev/stderr") '
        '(subpath "/dev/fd"))'
    ),
    '(allow file-read* (literal "/dev/urandom") (literal "/dev/random"))',
)
"""The fixed baseline of every Seatbelt profile (decision-0010 item 1), each line measured on
macOS 27.0.1 (TASK-0061). No `(import "system.sb")`: CPython, `sh` and `git` start without it,
and without it the system's own paths are readable only where the policy reads them.

- Deny by default, then fork and exec, and `sysctl-read`, which CPython and `dyld` need at start
  (it also shows the jail every host process's argv, so `fs_read` is never `ENFORCED`).
- Signals only to processes in this same sandbox: unfiltered, a jail killed a host process of
  the same user. The command can still signal its own children and its supervisor.
- No refusal of `setsid` or `setpgid`: refusing the system calls held nothing, since
  `posix_spawn` with `setpgroup` or `setsid` left the group anyway (measured). Teardown finds a
  process that left the group by its sandbox instead (`compile_rules`' `member_mark`,
  `infra.members`).
- One Mach service, the directory lookups (`getpwuid` and the like, read-only); unfiltered,
  `mach-lookup` let a jail read the host's pasteboard, and every other service is a route out
  this compile cannot grade.
- Read on the root directory itself (`dyld` aborts every process without it), which lists the
  names at `/`.
- `/dev`'s null, zero and random devices and the process's own descriptors, nothing else of
  `/dev`: with `file-write-data` on all of it, a jail wrote to the user's terminals. No
  `file-ioctl`.
"""

_FREEZER_FLAG = "--freezer"
"""What the supervisor program is given to start the jail's teardown freezer
(`infra.supervisor.program.FREEZER_FLAG`, repeated: the domain imports no infra): only a
Seatbelt jail's supervisor starts one (decision-0010 item 2)."""

EGRESS_BRIDGE_PORT = 3128
"""Where the supervisor listens, on `127.0.0.1`, for the connections it bridges to the egress
proxy (decision-0009 item 1, decision-0010 item 4)."""


def compile_run(
    command: tuple[str, ...],
    env: Mapping[str, str] = frozendict(),
    *,
    egress_port: int | None = None,
) -> Plan:
    """The plan for running `command`, with `env` as its candidate environment, as the
    supervisor's child (decision-0002). With `egress_port`, the jail's bridge to its egress
    proxy, the proxy variables are set to it whatever the `EnvPolicy` allows
    (`proxy_environment`). A policy is refused before this, by `refusal` and
    `proxy_variable_refusal`."""
    set_env = proxy_environment(egress_port) if egress_port is not None else frozendict()
    return Plan(argv=command, env=frozendict(env), set_env=set_env)


class RuleKind(StrEnum):
    """One compiled Seatbelt profile rule kind."""

    METADATA_LITERAL = "metadata-literal"
    READABLE = "readable"
    WRITABLE = "writable"
    PIN = "pin"
    WRITE_DENY = "write-deny"
    MASK = "mask"
    CHANNEL_UNIX = "channel-unix"
    EGRESS_BRIDGE = "egress-bridge"


@dataclass(frozen=True)
class Rule:
    """One compiled rule, in profile order: `target` is the path or port emitted into the SBPL
    filter, and `source` is the policy or host path it was compiled for."""

    kind: RuleKind
    target: str
    source: str = ""


_RANK = frozendict({"readable": 0, "writable": 1, "pin": 2, "deny": 3, "mask": 4})
"""At one target path, which entry emits last and so wins in SBPL's last-match evaluation: a mask
over a write deny over a pin over a writable root over a readable one."""

_SUBPATH_KINDS: tuple[RuleKind, ...] = (
    RuleKind.READABLE,
    RuleKind.WRITABLE,
    RuleKind.WRITE_DENY,
    RuleKind.MASK,
)
"""The rule kinds that establish read or write permissions over a filesystem subtree."""


def _depth(path: str) -> int:
    return 0 if path == "/" else path.count("/")


def _ancestors(path: str) -> tuple[str, ...]:
    """Every strict ancestor directory of `path` other than `"/"`, shallowest first."""
    parts = path.split("/")
    return tuple("/".join(parts[:depth]) for depth in range(2, len(parts)))


def _governing_role(policy: FsPolicy, path: str) -> str | None:
    """The role of the most specific entry strictly above `path` (at one path, the one that
    emits last), or `None` when no entry covers it: what the jail allows at `path`'s parent."""
    above = [
        (role, root)
        for role, roots in (
            ("readable", policy.readable),
            ("writable", policy.writable),
            ("deny", policy.write_denies),
            ("mask", policy.masks),
        )
        for root in roots
        if root != path and within(path, root)
    ]
    if not above:
        return None
    return max(above, key=lambda entry: (_depth(entry[1]), _RANK[entry[0]]))[0]


def _entries(policy: FsPolicy) -> frozenset[str]:
    return frozenset((*policy.readable, *policy.writable, *policy.write_denies, *policy.masks))


def _between(path: str, roots: tuple[str, ...]) -> tuple[str, ...]:
    """The directories strictly between `path` and each of `roots` it is inside, shallowest
    first."""
    return tuple(
        ancestor
        for ancestor in _ancestors(path)
        if any(ancestor != root and within(ancestor, root) for root in roots)
    )


def pin_candidates(policy: FsPolicy, state_dir: str | None = None) -> tuple[str, ...]:
    """Every path strictly between a writable root and a write deny, a mask, a readable root or
    `state_dir` inside it: where `compile_rules` may pin a directory, so what presentation looks
    up on the host for it."""
    extra = (state_dir,) if state_dir is not None else ()
    return tuple(
        dict.fromkeys(
            ancestor
            for path in (*policy.readable, *policy.write_denies, *policy.masks, *extra)
            for ancestor in _between(path, policy.writable)
        )
    )


def _kind(host: Mapping[str, HostPath], path: str) -> PathKind:
    found = host.get(path)
    return PathKind.ABSENT if found is None else found.kind


def _targets(
    host: Mapping[str, HostPath], links: Mapping[str, tuple[str, ...]], path: str
) -> tuple[str, ...]:
    """Every path `path` needs in the SBPL profile: `path` itself, any symbolic link targets on
    the way (`links`), and its canonical resolved path on the host (`host`)."""
    found = host.get(path)
    steps = (
        path,
        *links.get(path, ()),
        *((found.resolved,) if found is not None else ()),
    )
    return tuple(dict.fromkeys(step for step in steps if step))


def _pins(
    policy: FsPolicy, host: Mapping[str, HostPath], protected: list[tuple[str, bool]]
) -> set[tuple[str, str]]:
    """The directories to pin on the way to each `protected` `(path, made)`, as `("pin", path)`:
    `made` when brig makes the directories missing on the way to `path` before the jail starts
    (an absent deny or mask, its placeholders); never for a readable root or `state_dir`, which
    exist."""
    entries = _entries(policy)
    pins: set[tuple[str, str]] = set()
    for path, made in protected:
        for directory in _between(path, policy.writable):
            kind = _kind(host, directory)
            there = kind is PathKind.DIRECTORY or (made and kind is PathKind.ABSENT)
            if (
                there
                and directory not in entries
                and _governing_role(policy, directory) == "writable"
            ):
                pins.add(("pin", directory))
    return pins


def _kept(policy: FsPolicy, host: Mapping[str, HostPath], state_dir: str) -> list[tuple[str, str]]:
    """The policy's entries that need a rule, as `(role, path)`, and the pins on the way to each
    readable root, deny, mask and `state_dir` among them (`_pins`)."""
    entries = [("readable", p) for p in policy.readable]
    entries += [("writable", p) for p in policy.writable]
    protected = [(path, False) for path in policy.readable]
    if any(within(state_dir, root) for root in policy.writable) and not any(
        other != state_dir and within(state_dir, other) for other in policy.masks
    ):
        protected.append((state_dir, False))
    for role, paths in (("deny", policy.write_denies), ("mask", policy.masks)):
        for path in paths:
            if any(other != path and within(path, other) for other in policy.masks):
                continue
            if role == "deny" and not any(within(path, root) for root in policy.writable):
                continue
            absent = _kind(host, path) is PathKind.ABSENT
            if absent and _governing_role(policy, path) != "writable":
                continue
            entries.append((role, path))
            protected.append((path, absent))
    kept = {*entries, *_pins(policy, host, protected)}
    return sorted(kept, key=lambda entry: (_depth(entry[1]), _RANK[entry[0]], entry[1]))


def _rules_for_entry(policy: FsPolicy, role: str, target: str, source: str) -> tuple[Rule, ...]:
    match role:
        case "readable":
            if source not in policy.writable and _governing_role(policy, source) == "writable":
                return (
                    Rule(RuleKind.READABLE, target, source),
                    Rule(RuleKind.WRITE_DENY, target, source),
                )
            return (Rule(RuleKind.READABLE, target, source),)
        case "writable":
            if target != "/":
                return (
                    Rule(RuleKind.WRITABLE, target, source),
                    Rule(RuleKind.PIN, target, source),
                )
            return (Rule(RuleKind.WRITABLE, target, source),)
        case "pin":
            return (Rule(RuleKind.PIN, target, source),) if target != "/" else ()
        case "deny":
            return (Rule(RuleKind.WRITE_DENY, target, source),)
        case _:
            return (Rule(RuleKind.MASK, target, source),)


def compile_rules(
    policy: FsPolicy,
    host: Mapping[str, HostPath] = frozendict(),
    *,
    state_dir: str,
    supervisor_script: str,
    channels: Reservations | None = None,
    egress_port: int | None = None,
    links: Mapping[str, tuple[str, ...]] = frozendict(),
    member_mark: str | None = None,
) -> tuple[Rule, ...]:
    """Every rule a Seatbelt jail for `policy` needs, in profile order.

    `host` is what presentation found at each policy path, `pin_candidates`, `state_dir`,
    `supervisor_script` and `channels.directory.host_path` (kind and `os.path.realpath`); a path
    it does not name reads as absent and unresolved. `links` is any symbolic-link chain for the
    roots. `refusal` in `domain/policy/paths.py` must have passed first.

    `member_mark`, a file inside `state_dir` made for this jail alone, is allowed
    `file-read-metadata` after the state directory's mask, and nothing else of the state
    directory beside the jail's own files: what lets teardown ask the kernel which processes
    carry this jail's profile, however they left its process group (`infra.members`).
    """
    kept = _kept(policy, host, state_dir)
    expanded = sorted(
        ((role, target, path) for role, path in kept for target in _targets(host, links, path)),
        key=lambda item: (_depth(item[1]), _RANK[item[0]], item[1], item[2]),
    )
    mask_targets = tuple(target for role, target, _ in expanded if role == "mask")
    state_targets = _targets(host, links, state_dir)
    script_targets = _targets(host, links, supervisor_script)
    channel_targets = (
        _targets(host, links, channels.directory.host_path)
        if channels is not None and channels.reservations
        else ()
    )
    root_targets = (
        *(target for role, target, _ in expanded if role in ("readable", "writable")),
        *script_targets,
        *channel_targets,
    )
    ancestors = sorted(
        {
            ancestor
            for target in root_targets
            for ancestor in _ancestors(target)
            if not any(within(ancestor, mask) for mask in mask_targets)
        },
        key=lambda path: (_depth(path), path),
    )
    rules: list[Rule] = [Rule(RuleKind.METADATA_LITERAL, anc, anc) for anc in ancestors]
    for role, target, source in expanded:
        rules.extend(_rules_for_entry(policy, role, target, source))
    for target in state_targets:
        rules.append(Rule(RuleKind.MASK, target, state_dir))
    state_ancestors = sorted(
        {
            ancestor
            for target in (*script_targets, *channel_targets)
            for ancestor in _ancestors(target)
            if any(within(ancestor, st) for st in state_targets)
        },
        key=lambda path: (_depth(path), path),
    )
    for anc in state_ancestors:
        rules.append(Rule(RuleKind.METADATA_LITERAL, anc, state_dir))
    if member_mark is not None:
        rules.append(Rule(RuleKind.METADATA_LITERAL, member_mark, state_dir))
    for target in script_targets:
        rules.append(Rule(RuleKind.READABLE, target, supervisor_script))
    if channels is not None and channels.reservations:
        channel_source = channels.directory.host_path
        for target in channel_targets:
            rules.append(Rule(RuleKind.WRITABLE, target, channel_source))
            if target != "/":
                rules.append(Rule(RuleKind.PIN, target, channel_source))
            rules.append(Rule(RuleKind.CHANNEL_UNIX, target, channel_source))
    if egress_port is not None:
        rules.append(Rule(RuleKind.EGRESS_BRIDGE, str(egress_port), ""))
    return tuple(dict.fromkeys(rules))


def _render_atom(template: Template) -> str:
    """Render one SBPL s-expression from a Python 3.15 template string (`t"..."`, decision-0001
    rule 16), escaping `\\` and `"` inside every interpolated value and rejecting NUL bytes.

    Raises:
        TypeError: `template` is not a `string.templatelib.Template` (e.g. a plain `str`).
        ValueError: an interpolated value contains a NUL byte (`\\x00`).
    """
    if not isinstance(template, Template):
        raise TypeError("_render_atom requires a Template (t-string), not a plain str")
    parts: list[str] = []
    for item in template:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, Interpolation):
            raw = str(item.value)
            if "\x00" in raw:
                raise ValueError("SBPL atom interpolation cannot contain a NUL byte")
            escaped = raw.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(escaped)
    return "".join(parts)


def render_profile(rules: tuple[Rule, ...]) -> str:
    """The complete SBPL profile text for `rules`, in order."""
    lines: list[str] = list(_HEADER_LINES)
    for rule in rules:
        target = rule.target
        match rule.kind:
            case RuleKind.METADATA_LITERAL:
                lines.append(_render_atom(t'(allow file-read-metadata (literal "{target}"))'))
            case RuleKind.READABLE:
                lines.append(_render_atom(t'(allow file-read* (subpath "{target}"))'))
            case RuleKind.WRITABLE:
                lines.append(_render_atom(t'(allow file-read* file-write* (subpath "{target}"))'))
            case RuleKind.PIN:
                lines.append(_render_atom(t'(deny file-write-unlink (literal "{target}"))'))
            case RuleKind.WRITE_DENY:
                lines.append(_render_atom(t'(deny file-write* (subpath "{target}"))'))
            case RuleKind.MASK:
                lines.append(_render_atom(t'(deny file-read* file-write* (subpath "{target}"))'))
            case RuleKind.CHANNEL_UNIX:
                lines.append(
                    _render_atom(t'(allow network-bind network-outbound (subpath "{target}"))')
                )
            case RuleKind.EGRESS_BRIDGE:
                lines.append(
                    _render_atom(
                        t'(allow network-bind network-inbound (local tcp "localhost:{target}"))'
                    )
                )
                lines.append(
                    _render_atom(t'(allow network-outbound (remote tcp "localhost:{target}"))')
                )
    return "\n".join(lines) + "\n"


SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM = Claim(
    name="channel_exclusivity",
    description=(
        "the only paths this jail can write that the host can also reach are the channels it "
        "declared, and Seatbelt refuses every Unix-domain bind and connect outside its own "
        "channel directory whatever roots the policy reads, every signal to a process outside "
        "the jail, and every Mach service but the directory lookups, so it can dial no socket "
        "the host keeps: nothing crosses the boundary anonymously (law 9). A writable root "
        "outside the declared channel directory shares host files and violates it. Stdio is no "
        "shared path: the command's fd 0, 1 and 2 are pipes the host pumps"
    ),
)
"""What the Seatbelt compile claims about the paths, sockets, signals and Mach services it allows
(law 9, decision-0010 item 4)."""

SEATBELT_FS_WRITE_CLAIM = Claim(
    name="fs_write",
    description=(
        "the command writes only inside the policy's writable roots and its declared channels, "
        "and nothing a write deny or a mask names; nor can it remove a writable root or rename a "
        "directory on the way to a write deny, a mask or a readable root inside a writable root "
        "that was there when the jail started. Best-effort while any read-only or denied subpath "
        "(a deny, a mask, a nested readable root, or brig's state directory) sits beneath a "
        "writable root: Seatbelt judges a path, not the file at it, so the host renaming or "
        "linking an entry on the way while the jail runs moves what lies beneath it"
    ),
)

SEATBELT_FS_READ_CLAIM = Claim(
    name="fs_read",
    description=(
        "the command reads only the policy's roots, and nothing a mask names. Best-effort on "
        "Darwin, whatever the policy: the jail lists the names at / and reads the metadata of "
        "every directory on the way to a root (dyld and path lookup need both), reads every host "
        "process's arguments through sysctl, reads the hardware registry (I/O Kit's properties, "
        "the machine's serial number among them), and looks up the host's users and groups; and a "
        "mask matches a path, so a host hard link or rename of a masked file inside a readable "
        "root shows it under another name"
    ),
)

SEATBELT_NETWORK_CLAIM = Claim(
    name="network",
    description=(
        "the command reaches no network: Seatbelt refuses every TCP, UDP and raw socket "
        "operation, every Unix-domain bind and connect outside the jail's own channel "
        "directory, and every Mach service but the directory lookups, so no host service can "
        "carry the network for it"
    ),
)

SEATBELT_NETWORK_EGRESS_CLAIM = Claim(
    name="network",
    description=(
        "the command reaches only the destinations the policy grants, and only through the "
        "proxy: Seatbelt allows TCP only to the supervisor's bridge port on a local address, "
        "where the supervisor bridges each connection to a proxy on the host that decides it and "
        "resolves a granted name itself. Best-effort on Darwin: the jail shares the host's "
        "network stack, and Seatbelt's localhost filter matches every local address, so a host "
        "service listening at the bridge port on any local address (a LAN address, or a "
        "wildcard) is reachable past the proxy, and the command can listen at the bridge port on "
        "the wildcard address, reachable from the network. Not covered: the proxy judges an "
        "HTTP CONNECT's authority, never the TLS SNI inside it, and the bytes inside a granted "
        "connection are not inspected"
    ),
)

SEATBELT_ENV_CLAIM = Claim(
    name="env",
    description="the command's environment is exactly what the environment policy allows",
)


def _beneath_writable(rules: tuple[Rule, ...]) -> bool:
    """Whether any subpath rule that is not writable (a write deny, a mask, a nested readable
    root, or brig's state directory mask) sits where the jail would otherwise see a writable
    subpath: the last subpath rule strictly above its target is `RuleKind.WRITABLE`."""
    for index, rule in enumerate(rules):
        if rule.kind not in (RuleKind.READABLE, RuleKind.WRITE_DENY, RuleKind.MASK):
            continue
        above = [
            earlier
            for earlier in rules[:index]
            if earlier.kind in _SUBPATH_KINDS
            and earlier.target != rule.target
            and within(rule.target, earlier.target)
        ]
        if above and above[-1].kind is RuleKind.WRITABLE:
            return True
    return False


def _governing(rules: tuple[Rule, ...], path: str) -> Rule | None:
    """The last subpath rule at or above `path`: what the profile allows there once every rule
    applied."""
    covering = [rule for rule in rules if rule.kind in _SUBPATH_KINDS and within(path, rule.target)]
    return covering[-1] if covering else None


def _writable_shared_paths(rules: tuple[Rule, ...]) -> tuple[str, ...]:
    """The host paths a jail with `rules` can write: each `RuleKind.WRITABLE` rule still in
    effect at its own target once later rules applied, as its `source`. Distinct, in rule
    order."""
    shared = [
        rule.source
        for rule in rules
        if rule.kind is RuleKind.WRITABLE and _governing(rules, rule.target) == rule
    ]
    return tuple(dict.fromkeys(shared))


def _declared_channel_paths(channels: Reservations | None) -> tuple[str, ...]:
    """The host paths of the channels a jail declared: its channel directory, or nothing.
    What `_writable_shared_paths` is allowed to name under `SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM`."""
    if channels is None or not channels.reservations:
        return ()
    return (channels.directory.host_path,)


def ceilings(
    rules: tuple[Rule, ...],
    channels: Reservations | None,
    *,
    egress: bool = False,
) -> frozendict[Claim, Grade]:
    """The strongest grade each claim can have for a Seatbelt jail compiled to `rules`
    (decision-0008, decision-0010 item 4): what this compile states, before any jail runs. An
    e2e battery holds every one of these to what it measures (`at_most`), so none is stated
    stronger than the batteries show.

    - `fs_write` is `BEST_EFFORT` while any subpath rule that is not writable sits beneath a
      writable one (`_beneath_writable`), else `ENFORCED`: Seatbelt refuses every write outside
      the writable roots in the kernel.
    - `fs_read` is always `BEST_EFFORT`: the header's measured needs (`/`'s names, ancestor
      metadata, `sysctl-read`, the directory lookups) and the hardware registry, which Seatbelt
      lets any process read, show the jail host data no policy names.
    - `network` is `ENFORCED` without `egress` (Seatbelt refuses every network operation outside
      the channel directory), `BEST_EFFORT` with it (`SEATBELT_NETWORK_EGRESS_CLAIM`'s gaps).
    - `channel_exclusivity` is `VIOLATED` when a writable path the jail shares with the host is
      not a declared channel, else `ENFORCED`: unlike a bind mount, Seatbelt refuses a dial of
      a host socket inside a readable root, so a root the jail reads lowers nothing.
    - `env` is `ENFORCED`: the supervisor spawns the command with the allowed environment alone.
    """
    shared = set(_writable_shared_paths(rules)) <= set(_declared_channel_paths(channels))
    exclusivity = Grade.ENFORCED if shared else Grade.VIOLATED
    return frozendict(
        {
            SEATBELT_FS_WRITE_CLAIM: (
                Grade.BEST_EFFORT if _beneath_writable(rules) else Grade.ENFORCED
            ),
            SEATBELT_FS_READ_CLAIM: Grade.BEST_EFFORT,
            SEATBELT_NETWORK_EGRESS_CLAIM if egress else SEATBELT_NETWORK_CLAIM: (
                Grade.BEST_EFFORT if egress else Grade.ENFORCED
            ),
            SEATBELT_ENV_CLAIM: Grade.ENFORCED,
            SEATBELT_CHANNEL_EXCLUSIVITY_CLAIM: exclusivity,
        }
    )


def compile_supervisor_launch(
    supervisor_path: tuple[str, ...], profile_path: str, cwd: str | None = None
) -> tuple[str, ...]:
    """The argv that starts `supervisor_path` as the jail's supervisor under
    `/usr/bin/sandbox-exec -f <profile_path>`, in `cwd` when one is given (`sandbox-exec` has no
    `--chdir` flag, so the supervisor's interpreter changes to `cwd` before running the
    supervisor script, and the command inherits it from the supervisor)."""
    if cwd is None:
        return (_SANDBOX_EXEC, "-f", profile_path, *supervisor_path, _FREEZER_FLAG)
    return (
        _SANDBOX_EXEC,
        "-f",
        profile_path,
        *supervisor_path[:-1],
        "-c",
        _CHDIR_RUNNER,
        cwd,
        supervisor_path[-1],
        _FREEZER_FLAG,
    )
