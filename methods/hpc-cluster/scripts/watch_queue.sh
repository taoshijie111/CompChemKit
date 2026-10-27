#!/usr/bin/env bash
# Wait until the caller's queue is empty, then print the result lines.
#
# This is the *server-side* companion of watch_jobs.ps1: it runs on the cluster
# (no notification, you read the output when you come back), while
# watch_jobs.ps1 runs locally and wakes the agent when a job leaves the queue.
#
# usage
#   bash watch_queue.sh                       # all my jobs, poll 120 s
#   bash watch_queue.sh -u "$USER" -i 60      # explicit user / interval
#   bash watch_queue.sh -p cpu192             # only this partition
#   bash watch_queue.sh -J '^O_(amino|aldehyde)_' -l 20
#       -J  only count job NAMES matching this regex (ERE)
#       -l  max lines of `sacct` tail to print at the end (default 30)
#       -t  give up after this many hours (default 72)
#
# exit codes: 0 = queue became empty (or only the watched pattern is empty),
#             2 = timeout
set -u

USER_=${USER:-$(whoami)}
INTERVAL=120
PARTITION=""
NAME_RE=""
TAIL=30
MAXH=72

while getopts "u:i:p:J:l:t:h" opt; do
  case "$opt" in
    u) USER_=$OPTARG ;;
    i) INTERVAL=$OPTARG ;;
    p) PARTITION=$OPTARG ;;
    J) NAME_RE=$OPTARG ;;
    l) TAIL=$OPTARG ;;
    t) MAXH=$OPTARG ;;
    h) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option; try -h" >&2; exit 64 ;;
  esac
done

part_opt=""
[ -n "$PARTITION" ] && part_opt=" -p $PARTITION"

echo "watching queue of '$USER_'${part_opt:+ in partition $PARTITION}, poll ${INTERVAL}s, max ${MAXH}h"
start=$(date +%s)
deadline=$(( start + MAXH * 3600 ))

count() {
  # number of my jobs still pending/running (optionally filtered by name)
  squeue -u "$USER_"$part_opt -h -o '%i|%j|%T' 2>/dev/null |
    if [ -n "$NAME_RE" ]; then grep -E "$NAME_RE" | wc -l; else wc -l; fi
}

while :; do
  n=$(count)
  now=$(date +%s)
  printf '[%s] jobs in queue: %s\n' "$(date '+%H:%M:%S')" "$n"
  [ "$n" -eq 0 ] && break
  if [ "$now" -ge "$deadline" ]; then
    echo "TIMEOUT after ${MAXH}h, $n job(s) still queued" >&2
    exit 2
  fi
  sleep "$INTERVAL"
done

echo
echo "================ queue is empty ================"
echo "recent jobs (sacct):"
sacct -u "$USER_" -S "$(date -d "-${MAXH} hours" '+%Y-%m-%dT%H:%M')" \
      --format=JobID%14,JobName%28,State%12,ExitCode%8,Elapsed,NodeList%10 2>/dev/null |
  grep -v '\.' | tail -"$TAIL"
echo "=============================================="
