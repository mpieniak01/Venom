#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
# Release images are a deployment recipe, not another application profile.
export VENOM_DOCKER_RECIPE=release
exec bash "$ROOT_DIR/scripts/docker/stack.sh" "$@"
