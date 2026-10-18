---
id: DRAFT-0004
title: >-
  Confirm bwrap's --unshare-all works unprivileged on GitHub's ubuntu-latest
  runner
status: Draft
assignee: []
created_date: '2026-10-17 21:53'
updated_date: '2026-10-18 01:22'
labels:
  - brig
  - ci
dependencies: []
documentation:
  - .github/workflows/ci.yml
parent_task_id: TASK-0001
type: spike
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

TASK-0001.03's adversarial review raised an open question about its own e2e test (`tests/e2e/test_bwrap_journey.py`) that could not be settled on a macOS development host (no bwrap, no Docker daemon, no Linux VM): bwrap's `--unshare-all` needs unprivileged user namespaces, and Ubuntu 24.04 ships an AppArmor profile that restricts them by default (`kernel.apparmor_restrict_unprivileged_userns_clone`-style confinement) -- a change that broke a number of CI pipelines when 24.04 became `ubuntu-latest` on GitHub-hosted runners in 2024.

`.github/workflows/ci.yml` installs bubblewrap on `ubuntu-latest` and runs `just done` with no special AppArmor/sysctl step. Whether the walking skeleton's e2e test (and every later bwrap e2e test) actually passes on its first real CI run, rather than failing with a permissions error on `--unshare-all` unrelated to anything brig's own code does, depends entirely on whether GitHub's runner image already relaxed that restriction (their `runner-images` project is known to have patched exactly this for several popular sandboxing tools) or whether the workflow needs an explicit step.

## What finishes this

- [ ] Push this repository (or a throwaway branch) so CI actually runs once, and read whether `tests/e2e/test_bwrap_journey.py` passes or fails on `--unshare-all` specifically.
- [ ] If it fails for that reason, decide and add the minimal CI fix (e.g. `sudo sysctl kernel.apparmor_restrict_unprivileged_userns=0`, or an AppArmor profile permitting bwrap) to `.github/workflows/ci.yml`.
- [ ] If it passes, note that here so nobody re-opens this question.

## Notes

Nothing has been pushed to a real git remote yet as of TASK-0001.03 (explicitly out of scope for that task -- a separate decision for the repo owner), so this is genuinely unverified, not just unverified-by-TASK-0001.03.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
### 2026-10-17 — Docker probe on the macOS dev host (partial answer; read the scope limit first)

**Scope limit, stated up front: this did NOT test the mechanism this spike is about.** Docker
Desktop's VM kernel here is `6.12.76-linuxkit`, which has no AppArmor LSM compiled in at all
(`/sys/module/apparmor` absent, no `kernel.apparmor_restrict_unprivileged_userns` in `sysctl -a`).
Ubuntu 24.04's restriction lives in an Ubuntu-patched kernel's AppArmor LSM, so no container flag
on this host — `--security-opt apparmor=unconfined` included, which is a no-op against a kernel
without AppArmor — can reproduce or refute it. Nobody should read the Docker result below as
"we tested CI and it's fine." The only verification that settles this spike is still an actual push.

#### Measured in a container (`ubuntu:24.04`, `--platform=linux/arm64`, bubblewrap 0.9.0)

brig's exact compiled argv, run as the raw CLI:
`bwrap --ro-bind / / --unshare-all --die-with-parent --new-session -- true`

| Docker flags | exit | output |
|---|---|---|
| (default) | 1 | `bwrap: No permissions to create new namespace, likely because the kernel does not allow non-privileged user namespaces.` |
| `--security-opt apparmor=unconfined` | 1 | same denial (expected: no AppArmor in this kernel) |
| `--cap-add=SYS_ADMIN` | 1 | `bwrap: pivot_root: Operation not permitted` |
| `--security-opt seccomp=unconfined` | **0** | — |
| `--privileged` | 0 | — |
| `--security-opt seccomp=unconfined --user 65534` | **0** | — |
| `--security-opt seccomp=unconfined --cap-drop=ALL --user 65534` | **0** | — |

**`--security-opt seccomp=unconfined` is necessary and sufficient.** Minimality is established in
both directions: it works with *zero* capabilities as an unprivileged uid (65534), and
`--cap-add=SYS_ADMIN` alone does not fix it — it only moves the failure from `unshare` to
`pivot_root`, both of which Docker's default seccomp profile blocks. So capabilities are not the
blocker and `--privileged` is overkill. (`seccomp=unconfined --cap-drop=ALL` as *uid 0* fails at
`setting up uid map` — an artifact of root needing CAP_SETUID in the parent namespace to write a
full uid_map; irrelevant to CI, which runs as the unprivileged `runner` user.)

