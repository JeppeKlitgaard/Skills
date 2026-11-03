#!/usr/bin/env python3
"""Read-only diagnosis of why an LSF job is pending and when it could start.

Usage:
    lsf_job_report.py JOBID            # a job, or every element of an array
    lsf_job_report.py 'JOBID[3]'       # one array element

It only runs query commands (bjobs, bhosts, bqueues, bmgroup) and never
changes a job. Built for the DTU "dcc" cluster (LSF 10.1), where other users'
jobs are visible in summary form only and `showstart` rarely has an estimate.

What it prints:
  1. the job's request (queue, slots, walltime, memory, resource string),
  2. LSF's own pending reasons, including the per-host breakdown (-p3),
  3. the hosts that satisfy the job's select[] and their status,
  4. a timeline of when slots on those hosts free up, assuming every running
     job uses its full walltime limit (jobs usually end sooner),
  5. the user's fairshare rank among users with pending jobs in the queue,
  6. if any matching host is closed_Adm: the admins' status message
     (motd.breaking) plus lines recently removed from it.
"""
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter

OPEN_STATES = {"ok", "closed_Full", "closed_Busy"}
MOTD = "/apps9/dcc/etc/motd.breaking"


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True)
    return p.stdout


def bjobs_json(args, fields):
    out = run(["bjobs", "-json", "-o", " ".join(fields)] + args)
    try:
        return json.loads(out).get("RECORDS", [])
    except ValueError:
        return []


def hms_to_s(s):
    """'63:18:56' or '02:00:00' -> seconds; '-' or '' -> None."""
    if not s or s.strip() in ("-", ""):
        return None
    m = re.match(r"^\s*(\d+):(\d+):(\d+)", s)
    if m:
        h, mi, se = map(int, m.groups())
        return h * 3600 + mi * 60 + se
    m = re.match(r"^\s*([\d.]+)\s*second", s)
    if m:
        return int(float(m.group(1)))
    return None


def fmt_dur(sec):
    if sec is None:
        return "?"
    sec = int(sec)
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return "{}d{:02d}h{:02d}m".format(d, h, m) if d else "{}h{:02d}m".format(h, m)


def select_alternatives(resreq):
    """Every select[...] clause in a (possibly ||-compound) resource string."""
    return re.findall(r"select\[(.*?)\]\s*(?:order|rusage|span|cu|affinity|same|\}|$)",
                      resreq)


def queue_info(queue):
    text = run(["bqueues", "-l", queue])
    hosts = []
    m = re.search(r"^HOSTS:\s*(.*)$", text, re.M)
    if m:
        for tok in m.group(1).split():
            tok = re.sub(r"\+\d+$", "", tok).rstrip("/")
            if tok and tok not in ("all", "others", "~"):
                hosts.append(tok)
    shares = []
    block = text.split("SHARE_INFO_FOR:", 1)
    if len(block) == 2:
        for line in block[1].splitlines()[2:]:
            parts = line.split()
            if len(parts) >= 3 and re.match(r"^[\d.]+$", parts[2]):
                shares.append((parts[0], float(parts[2])))
            elif shares and not line.strip():
                break
    return hosts, shares


def specified_hosts(jobid):
    text = run(["bjobs", "-l", jobid])
    flat = re.sub(r"\n\s+", "", text)
    m = re.search(r"Specified Hosts <([^>]*)>", flat)
    if not m:
        return []
    return [h.strip().rstrip("/").lstrip("+") for h in m.group(1).split(",") if h.strip()]


def matching_hosts(selects, candidates):
    found = {}
    for sel in selects or ["type==any"]:
        out = run(["bhosts", "-w", "-R", "select[{}]".format(sel)] + candidates)
        for line in out.splitlines()[1:]:
            p = line.split()
            if len(p) >= 5 and p[3].isdigit() and p[4].isdigit():
                found[p[0]] = {"status": p[1], "max": int(p[3]), "njobs": int(p[4])}
    return found


def read_lines(path):
    try:
        with open(path) as f:
            return [l.rstrip() for l in f]
    except OSError:
        return []


def print_admin_messages():
    """Current motd.breaking, plus lines the admins removed in the latest edit."""
    current = read_lines(MOTD)
    print("\n== Admin status message ({})".format(MOTD))
    print("   " + "\n   ".join(l for l in current if l.strip()) if current else "   (unreadable)")
    archives = sorted(glob.glob(MOTD + ".pre*"), key=os.path.getmtime)
    if archives:
        kept = set(current)
        removed = [l for l in read_lines(archives[-1]) if l.strip() and l not in kept]
        if removed:
            print("\n   Removed in the latest edit (from {}):".format(os.path.basename(archives[-1])))
            print("   " + "\n   ".join(removed))


