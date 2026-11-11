#!/usr/bin/env bash
set -euo pipefail

if command -v rg >/dev/null; then
    rg --version
    exit 0
fi

release=ripgrep-14.1.0-x86_64-unknown-linux-musl
directory="$(mktemp -d "$RUNNER_TEMP/venom-ripgrep.XXXXXXXX")"
archive="$directory/$release.tar.gz"
curl --fail --silent --show-error --location --retry 3 --max-time 45 \
    --proto '=https' --proto-redir '=https' \
    "https://github.com/BurntSushi/ripgrep/releases/download/14.1.0/$release.tar.gz?download=1" \
    --output "$archive"
printf '%s  %s\n' f84757b07f425fe5cf11d87df6644691c644a5cd2348a2c670894272999d3ba7 "$archive" \
    | sha256sum --check --strict
tar -xzf "$archive" -C "$directory" -- "$release/rg"
"$directory/$release/rg" --version
echo "$directory/$release" >> "$GITHUB_PATH"