Two further points, one measured and one inferred from it:

- **Measured: `/usr/bin/bwrap` is `-rwxr-xr-x`, not setuid.** (Corroborated by
  `50-bubblewrap.conf`'s own comment, which tells an administrator who disables userns to
  "use dpkg-statoverride to make /usr/bin/bwrap setuid root" — i.e. it is not, as shipped.)
- **Inferred from that: `--unshare-all` is not the load-bearing part, so narrowing it is not an
  escape hatch.** A non-setuid bwrap has no privileged route to any namespace, so it needs an
  unprivileged user namespace whatever flags it is given; the dependency is on bwrap itself, not
  on this flag, and any later filesystem-policy slice inherits the same constraint. Supporting but
  *not* conclusive observation: `bwrap --ro-bind / / -- true`, with no `--unshare-*` at all, fails
  identically in the default container — though that was Docker's seccomp filter, and the probe
  did not isolate which clone flag was refused, so it does not by itself prove `CLONE_NEWUSER` is
  what bwrap always requests.

#### Measured from Ubuntu 24.04's own packages (in-container, so: how Ubuntu ships it)

- The `apparmor` package ships `/usr/lib/sysctl.d/10-apparmor.conf` containing
  `kernel.apparmor_restrict_unprivileged_userns = 1`. Its own comment states the semantics:
  *"Allows to restrict the use of unprivileged user namespaces to applications which have an
  AppArmor profile loaded which specifies the userns permission. All other applications (whether
  confined by AppArmor or not) will be denied the use of unprivileged user namespaces."*
  So the restriction is **on by default on Ubuntu 24.04**, and it is deny-by-default for any
  binary without a `userns`-granting profile.
- `/etc/apparmor.d/` ships ~90 stub profiles granting `userns` to sandboxing and browser binaries
  (`flatpak`, `podman`, `runc`, `crun`, `lxc-*`, `chrome`, `firefox`, `linux-sandbox`, `ch-run`,
  `mmdebstrap`, `vdens`, …). **There is no stub profile for `/usr/bin/bwrap`** —
  `grep -rn bwrap /etc/apparmor.d/` finds nothing.
- The `bubblewrap` package *does* ship a sysctl file, `/usr/lib/sysctl.d/50-bubblewrap.conf`, and
  its postinst applies it — but it sets `kernel.unprivileged_userns_clone=1`, the **Debian**
  old-kernel knob, not Ubuntu's AppArmor knob. Installing bubblewrap therefore does **not**
  relax the 24.04 restriction. (This was the most plausible "it just works" theory; it is wrong.)
- The profile that *would* permit it, `bwrap-userns-restrict`, lives in a **separate, not-installed
  package** (`apparmor-profiles`) at `/usr/share/apparmor/extra-profiles/bwrap-userns-restrict`,
  and its header says it is **"disabled by default … use aa-enforce to enable it"**. It grants
  bwrap `userns`, `mount`, `umount`, `pivot_root` and `capability`, while stacking bwrap's children
  into a subprofile with no capabilities.

#### Found by research, not measured (primary sources, `actions/runner-images`)

- `ubuntu-latest` still maps to **Ubuntu 24.04** as of today (2026-10-17); `ubuntu-26.04` exists
  only as an explicit label, with the `-latest` migration still pending. So `.github/workflows/ci.yml`
  gets the 24.04 restriction, not a hypothetical later default.
- **Issue #10015 ("apparmor should be disabled by default on Ubuntu")** — closed. GitHub's own
  answer: *"After careful security review and due to security reasons (risks) we do not plan to
  disable it. Also these runners are ephemeral VMs and workflows already have root, so can disable
  AppArmor themselves."* This is a deliberate, stated policy, not an oversight awaiting a fix.
- **Issue #10443 ("ubuntu-24.04 Error during unshare(...): Operation not permitted")** — same
  failure class from skopeo. The accepted workaround in-thread is exactly
  `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`.
- **PR #11489 ("[Ubuntu] Disable apparmor user namespace restrictions")**, which would have set
  that sysctl at image-build time, was **CLOSED unmerged** (2025-01-28).
