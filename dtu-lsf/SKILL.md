---
name: dtu-lsf
description: DTU HPC LSF cluster ("dcc", hpc.dtu.dk, nodes n-62-*). Use for any question about the user's cluster jobs, even without the word "LSF": why a job is pending, when it will start or finish, bjobs/bsub/bhist/bstat output, writing #BSUB scripts, queues (hpc, gpua100, gpuv100, ...), GPU/memory requests, arrays, failed jobs (TERM_RUNLIMIT, TERM_MEMLIMIT), closed hosts, outages, cluster load. Never cancels or alters jobs without explicit consent.
---

# DTU LSF cluster

LSF 10.1, cluster `dcc`. DTU adds helper commands and a submit filter (`esub.dcc`)
that silently rewrites jobs. Read `references/dtu-cluster.md` for limits, queues, GPUs,
memory rules, esub behaviour, or an unfamiliar pending reason.

You are usually on a cluster node. Query commands are safe; run them before answering,
since cluster state changes hourly and generic LSF knowledge is often wrong here.

## Hard rule: consent before changing any job

Never run `bkill`, `bstop`, `bresume`, `brequeue`, `bswitch`, `bmod`, `btop`/`bbot`,
`bchkpnt`, `bmig` (or a script calling them) unless the user agreed, in this
conversation, to that action on those job IDs. A killed job loses its compute time,
results and queue position; a pending one may have waited days for fairshare. "Fix my
job" is not consent. To propose it: say why, show the exact command and what it hits
(`bkill 29874847` = all 27 array elements), wait for a yes. Prefer the narrowest form
(`bkill 'ID[3]'`, never `-J`/`0`). `bsub` is fine when asked; a resubmit that replaces
a job needing a kill is part of the same consent.

**Your own session may be a job** (`linuxsh`, `qrsh`, `a100sh`, ..., sometimes without
`LSB_JOBID`). Match `bjobs -o "jobid queue job_name exec_host"` against `hostname`;
never include it in a cancellation, and point it out on "kill all my jobs".

## Why is my job not running?

Run the read-only report first (< 1 s):

```bash
python3 <skill dir>/scripts/lsf_job_report.py <jobid>     # or 'ID[3]'
```

It prints the effective request (after esub), pending reasons with per-host breakdown,
hosts matching the job's `select[]`/`-m` and their status, a slot-release timeline from
running jobs' walltimes, the user's fairshare rank, and, if matching hosts are
`closed_Adm`, the admins' status message including lines recently removed from it.

Then explain the cause and what would change it:

- **Matching hosts `closed_Adm`:** drained by admins; the report's status message
  usually says why. Options: wait, or widen `-m`/`model ==` (kill + resubmit, needs
  consent); check a relaxed request with `bhosts -w -R "select[...]"`. Suggest
  support@hpc.dtu.dk if it lasts days.
- **No host can ever satisfy it** (mem/core × cores > any host, `span[hosts=1]` with too
  many cores, nonexistent GPU spec): it will never start; say so.
- **Hosts match but are full:** normal queueing; estimate as below.
- **Per-user limit:** own running jobs block it (`blimits -w`, `busers`).
- **Dependency (`-w`):** check the parent with `bjobs -a`/`bhist`; a failed parent may
  block it forever.
- **Low fairshare:** heavy recent use; recovers over a few days.

Also check how it was submitted (`bjobs -l`: CWD, relative `-o` paths, `-env`). Jobs
don't inherit exported variables. For alternatives, list usable queues with
`bqueues -u $USER` and read each one's description and limits (`bqueues -l Q`). On
`hpc`, walltime ≤ 8 h gets a larger host pool (reference §2): flag padded walltimes.

## When will it start?

`showstart`/`estimated_start_time` are almost always `-` here; don't present that.
Estimate from evidence:
1. Can it start now? (report: open hosts, free slots/mem/GPUs)
2. Supply: the report's timeline, a pessimistic bound (jobs usually end early).
3. Competition: `classstat Q`, `bqueues Q` (PEND), fairshare rank,
   `bjobs -u all -p -q Q -o "user nreq_slot runtimelimit pend_time"`, `nodestat -r Q`
   (reserved slots). Higher fairshare picks first; backfill lets short jobs into gaps.
4. History: `bhist -l <similar past job>` for past pend times.

Give a range with reasoning ("likely within a few hours: earliest host frees in ~40 min,
you're 3rd of 12 in fairshare"). If it hinges on admins reopening nodes, say so.

## How long will it run?

- Running: `bjobs -o "jobid stat run_time runtimelimit time_left"`; progress via
  `bpeek` or the `-o` log; efficiency `bstat -C`/`-M`; GPU `gpustat -j Q`/`bnvtop ID`.
  Warn if it will hit its walltime or memory limit.
- Not started: scale from `bhist -l <old jobid>` (run time, MAX MEM, CPU efficiency);
  CPU models in one queue differ in speed. `bacct` is not available.

## Job scripts

Rules (details in reference §2–4): always set `-W` (default 15 min); `rusage[mem=]` is
per core; `span[hosts=1]` for single-node multi-core; GPUs need
`mode=exclusive_process` and ≥ 4 cores/GPU; exported variables need `-env`. Use
`bsub < script.sh` with `#BSUB` lines, arrays `-J name[1-N]%K`, `%J`/`%I` in `-o`/`-e`.
Match the repo's existing submit scripts.

## Finished or failed jobs

`bhist -l ID` (exit reason, MAX MEM, efficiency) or
`bjobs -a -o "jobid stat exit_code exit_reason max_mem run_time runtimelimit"`, then the
`.out`/`.err` log. `TERM_MEMLIMIT`: raise `rusage[mem]` to MAX MEM + margin.
`TERM_RUNLIMIT`: raise `-W` (queue max, 8 h tier on `hpc`) or checkpoint.
`TERM_ADMIN`/`TERM_REQUEUE_ADMIN`: admin action; check the status messages (reference §9).

## Answer style

Cause or estimate first, then the evidence lines, then options, marking any that need
kill + resubmit.
