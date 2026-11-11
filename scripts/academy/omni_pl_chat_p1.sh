#!/usr/bin/env bash
# Use the qualified WSL training environment with read-only inputs and no network.
set -euo pipefail

if [[ "${1:-}" != --inside ]]; then
    if [[ $# != 5 ]]; then
        echo "Usage: bash $0 SNAPSHOT TRAIN_JSONL OUTPUT VENV {control|initial|resume|merge}" >&2
        exit 2
    fi
    snapshot=$(realpath -e -- "$1")
    train=$(realpath -e -- "$2")
    output=$(realpath -m -- "$3")
    venv=$(realpath -e -- "$4")
    case "$5" in
        control|initial) mkdir -- "$output" ;;
        resume) test -f "$output/checkpoint-2/hashes.json" ;;
        merge) test -f "$output/checkpoint-8/hashes.json" ;;
        *) exit 2 ;;
    esac
    scratch=$(mktemp -d)
    trap 'rmdir -- "$scratch"' EXIT
    unshare --user --map-root-user --mount --net --pid --fork --kill-child=SIGKILL \
        --propagation private bash "$(realpath -- "$0")" --inside \
        "$snapshot" "$train" "$output" "$venv" "$5" "$scratch"
    exit
fi

snapshot=$2
train=$3
output=$4
venv=$5
mode=$6
scratch=$7
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
file_ro "$train" "$scratch/inputs/train.jsonl"
for file in omni_pl_chat_data.py omni_pl_chat_masks.py omni_pl_chat_p1.py omni_pl_chat_export.py; do
    file_ro "$job/$file" "$scratch/job/scripts/academy/$file"
done
file_ro "$job/../llm/omni_native_snapshot.json" "$scratch/job/scripts/llm/omni_native_snapshot.json"
mount --bind "$output" "$scratch/out"
mount -o remount,bind,rw,nodev,nosuid,noexec "$scratch/out"
mount -t proc -o ro,nodev,nosuid,noexec proc "$scratch/proc"
for device in null urandom dxg nvidiactl nvidia0 nvidia-uvm nvidia-uvm-tools; do
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
worker=(scripts.academy.omni_pl_chat_p1 "$mode")
if [[ "$mode" == merge ]]; then
    worker=(scripts.academy.omni_pl_chat_export)
fi
exec /usr/sbin/chroot "$scratch" /usr/bin/env -i \
    PATH="$venv/bin:/usr/bin" LANG=C.UTF-8 LD_LIBRARY_PATH="$gpu_libraries" \
    HOME=/tmp HF_HOME=/out/hf-cache XDG_CACHE_HOME=/out/cache PYTHONPATH=/job \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
    TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 PYTHONHASHSEED=42 \
    /usr/bin/setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all --no-new-privs \
    "$venv/bin/python" -u -m "${worker[@]}"
