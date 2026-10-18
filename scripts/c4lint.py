#!/usr/bin/env python3
"""c4lint — enforces orthodox C4 rules that LikeC4 deliberately does not.

Vendored from the c4-architecture knowhere plugin (likec4-diagrams skill,
v0.3.0) so CI can run it without the plugin installed. Re-sync by copying the
plugin's tools/c4lint.py over this file when the plugin version changes.

Usage:
  python3 c4lint.py <project-dir>   (runs `npx likec4 export json` itself)
  python3 c4lint.py <dump.json>     (pre-exported model)

Exit codes: 0 = clean (warnings allowed), 1 = errors found, 2 = tool failure.
Python 3.9+, stdlib only. (Node is still required at runtime because the
model export comes from the `likec4` npm CLI.)
"""

import json
import os
import re
import subprocess
import sys
import tempfile

CONTAINER_KINDS = {"container", "webapp", "mobileApp", "database", "queue", "blobStore"}
SYSTEM_KINDS = {"softwareSystem", "externalSystem"}
# Ordered for the error message (canonical listing); membership via the set.
ALLOWED_KINDS_ORDERED = [
    "person", "component", "container", "webapp", "mobileApp",
    "database", "queue", "blobStore", "softwareSystem", "externalSystem",
]
ALLOWED_KINDS = set(ALLOWED_KINDS_ORDERED)
VAGUE_TITLES = {
    "uses", "use", "calls", "call", "depends on",
    "interacts with", "talks to", "connects to",
}

errors: list[str] = []
warnings: list[str] = []
ctx = ""  # project prefix, set per-project in multi-project workspaces


def err(loc: str, msg: str) -> None:
    errors.append(f"{ctx}{loc}: {msg}")


def warn(loc: str, msg: str) -> None:
    warnings.append(f"{ctx}{loc}: {msg}")


# ---------- load model -------------------------------------------------------
target = sys.argv[1] if len(sys.argv) > 1 else "."
dump_path = target
tmp_path = None

try:
    if os.path.isdir(target):
        fd, tmp_path = tempfile.mkstemp(prefix="c4lint-", suffix=".json")
        os.close(fd)
        proc = subprocess.run(
            f'npx -y likec4 export json -o "{tmp_path}"',
            shell=True, cwd=target, capture_output=True, text=True,
        )
        if proc.returncode != 0 and not os.path.getsize(tmp_path):
            raise RuntimeError(proc.stderr.strip()[-2000:])
        dump_path = tmp_path
except Exception as e:  # noqa: BLE001 — tool boundary, report and exit
    print(
        "c4lint: failed to export model JSON — run `npx likec4 validate` first.\n" + str(e),
        file=sys.stderr,
    )
    sys.exit(2)

if not os.path.exists(dump_path):
    print(f"c4lint: no such file: {dump_path}", file=sys.stderr)
    sys.exit(2)

with open(dump_path, encoding="utf-8") as f:
    parsed = json.load(f)
if tmp_path:
    os.unlink(tmp_path)

# `likec4 export json` returns a single model object for one project, but an
# ARRAY for a workspace — and it repeats the SAME project more than once in
# that array. Dedupe by projectId so each distinct project is linted once
# (genuinely-separate nested projects have different projectIds and are kept).
raw_projects = parsed if isinstance(parsed, list) else [parsed]
seen: set[str] = set()
projects = []
for p in raw_projects:
    key = p.get("projectId") or p.get("project") or json.dumps(sorted((p.get("elements") or {}).keys()))
    if key in seen:
        continue
    seen.add(key)
    projects.append(p)
multi = len(projects) > 1

# Reassigned per project; helpers close over the current values.
elements: dict = {}
total_elements = total_rels = total_views = 0


def text(v) -> str:
    if isinstance(v, dict):
        return v.get("txt") or v.get("md") or ""
    return v or ""


def parent_fqn(fqn: str):
    return fqn[: fqn.rindex(".")] if "." in fqn else None


def kind_of(fqn):
    el = elements.get(fqn)
    return el.get("kind") if el else None


