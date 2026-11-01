#!/usr/bin/env bash
set -euo pipefail
[[ $# == 2 ]] || { echo 'Usage: upload.sh SSH_CONFIG SSH_ALIAS' >&2; exit 2; }
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# Supply an existing SSH config with IdentityFile/User/HostName/Port/known_hosts.
# First verify the Vast host fingerprint out-of-band; never accept it blindly.
tar -C "$SCRIPT_DIR" -czf - bootstrap.sh doctor.py configure.py train.sh stack.json |
  ssh -F "$1" -o StrictHostKeyChecking=yes "$2" 'umask 077; mkdir -p /workspace/data/vast-training/kit; tar -xzf - -C /workspace/data/vast-training/kit'
