#!/usr/bin/env bash
set -euo pipefail

# Resolve this checkout, never the operator's currently running checkout.
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
if [[ ! -f .venv/bin/activate ]]; then
  echo "ERROR: missing .venv/bin/activate in ${repo_root}" >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

fast_workers="${PYTEST_FAST_WORKERS:-4}"
long_workers="${PYTEST_LONG_WORKERS:-2}"
heavy_workers="${PYTEST_HEAVY_WORKERS:-1}"
case_timeout="${PYTEST_TEST_TIMEOUT_SECONDS:-120}"
group_timeout="${PYTEST_GROUP_TIMEOUT_SECONDS:-1800}"
report_base="${PYTEST_GROUP_REPORT_DIR:-test-results/test-groups}"
manual_file="${MANUAL_LONG_RUNNING_FILE:-config/pytest-groups/manual-long-running.txt}"
group_selection=all
plan_only=0
while (($#)); do
  case "$1" in
    --plan) plan_only=1 ;;
    --group)
      if (($# < 2)); then echo 'ERROR: --group requires fast, long, heavy or all' >&2; exit 2; fi
      group_selection="$2"
      shift ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$group_selection" in all|fast|long|heavy) ;; *) echo "ERROR: invalid group: $group_selection" >&2; exit 2 ;; esac
for value in "$fast_workers" "$long_workers" "$heavy_workers" "$case_timeout" "$group_timeout"; do
  if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: workers and timeouts must be positive integers: $value" >&2
    exit 2
  fi
done
if ! command -v timeout >/dev/null; then
  echo 'ERROR: GNU timeout is required to enforce the group time limit' >&2
  exit 2
fi

# Physical tests are gated independently in conftest. Keep the command-line
# timeout and other pytest options inherited from CI or the operator.
export ENABLE_SANDBOX=false ALLOW_SANDBOX_CONTAINERS=false
unset PYTEST_MARKEXPR

safe_mark='not live_venom and not live_model and not unsafe_direct_runtime and not requires_docker and not requires_docker_compose'
auto_mark="(${PYTEST_AUTO_MARK_EXPR:-not manual_llm and not performance}) and $safe_mark"
heavy_mark="(${PYTEST_HEAVY_MARK_EXPR:-not manual_llm}) and $safe_mark"
groups=(fast long heavy)
if [[ "$group_selection" != all ]]; then groups=("$group_selection"); fi

group_workers() {
  case "$1" in fast) echo "$fast_workers" ;; long) echo "$long_workers" ;; heavy) echo "$heavy_workers" ;; esac
}
group_marker() {
  case "$1" in heavy) echo "$heavy_mark" ;; *) echo "$auto_mark" ;; esac
}
read_group() {
  local file="config/pytest-groups/$1.txt"
  [[ -f "$file" ]] || { echo "ERROR: missing group: $file" >&2; return 1; }
  if [[ -f "$manual_file" ]]; then
    grep -vE '^[[:space:]]*(#|$)' "$file" | grep -vxF -f "$manual_file" || true
  else
    grep -vE '^[[:space:]]*(#|$)' "$file" || true
  fi
}

if ((plan_only)); then
  echo "Checkout: $repo_root"
  echo "Marked physical tests: excluded; unreviewed files still require audit"
  for group in "${groups[@]}"; do
    tests="$(read_group "$group")" || exit 2
    count=0
    if [[ -n "$tests" ]]; then count="$(printf '%s\n' "$tests" | wc -l)"; fi
    printf '%s: files=%s workers=%s marker=%s\n' "$group" "$count" "$(group_workers "$group")" "$(group_marker "$group")"
  done
  printf 'Per test timeout: %ss; per group timeout: %ss\n' "$case_timeout" "$group_timeout"
  exit 0
fi

