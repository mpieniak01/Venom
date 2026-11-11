#!/usr/bin/env bash
# Run pinned model code in a networkless WSL namespace with read-only inputs.
set -euo pipefail
umask 077

if [[ "${1:-}" != --inside ]]; then
    if [[ $# -lt 5 ]]; then
        echo "Usage: bash $0 SNAPSHOT JSONL OUTPUT VENV MODE [RECIPE_JSON | VARIANTS...]" >&2
        exit 2
    fi
    snapshot=$(realpath -e -- "$1")
    data=$(realpath -e -- "$2")
    output=$(realpath -m -- "$3")
    venv=$(realpath -e -- "$4")
    mode=$5
    shift 5
    test -d "$snapshot"
    test -f "$data"
    test -x "$venv/bin/python"
    inputs=()
    case "$mode" in
        preflight|control|initial|resume)
            if [[ $# -gt 1 ]]; then exit 2; fi
            if [[ $# -eq 1 ]]; then inputs+=("$(realpath -e -- "$1")"); fi
            ;;
        merge) [[ $# -eq 0 ]] ;;
        evaluate)
            if [[ $# -lt 2 || $# -gt 5 ]]; then exit 2; fi
            declare -A seen=()
            for variant in "$@"; do
                name="${variant%%=*}"
                if [[ "$variant" == base ]]; then
                    inputs+=(base)
                elif [[ "$name" =~ ^checkpoint-[1-9][0-9]{0,4}$ && "$variant" == *=* ]]; then
                    checkpoint=$(realpath -e -- "${variant#*=}")
                    test -d "$checkpoint"
                    inputs+=("$name=$checkpoint")
                else
                    echo "Invalid evaluation variant" >&2
                    exit 2
                fi
                if [[ -n "${seen[$name]:-}" ]]; then exit 2; fi
                seen[$name]=1
            done
            if [[ -z "${seen[base]:-}" ]]; then exit 2; fi
            ;;
        *) exit 2 ;;
    esac
    case "$mode" in
        resume|merge) test -f "$output/profile.json" ;;
        *) mkdir -- "$output" ;;
    esac
    # An open directory descriptor avoids a lockfile path controlled by run output.
    exec {run_lock}<"$output"
    flock --nonblock "$run_lock"
    scratch=$(mktemp -d)
    trap 'rmdir -- "$scratch"' EXIT
    unshare --user --map-root-user --mount --net --pid --fork --kill-child=SIGKILL \
        --propagation private bash "$(realpath -- "$0")" --inside \
        "$snapshot" "$data" "$output" "$venv" "$mode" "$scratch" "${inputs[@]}" {run_lock}<&- </dev/null
    exit
fi

snapshot=$2
data=$3
output=$4
venv=$5
mode=$6
scratch=$7
shift 7
job=$(dirname "$(realpath -- "$0")")
python_base=$(dirname "$(dirname "$(realpath -- "$venv/bin/python")")")

test "$(id -u)" = 0
mount -t tmpfs -o mode=0755,nodev,nosuid tmpfs "$scratch"
cd "$scratch"
mkdir -p usr dev proc tmp etc inputs/model job/scripts/{academy,llm} out "$scratch$venv" "$scratch$python_base"
ln -s usr/bin bin
ln -s usr/lib lib
ln -s usr/lib64 lib64

mount_ro() {
    mount --bind "$1" "$2"
    mount -o remount,bind,ro,nosuid "$2"
}

file_ro() {
    touch "$2"
    mount_ro "$1" "$2"
}

for directory in /usr/bin /usr/lib/x86_64-linux-gnu /usr/lib64 /usr/share /usr/lib/wsl/lib /usr/lib/wsl/drivers; do
    if [[ -d "$directory" ]]; then
        mkdir -p "$scratch$directory"
        mount_ro "$directory" "$scratch$directory"
    fi
done
mount_ro "$venv" "$scratch$venv"
if [[ "$python_base" != "$venv" ]]; then
    mount_ro "$python_base" "$scratch$python_base"
fi
mount_ro "$snapshot" "$scratch/inputs/model"
file_ro "$data" "$scratch/inputs/train.jsonl"
for file in omni_pl_chat_data.py omni_pl_chat_masks.py omni_pl_chat_recipe.py omni_pl_chat_p1.py omni_pl_chat_export.py omni_pl_chat_evaluate.py; do
    file_ro "$job/$file" "$scratch/job/scripts/academy/$file"
done
file_ro "$job/../llm/omni_native_snapshot.json" "$scratch/job/scripts/llm/omni_native_snapshot.json"

worker=(scripts.academy.omni_pl_chat_p1 "$mode")
case "$mode" in
    merge) worker=(scripts.academy.omni_pl_chat_export) ;;
    evaluate)
        mkdir "$scratch/inputs/adapters"
        worker=(scripts.academy.omni_pl_chat_evaluate)
        for variant in "$@"; do
            name="${variant%%=*}"
            if [[ "$name" != base ]]; then
                mkdir "$scratch/inputs/adapters/$name"
                mount_ro "${variant#*=}" "$scratch/inputs/adapters/$name"
            fi
            worker+=("$name")
        done
        ;;
    *) if [[ $# -eq 1 ]]; then file_ro "$1" "$scratch/inputs/recipe.json"; fi ;;
esac

mount --bind "$output" "$scratch/out"
mount -o remount,bind,rw,nodev,nosuid,noexec "$scratch/out"
mount -t proc -o ro,nodev,nosuid,noexec proc "$scratch/proc"
for device in null urandom dxg nvidiactl nvidia0 nvidia-uvm nvidia-uvm-tools; do
    if [[ "$mode" == preflight && "$device" != null && "$device" != urandom ]]; then
        continue
    fi
    if [[ -c "/dev/$device" ]]; then
        touch "dev/$device"
        mount --bind "/dev/$device" "$scratch/dev/$device"
    fi
done
printf 'root:x:0:0:Isolated pilot:/tmp:/bin/false\n' > etc/passwd
printf 'root:x:0:\n' > etc/group
mount -t tmpfs -o mode=1777,nodev,nosuid,noexec tmpfs "$scratch/tmp"
mount -o remount,bind,ro,nodev,nosuid "$scratch"
cd /

gpu_libraries=/usr/lib/wsl/lib
for directory in "$venv"/lib/python*/site-packages/nvidia/*/lib; do
    if [[ -d "$directory" ]]; then
        gpu_libraries="$gpu_libraries:$directory"
    fi
done
exec /usr/sbin/chroot "$scratch" /usr/bin/env -i \
    PATH="$venv/bin:/usr/bin" LANG=C.UTF-8 LD_LIBRARY_PATH="$gpu_libraries" \
    HOME=/tmp HF_HOME=/out/hf-cache XDG_CACHE_HOME=/out/cache PYTHONPATH=/job \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
    TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 PYTHONHASHSEED=42 \
    /usr/bin/setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs \
    "$venv/bin/python" -u -m "${worker[@]}"
