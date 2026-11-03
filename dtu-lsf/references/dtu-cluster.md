# DTU "dcc" LSF cluster reference

Observed 2026-11-03 (LSF 10.1.0.16, master `lsf10-prod`). Limits change without
notice; confirm a number live with the command next to it before relying on it.

## 1. DTU helper commands (`/lsf/local/bin`)

| Command | Shows |
|---|---|
| `bstat [-u all] [-q Q] [ID]` | Compact job list with elapsed time |
| `bstat -C [ID]` / `-M [ID]` | CPU efficiency / memory (cur, max, avg, LIM = kill threshold) |
| `classstat Q...` | Per queue: total/used/avail slots, pending count |
| `nodestat Q` | Per node: state, free:total procs, load |
| `nodestat -F Q` | + CPU model, memory, features (for `select[...]`) |
| `nodestat -g`/`-G Q` | GPU free:installed (+ model) |
| `nodestat -j`/`-r Q` | Jobs per node / slots reserved for pending jobs |
| `gpustat [-j] Q` | Per GPU: memory, util, temp, owning job |
| `bgstat host`, `bnvtop ID` | GPU allocation on a host / nvtop for a job's GPUs |
| `bqlimits Q`, `bappinfo APP` | Queue limits / application profile params |
| `bgrpuser [user]` | User's LSF groups (queue access, long-job tiers) |

Plain LSF that works: `bjobs [-p3|-psum]`, `bhist -l|-a`, `bpeek`, `bqueues -l`,
`bhosts`, `bmgroup`, `lshosts`, `lsload -gpu`, `blimits -w`, `busers`, `brsvs`, `bsla`.

## 2. What esub.dcc does to every job

- **No `-W`:** 15 min walltime. The most common surprise.
- **Memory:** `rusage[mem=X]` is **per slot**. If only one of rusage/`-M` is set the
  other matches; neither → 1024 MB. `-M` < rusage is raised; `-M` far above rusage is
  rejected. Set only `rusage[mem=...]`. Limit is per job but enforced per host.
- **Multi-core without `span[...]`** → `span[hosts=1]`.
- **GPUs:** ≥ 4 cores per GPU. 1 GPU with fewer cores is raised to 4; else rejected.
- **Walltime tiers** (queues without RUNLIMIT, e.g. `hpc`) pick an app profile, which
  decides the host pool: parallel `shortparallel` ≤ 8 h, `parallel` ≤ 72 h,
  `longparallel` ≤ 14 d (group `userlongparallelhpc`); serial `serial` ≤ 5 d,
  `longserial` ≤ 18 d (`userlongserialhpc`); longer is rejected. 9 h instead of 8 h
  shrinks the pool.
- **Rejected in user `-R`:** `same[]`, `cu[]`, `order[]`, additive compound,
  `span[hosts=-1]`, `span[stripe]`.
- Missing `-o` is added; missing job name → `NONAME`, spaces → `_`.
- **`bmod` is disabled for users.** Changing a pending job = kill + resubmit (consent).
- No environment inheritance: use `bsub -env "all"` (or a list).
- `JOB_STARTER: /bin/bash -l -c`; default queue `hpc`.

## 3. Queues and limits

Check with `bqueues -l Q`, `bqlimits Q`, `blimits -w`.

- All general queues: FAIRSHARE + BACKFILL. Priority drops with recent (GPU) run time
  and recovers (`HIST_HOURS` ≈ 96 h on gpua100). Short, accurate walltimes backfill.
- **`hpc`:** TASKLIMIT 128 cores/job; per user 192 slots and ~1.3 TB memory in use
  (`hpc_default_slot_limit`). CPUs: XeonE5_2650v4, XeonGold6226R, XeonGold6342,
  EPYC9554, XeonPlatinum8462Y (`nodestat -F hpc`).
- **GPU queues** (default walltime 15 min):

  | Queue | GPUs | Max walltime |
  |---|---|---|
  | `gpuv100` | V100 16/32 GB, some NVLink; 96 slots/user | 24 h |
  | `gpua100` | A100 40/80 GB | 72 h |
  | `gpul40s` | L40s 48 GB | 48 h |
  | `gpua10` / `gpua40` | A10 / A40 | 24 h |
  | `gpuh100` | H100, Hopper user groups only | 24 h |