def level_of(kind) -> int:
    if kind == "person" or kind in SYSTEM_KINDS:
        return 1
    if kind in CONTAINER_KINDS:
        return 2
    if kind == "component":
        return 3
    return 0


def container_of(fqn: str) -> str:
    """Nearest ancestor (or self) that is a process boundary."""
    f = fqn
    while f:
        k = kind_of(f)
        if k in CONTAINER_KINDS or k in SYSTEM_KINDS or k == "person":
            return f
        f = parent_fqn(f)
    return fqn


for proj in projects:
    elements = proj.get("elements") or {}
    relations = proj.get("relations") or proj.get("relationships") or {}
    views = proj.get("views") or {}
    ctx = f"[{proj.get('projectId') or proj.get('project') or '?'}] " if multi else ""

    # ---------- 1. element rules ----------
    for fqn, el in elements.items():
        kind = el.get("kind")
        p = parent_fqn(fqn)
        pk = kind_of(p) if p else None

        if kind not in ALLOWED_KINDS:
            err(fqn, f"kind '{kind}' is not a canonical C4 kind (allowed: {', '.join(ALLOWED_KINDS_ORDERED)})")
            continue  # containment checks would be noise
        if (kind == "person" or kind in SYSTEM_KINDS) and p:
            err(fqn, f"'{kind}' must be top-level, but is nested inside '{p}' ({pk})")
        if pk == "externalSystem":
            err(fqn, f"nested inside external system '{p}' — external systems are black boxes and must have no children")
        if kind in CONTAINER_KINDS and pk != "softwareSystem":
            if p:
                err(fqn, f"container-kind '{kind}' must sit directly inside a softwareSystem, not inside '{p}' ({pk})")
            else:
                err(fqn, f"container-kind '{kind}' is top-level — containers live inside a softwareSystem")
        if kind == "component":
            if not p:
                err(fqn, "component is top-level — components live inside a container")
            elif pk == "component":
                err(fqn, f"component nested in component '{p}' — model the inner one as code (i.e. don't) or flatten")
            elif pk not in CONTAINER_KINDS:
                err(fqn, f"component must sit inside a container-kind, not '{p}' ({pk})")
        if not text(el.get("description")) and not text(el.get("summary")):
            err(fqn, 'missing description — every element needs an "at a glance" responsibility')
        if (kind in CONTAINER_KINDS or kind == "component") and not el.get("technology"):
            what = "component" if kind == "component" else "container"
            err(fqn, f"missing technology — every {what} states its technology")

    # ---------- 2. relationship rules ----------
    rels = relations if isinstance(relations, list) else list(relations.values())
    for r in rels:
        if not r:
            continue
        src = (r.get("source") or {}).get("model") if isinstance(r.get("source"), dict) else r.get("source")
        tgt = (r.get("target") or {}).get("model") if isinstance(r.get("target"), dict) else r.get("target")
        loc = f"{src} -> {tgt}"
        title = (r.get("title") or "").strip()

        if not title:
            err(loc, "relationship has no title — label every line with its intent")
        elif title.lower() in VAGUE_TITLES:
            warn(loc, f"vague title '{title}' — use an intent-revealing verb phrase (what does it use it FOR?)")

        sk, tk = kind_of(src), kind_of(tgt)
        # Technology/protocol is a CONTAINER-level requirement: needed when a
        # concrete process (container/component) calls out across a boundary.
        # System→system (context-level) and person→container (UI) edges don't.
        inter_process = level_of(sk) >= 2 and tk and tk != "person" and container_of(src) != container_of(tgt)
        if inter_process and not r.get("technology"):
            err(loc, "inter-process relationship without technology/protocol (e.g. JSON/HTTPS, JDBC, SMTP)")

        # Black-box boundary (orthodox C4 + federation hinge): never reach INTO
        # a different software system's internals. System→system is fine; a
        # person using a container is fine.
        stop_, ttop = str(src).split(".")[0], str(tgt).split(".")[0]
        if stop_ != ttop and kind_of(ttop) == "softwareSystem" and tgt != ttop and sk != "person":
            err(loc, f"reaches into another software system's internals ('{tgt}') — reference the system '{ttop}' as a black box (system→system); this is required for orthodox C4 and for splitting '{ttop}' into its own project later")

    # ---------- 3. view rules ----------
    for vid, v in views.items():
        loc = f"view '{vid}'"
        if not v.get("title"):
            err(loc, "missing title — every diagram states its type and scope")

        nodes = [n for n in (v.get("nodes") or []) if n.get("modelRef") and n["modelRef"] in elements]
        leaves = [n for n in nodes if not n.get("children")]
        root = v.get("viewOf")
        vtype = v.get("_type") or v.get("__")
        if vtype == "deployment":
            continue

        def inside(fqn: str) -> bool:
            return bool(root) and (fqn == root or fqn.startswith(root + "."))

        internal_levels = {
            level_of(kind_of(n["modelRef"]))
            for n in leaves
            if (inside(n["modelRef"]) if root else True)
        }

        if vtype == "dynamic":
            if 2 in internal_levels and 3 in internal_levels:
                err(loc, "dynamic view mixes containers and components — keep every scenario at one abstraction level")
            continue

        # internals of a scoped view sit at ONE level; unscoped views show only top-level elements
        in_lvls = [l for l in internal_levels if l > 0]
        if root:
            root_lvl = level_of(kind_of(root))
            child_lvls = sorted(l for l in in_lvls if l > root_lvl)
            if len(child_lvls) > 1:
                err(loc, f"mixes abstraction levels inside '{root}' (levels {' & '.join(map(str, child_lvls))}: 1=system 2=container 3=component) — one zoom level per diagram; drill down with a separate view + navigateTo")
        elif any(l > 1 for l in in_lvls):
            err(loc, "unscoped view shows containers/components — landscape and context views show only people and systems")

        # neighbors: foreign components leaking into another element's view
        for n in leaves:
            if root and not inside(n["modelRef"]) and kind_of(n["modelRef"]) == "component":
                err(loc, f"shows component '{n['modelRef']}' from outside '{root}' — relate to its container instead (component diagrams scope ONE container)")

    total_elements += len(elements)
    total_rels += len(rels)
    total_views += len(views)