- The image build does nothing to relax it either. `images/ubuntu/scripts/build/configure-environment.sh`
  is the only place the Ubuntu image writes sysctls, and it writes exactly four — `vm.max_map_count`,
  `fs.inotify.max_user_watches`, `fs.inotify.max_user_instances`, `vm.mmap_rnd_bits` — none
  AppArmor-related. A code search of the repo for `apparmor` returns 0 hits; that zero is
  trustworthy because the same search for `sysctl` returns 2 (both `configure-environment.sh`),
  so the index does cover these build scripts.

#### Answer to the spike's question

**Inference, clearly labelled as such — not a measurement.** No step of the chain was observed on a
real runner; each link is independently sourced, which is why the conclusion is stated with
confidence but not as fact:

1. Ubuntu 24.04 ships the restriction on (measured in-package).
2. It denies userns to any binary without a `userns`-granting AppArmor profile (the package's own
   documented semantics).
3. bwrap has no such profile, and the enabling one ships disabled in an uninstalled package (both
   measured); bwrap cannot avoid userns because it is not setuid (measured that it is not; the
   "therefore needs userns" step is inference).
4. GitHub keeps AppArmor enabled by stated policy, rejected the PR that would have set the sysctl,
   and its image build touches neither (primary sources).

⇒ **`--unshare-all` is very likely to FAIL on `ubuntu-latest` as the workflow stands**, with
`bwrap: No permissions to create new namespace…` — a failure attributable to the host's LSM, not to
anything in brig. `tests/e2e/test_bwrap_journey.py` should be expected to fail on its first real CI
run unless the workflow gains a step.

**The genuinely unknown part:** whether GitHub's *built image* diverges from upstream Ubuntu's
default in some way not visible in the repo or the issue tracker (a provisioning step outside the
searched paths, a base-image difference, a change since those issues closed). That residue is why
this spike's acceptance criterion — push once and read the result — still stands. Nothing above
substitutes for it.

#### Recommendation (not applied — this was investigation; one line of CI config, for the owner to take or leave)

Add one step to `.github/workflows/ci.yml` before `uv run just done`:

```yaml
      - name: Permit unprivileged user namespaces (Ubuntu 24.04 AppArmor)
        run: sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0 || true
```

Notes on the shape of it:

- `sudo` is passwordless on GitHub-hosted runners, so this needs no secret or extra setup.
- The `|| true` guard matters: writing that sysctl **fails** on any kernel without the Ubuntu
  AppArmor patch, so the unguarded form would break the job on a future `ubuntu-latest`, on
  `ubuntu-*-arm`, or on a non-Ubuntu runner. Guarded, it is correct whether or not the restriction
  is present — which is also why it is safe to add *before* the push that confirms the diagnosis,
  rather than after.
- **Why this rather than the surgical `apparmor-profiles` + `aa-enforce bwrap` profile:** only that
  it is smaller — one line, no package install, and it is the workaround runner-images #10443
  documents. The alternative needs `apt-get install apparmor-profiles` plus
  `aa-enforce /usr/share/apparmor/extra-profiles/bwrap-userns-restrict`, for no benefit brig can
  currently use. Note what neither option does: **setting this sysctl to 0 does not take AppArmor
  out of the picture.** AppArmor stays loaded, and `/etc/apparmor.d/unprivileged_userns` — the
  profile unconfined processes transition into on creating a userns, which carries
  `audit deny capability` — still applies. So if a future battery needs to attribute a denial to
  bwrap rather than to the host LSM, that is an open problem under *either* choice, and this
  recommendation does not address it.
- No new task filed: this is one line of CI config, and the spike's own remaining criterion (push,
  observe) already covers confirming it.

Fix applied, 2026-10-18: .github/workflows/ci.yml now runs 'sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0 || true' after installing bubblewrap, per this draft's investigation. Owner approved applying it now (before the push decision) since it's a single guarded line with no downside on a kernel that lacks the Ubuntu patch. Residual open items from the investigation, NOT addressed by this fix: (1) the AppArmor unprivileged_userns transition profile still denies capabilities inside the new namespace independently of bwrap's own policy, so a future battery cannot yet attribute a denial to bwrap vs the host LSM -- a separate spike if a battery ever needs that; (2) re-verify this step when ubuntu-latest migrates off 24.04 to 26.04, rather than assuming it carries forward; (3) confirmed Docker is NOT used by brig's e2e tests (bwrap runs directly on the runner's kernel), so the Docker-container seccomp finding in this draft is not load-bearing for CI. This draft's own push-and-read criterion still stands -- this fix is informed prediction, not a verified CI pass.
<!-- SECTION:NOTES:END -->