- **Group queues** (`man`, `fotonano`, `steno`, `stenotest`, `elektro`, `cfu`, `chec`,
  `qimalma94`, ...): access by group (`bgrpuser`). Some own the only nodes of a CPU
  model (XeonGold6342 outside `hpc`'s `rhpcice` → `stenotest`/`fotonano`).
- **User s250250 (QIM)** can use `hpc`, `hpcint`, `milan`, `compute`, the GPU and
  interactive GPU queues, `qimalma94` (2 × 24-core XeonE5_2650v4, ≤ 240 h, "max 2 jobs
  per user" in its description), `c47511`. Per-user caps often live in the queue
  description or `blimits`, not `JL/U`.
- **Host groups:** `HOSTS: rhpc5/+200 ...` (`+N` = preference). Expand with
  `bmgroup -w G` (may nest); `bhosts G` works. `-m G` restricts to those hosts.
- **Drains:** ~100+ hosts may be `closed_Adm` at any time with no LSF comment (seen
  2026-11-03: 123 of 397). Running jobs continue. Reason: §9 status messages.

## 4. GPU requests

```
#BSUB -q gpua100
#BSUB -gpu "num=1:mode=exclusive_process"
#BSUB -n 4                        # ≥ 4 cores per GPU
#BSUB -R "span[hosts=1]"
#BSUB -R "rusage[mem=8GB]"        # system RAM per core
```
- Always `exclusive_process`: shared mode lets others onto the GPU, and their OOM kills
  your job.
- Size: `select[gpu32gb]` (V100 32 GB), `select[gpu80gb]`/`[gpu40gb]` (A100),
  `select[sxm2]` (NVLink V100); see `lshosts -w host`.
- MPS: `-gpu "num=1:mode=exclusive_process:mps=yes"`.

## 5. Interactive nodes

`linuxsh` (CPU, queue `hpcint`), `voltash`/`sxm2sh` (V100), `a100sh` (`gpua100i`),
`h100sh` (`gpuh100i`) submit `bsub -Is`; inside one `LSF_QRSH=true` and nesting is
refused. Interactive GPU nodes are shared (all users see all GPUs). Login nodes
`login1`/`login2.hpc.dtu.dk`: no heavy work.

## 6. Pending reasons (`bjobs -p3 ID` for the per-host breakdown)

| Reason (abridged) | Meaning |
|---|---|
| No suitable hosts | Read `-p3`: "Not specified in job submission" = excluded by `-m`; "Closed by LSF administrator" = drained; "resource requirements not satisfied" = select/mem/span too strict |
| Closed by LSF administrator | Host `closed_Adm`; wait or widen (kill + resubmit) |
| Job slot / user limit reached, per-user job slot limit of the queue | Per-user (`blimits -w`, `busers`) or queue `JL/U`; waits for own jobs |
| Not enough job slots / processors | Busy; see timeline |
| Reserving resource (mem) not satisfied | mem/slot × slots doesn't fit a free host now |
| Not enough GPUs | Matching GPUs busy or spec too narrow |
| Dependency condition not satisfied | Check the `-w` parent |
| Ineligible pending time | Time not yet eligible (dependency, limits) |
| PSUSP | `bstop`ped while pending; `bresume` only with consent |

## 7. bjobs output fields

`bjobs -o "<fields>" [-json]`; valid here: `jobid jobindex stat queue user job_name
pend_reason pend_time runtimelimit run_time time_left nreq_slot nalloc_slot memlimit
max_mem mem cpu_used combined_resreq effective_resreq gpu_num exit_code exit_reason
first_host exec_host submit_time start_time estimated_start_time`. Not valid:
`eligible_pend_time`, `asked_hosts` (see "Specified Hosts" in `bjobs -l`). JSON key
`JOB_NAME`; times are `HH:MM:SS`. `LSB_BJOBS_FORMAT` may alter plain `bjobs`, so
pass `-o` when parsing.

## 8. Not visible to users

- Other users' jobs: summary only (`bjobs -u all -o ...`); `bjobs -l` says "not found"
  (`SECURE_JOB_INFO_LEVEL=3`).
- `bacct`, `badmin hhist`, admin close comments: denied/hidden (use §9).
- `showstart`: only ~25 jobs cluster-wide get an estimate; `-` means unknown.

## 9. Status messages and docs

Admin announcements (outages, closed queues, reboots, service windows) are files shown
as the `linuxsh` banner; `cat` them directly:

```bash
cat /apps9/dcc/etc/motd.breaking                      # current
ls -t /apps9/dcc/etc/motd.breaking.pre* | head -1     # previous version
ls -t /apps9/dcc/etc/motd.service_window.* | head -1  # planned windows
```

Each edit archives the old file as `.pre<YYYYMMDD>`, and admins delete updates that
still matter (2026-11-03: the Nov 2 "kernel rollout, nodes rebooting" notice behind
the `closed_Adm` hosts survived only in the archive), so read the previous version
too. The report script does this automatically. Only interactive TTY shells print the
banner. Not in /etc/motd, the SSH banner, ~/Maildir, or the hpc.dtu.dk front page.
`~/.service_window.<date>` is just an acknowledgement marker.

Docs (hpc.dtu.dk `?page_id=`): batch jobs 1416, managing jobs 1519, efficiency 4204,
arrays 1434, GPUs 2759, cores per GPU 4976. Support: support@hpc.dtu.dk.