mkdir -p "$report_base"
report_dir="$(mktemp -d "${report_base%/}/run-XXXXXXXX")"
summary="$report_dir/groups.tsv"
: > "$summary"
overall_start="$(date +%s)"
overall_rc=0
for group in "${groups[@]}"; do
  tests="$(read_group "$group")" || { overall_rc=1; printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$group" 0 2 ERROR "$(group_workers "$group")" 0 >> "$summary"; continue; }
  if [[ -z "$tests" ]]; then
    echo "ERROR: group $group contains no eligible files" >&2
    overall_rc=1
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$group" 0 5 EMPTY "$(group_workers "$group")" 0 >> "$summary"
    continue
  fi
  mapfile -t test_files <<< "$tests"
  workers="$(group_workers "$group")"
  echo "▶ Pytest: $group; files=${#test_files[@]}; workers=$workers"
  start="$(date +%s)"
  set +e
  timeout --signal=TERM --kill-after=10 "$group_timeout" \
    .venv/bin/pytest -n "$workers" -m "$(group_marker "$group")" \
    --timeout="$case_timeout" --timeout-method=thread \
    --junitxml="$report_dir/$group.xml" "${test_files[@]}"
  rc=$?
  set -e
  elapsed=$(( $(date +%s) - start ))
  status=PASS
  if ((rc != 0)); then
    overall_rc=1
    case "$rc" in 5) status=EMPTY ;; 124|137) status=TIMEOUT ;; *) status=FAIL ;; esac
  fi
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$group" "$elapsed" "$rc" "$status" "$workers" "${#test_files[@]}" >> "$summary"
  printf '⏱ %s: %ss [%s, exit=%s]\n' "$group" "$elapsed" "$status" "$rc"
done
elapsed_total=$(( $(date +%s) - overall_start ))
set +e
python3 - "$summary" "$report_dir/summary.json" "$elapsed_total" "$overall_rc" <<'PY'
import csv
import json
import sys
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

rows = []
with Path(sys.argv[1]).open(encoding="utf-8", newline="") as stream:
    for group, seconds, exit_code, status, workers, files in csv.reader(stream, delimiter="\t"):
        xml = Path(sys.argv[2]).parent / f"{group}.xml"
        counts = {"tests": 0, "skipped": 0, "failures": 0, "errors": 0}
        try:
            if not xml.exists():
                raise FileNotFoundError(xml)
            for node in ET.parse(xml).iter("testcase"):
                counts["tests"] += 1
                for tag, key in (("skipped", "skipped"), ("failure", "failures"), ("error", "errors")):
                    counts[key] += node.find(tag) is not None
        except (ET.ParseError, OSError) as exc:
            if status == "PASS":
                status = "REPORT_ERROR"
            print(f"{group}: raport JUnit niedostępny: {exc}", file=sys.stderr)
        if status == "PASS" and counts["tests"] and counts["tests"] == counts["skipped"]:
            status = "ALL_SKIPPED"
        rows.append({"group": group, "seconds": int(seconds), "exit_code": int(exit_code), "status": status, "workers": int(workers), "group_files": int(files), "deselected_cases": None, **counts})
        print(f"{group}: {seconds}s, {status}, tests={counts['tests']}, skipped={counts['skipped']}, failures={counts['failures']}, errors={counts['errors']}")
report_exit = int(sys.argv[4]) or int(any(row["status"] in {"REPORT_ERROR", "ALL_SKIPPED"} for row in rows))
try:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL).strip())
except (OSError, subprocess.CalledProcessError):
    revision, dirty = None, None
report = {"revision": revision, "working_tree_dirty": dirty, "created_at_utc": datetime.now(timezone.utc).isoformat(), "total_seconds": int(sys.argv[3]), "exit_code": report_exit, "scope": "simulated selection; marked live/manual/Docker cases excluded; unreviewed files remain", "deselected_cases_reason": "not measured by xdist JUnit", "groups": rows}
Path(sys.argv[2]).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
sys.exit(report_exit)
PY
report_rc=$?
set -e
printf '⏱ Razem: %ss; raport: %s/summary.json (oznaczone scenariusze fizyczne wykluczone; niezweryfikowane pliki wymagają audytu)\n' "$elapsed_total" "$report_dir"
exit "$report_rc"