ctx = ""

# ---------- 4. house style (text-level, source files) ------------------------
# Explicit-reference style: no `it`/`this`, no sourceless `-> x`. Syntactic
# property of the .c4 SOURCE (the exported model has resolved these away).
if os.path.isdir(target):
    IT_THIS_SRC = re.compile(r"(^|[^.\w])(it|this)\s*->")
    IT_THIS_TGT = re.compile(r"->\s*(it|this)\b")
    SOURCELESS = re.compile(r"^\s*->\s*\S")
    STRIP = [
        (re.compile(r"//.*$"), ""),
        (re.compile(r"'[^']*'"), ""),
        (re.compile(r'"[^"]*"'), ""),
    ]
    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [d for d in dirnames if d != "node_modules" and not d.startswith(".")]
        for fn in filenames:
            if not (fn.endswith(".c4") or fn.endswith(".likec4")):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                continue
            rel = os.path.relpath(path, target)
            for i, raw in enumerate(content.split("\n"), start=1):
                line = raw
                for rx, repl in STRIP:
                    line = rx.sub(repl, line)
                if IT_THIS_SRC.search(line) or IT_THIS_TGT.search(line):
                    warn(f"{rel}:{i}", "uses 'it'/'this' in a relationship — house style is explicit element names")
                if SOURCELESS.match(line):
                    warn(f"{rel}:{i}", "sourceless relationship '-> x' — house style names both endpoints explicitly")

# If the export yielded no model at all, that's a tool-level problem, not a clean pass.
if total_elements == 0 and total_views == 0:
    print(
        "c4lint: model export contained no elements or views — check the project parses and `npx likec4 validate` passes.",
        file=sys.stderr,
    )
    sys.exit(2)

# ---------- report ------------------------------------------------------------
for w in warnings:
    print(f"WARN  {w}")
for e in errors:
    print(f"ERROR {e}")
scope = f" ({len(projects)} projects)" if multi else ""
print(f"\nc4lint: {len(errors)} error(s), {len(warnings)} warning(s) across {total_elements} elements, {total_rels} relationships, {total_views} views{scope}")
sys.exit(1 if errors else 0)