def main():
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        print(__doc__)
        sys.exit(1)
    jobarg = sys.argv[1]
    fields = ["jobid", "jobindex", "stat", "queue", "user", "job_name", "pend_reason",
              "pend_time", "runtimelimit", "nreq_slot", "memlimit", "combined_resreq",
              "gpu_num"]
    recs = [r for r in bjobs_json([jobarg], fields) if "ERROR" not in r]
    if not recs:
        print("No such job visible to you: {}".format(jobarg))
        print(run(["bjobs", "-a", jobarg]).strip())
        sys.exit(1)

    states = Counter(r["STAT"] for r in recs)
    pend = [r for r in recs if r["STAT"] == "PEND"]
    rep = pend[0] if pend else recs[0]
    rep_id = rep["JOBID"] + ("[{}]".format(rep["JOBINDEX"]) if rep.get("JOBINDEX") not in (None, "", "0") else "")

    print("== Job {} ({}) user={} queue={}".format(jobarg, rep["JOB_NAME"], rep["USER"], rep["QUEUE"]))
    print("   elements by state: " + ", ".join("{} {}".format(n, s) for s, n in states.items()))
    print("   request: slots={} walltime={} memlimit={} gpus={}".format(
        rep["NREQ_SLOT"], rep["RUNTIMELIMIT"], rep["MEMLIMIT"], rep["GPU_NUM"] or "-"))
    print("   resreq: {}".format(rep["COMBINED_RESREQ"]))
    if not pend:
        print("\nNothing pending; nothing to diagnose.")
        return

    print("\n== LSF pending reason (representative element {}): pending {}".format(rep_id, rep["PEND_TIME"]))
    reasons = Counter(r["PEND_REASON"] for r in pend)
    for reason, n in reasons.most_common():
        print("   {:4d} x {}".format(n, reason))
    p3 = run(["bjobs", "-p3", rep_id])
    tail = p3.split("\n", 2)[2] if p3.count("\n") >= 2 else p3
    print("   " + tail.strip().replace("\n", "\n   "))

    queue = rep["QUEUE"]
    q_hosts, shares = queue_info(queue)
    asked = specified_hosts(rep_id)
    candidates = asked or q_hosts
    selects = select_alternatives(rep["COMBINED_RESREQ"])
    hosts = matching_hosts(selects, candidates)
    print("\n== Hosts matching the job's select[] within {} ({} found)".format(
        "-m " + " ".join(asked) if asked else "queue " + queue, len(hosts)))
    by_status = Counter(h["status"] for h in hosts.values())
    print("   by status: " + (", ".join("{} {}".format(n, s) for s, n in by_status.most_common()) or "none"))
    if not hosts:
        print("   No host in the candidate set satisfies the request: the job cannot start as submitted.")

    need = int(rep["NREQ_SLOT"] or 1)
    single_host = "span[hosts=1]" in rep["COMBINED_RESREQ"]
    open_hosts = {n: h for n, h in hosts.items() if h["status"] in OPEN_STATES}
    if hosts and not open_hosts:
        print("   Every matching host is closed by an admin or unavailable. The job waits until")
        print("   they reopen (maintenance/drain). Timeline below is for when they would be empty.")
    timeline_hosts = open_hosts or hosts

    print("\n== Slot release timeline (running jobs assumed to use their full walltime)")
    best = None
    for name in sorted(timeline_hosts):
        h = timeline_hosts[name]
        jobs = bjobs_json(["-u", "all", "-r", "-m", name],
                          ["jobid", "user", "nalloc_slot", "run_time", "runtimelimit"])
        events = []
        for j in jobs:
            if "ERROR" in j:
                continue
            lim, ran = hms_to_s(j.get("RUNTIMELIMIT")), hms_to_s(j.get("RUN_TIME"))
            left = max(0, lim - ran) if lim is not None and ran is not None else None
            events.append((left if left is not None else 10 ** 9, int(j.get("NALLOC_SLOT") or 0)))
        events.sort()
        used = sum(s for _, s in events)
        free = max(0, h["max"] - used)
        t_ready = 0 if free >= need else None
        acc = free
        for left, slots in events:
            if t_ready is not None:
                break
            acc += slots
            if acc >= need:
                t_ready = left
        nxt = ", ".join("{}@{}".format(s, fmt_dur(l)) for l, s in events[:4])
        print("   {:12s} {:12s} free {:3d}/{:3d}  -> {} slots free {}   (next releases: {})".format(
            name, h["status"], free, h["max"], need,
            "now" if t_ready == 0 else "in " + fmt_dur(t_ready) if t_ready is not None else "never (too small)",
            nxt or "-"))
        if t_ready is not None and (best is None or t_ready < best[0]):
            best = (t_ready, name)
    if best and single_host:
        when = "now" if best[0] == 0 else "in " + fmt_dur(best[0])
        if open_hosts:
            print("   Earliest single host with {} free slots: {} {} (walltime-based upper bound for"
                  " running jobs; ignores higher-priority pending jobs)".format(need, best[1], when))
        else:
            print("   {} would have room {}, but only once an admin reopens it.".format(best[1], when))

    if shares:
        user = rep["USER"]
        pending_users = set(r["USER"] for r in bjobs_json(["-u", "all", "-p", "-q", queue], ["user"]) if "USER" in r)
        ranked = sorted([s for s in shares if s[0] in pending_users or s[0] == user],
                        key=lambda s: -s[1])
        pos = next((i for i, s in enumerate(ranked) if s[0] == user), None)
        mine = dict(shares).get(user)
        print("\n== Fairshare in {}: your dynamic priority {} ; rank {} of {} users with pending jobs".format(
            queue, mine, (pos + 1) if pos is not None else "?", len(ranked)))
        print("   (higher priority is scheduled first; priority drops as you use the queue and recovers over time)")

    if by_status.get("closed_Adm"):
        print_admin_messages()


if __name__ == "__main__":
    main()
