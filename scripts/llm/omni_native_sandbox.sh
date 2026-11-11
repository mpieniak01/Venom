#!/usr/bin/env bash
# Invoked only inside a private user, mount, network and PID namespace.
set -euo pipefail

snapshot=$1
sandbox=$2
python_env=$3
python_base=$4
python_exec=$5
worker_dir=$(dirname "$(realpath -- "$0")")

test "$(id -u)" = 0
mount -t tmpfs -o mode=0755,nodev,nosuid tmpfs "$sandbox"
cd "$sandbox"
mkdir -p usr dev proc tmp etc model job "$sandbox$python_env" "$sandbox$python_base"
ln -s usr/bin bin
ln -s usr/lib lib
ln -s usr/lib64 lib64

mount_readonly() {
    mount --bind "$1" "$2"
    mount -o remount,bind,ro,nosuid "$2"
}

for directory in /usr/bin /usr/lib/x86_64-linux-gnu /usr/lib64 /usr/share; do
    mkdir -p "$sandbox$directory"
    mount_readonly "$directory" "$sandbox$directory"
done
for directory in /usr/lib/wsl/lib /usr/lib/wsl/drivers; do
    if mountpoint -q "$directory"; then
        mkdir -p "$sandbox$directory"
        mount_readonly "$directory" "$sandbox$directory"
    fi
done
mount_readonly "$python_env" "$sandbox$python_env"
if [[ "$python_base" != "$python_env" ]]; then
    mount_readonly "$python_base" "$sandbox$python_base"
fi
# Mount only the material named by the tracked manifest. Ignore local Hub metadata.
pin="$worker_dir/omni_native_snapshot.json"
snapshot=$(realpath -- "$snapshot")
manifest_files=$("$python_exec" -c '
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print("\n".join(json.load(handle)["files"]))
' "$pin")
while IFS= read -r file; do
    original="$snapshot/$file"
    target="$sandbox/model/$file"
    [[ -f "$original" && "$(realpath -- "$original")" == "$original" ]]
    mkdir -p "$(dirname "$target")"
    touch "$target"
    mount_readonly "$original" "$target"
done <<< "$manifest_files"
for file in omni_native_worker.py omni_native_snapshot.json; do
    touch "$sandbox/job/$file"
    mount_readonly "$worker_dir/$file" "$sandbox/job/$file"
done
mount -t proc -o ro,nodev,nosuid,noexec proc "$sandbox/proc"
for device in null urandom dxg nvidiactl nvidia0 nvidia-uvm nvidia-uvm-tools; do
    if [[ -c "/dev/$device" ]]; then
        touch "$sandbox/dev/$device"
        mount --bind "/dev/$device" "$sandbox/dev/$device"
    fi
done
printf 'root:x:0:0:Isolated worker:/tmp:/bin/false\n' >etc/passwd
printf 'root:x:0:\n' >etc/group
mount -t tmpfs -o mode=1777,nodev,nosuid,noexec tmpfs "$sandbox/tmp"
mount -o remount,bind,ro,nodev,nosuid "$sandbox"
cd /

gpu_libraries=/usr/lib/wsl/lib
for directory in "$python_env"/lib/python*/site-packages/nvidia/*/lib; do
    if [[ -d "$directory" ]]; then
        gpu_libraries="$directory:$gpu_libraries"
    fi
done
exec /usr/sbin/chroot "$sandbox" /usr/bin/env -i \
    PATH="$python_env/bin:/usr/bin" LANG=C.UTF-8 \
    LD_LIBRARY_PATH="$gpu_libraries" \
    HOME=/tmp XDG_CACHE_HOME=/tmp/cache HF_HOME=/tmp/hf \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 \
    TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 \
    /usr/bin/setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
    --no-new-privs "$python_exec" -u /job/omni_native_worker.py
