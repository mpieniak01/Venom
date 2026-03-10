#!/usr/bin/env bash

# Shared env contract helpers for shell scripts.
# Priority order: explicit environment variable > value from env file > default.

env_contract_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$script_dir/../.." && pwd
}

env_contract_resolve_file() {
  local raw_path="${1:-}"
  local root_dir="${2:-$(env_contract_repo_root)}"
  if [[ -z "$raw_path" ]]; then
    printf ''
    return 0
  fi
  if [[ "$raw_path" = /* ]]; then
    printf '%s' "$raw_path"
  else
    printf '%s/%s' "$root_dir" "$raw_path"
  fi
}

env_contract_read_file_var() {
  local file_path="$1"
  local key="$2"
  if [[ ! -f "$file_path" ]]; then
    return 0
  fi
  awk -F= -v k="$key" '
    $1 == k {
      sub(/^[^=]+=*/, "", $0)
      gsub(/\r$/, "", $0)
      print $0
      exit
    }
  ' "$file_path"
}

env_contract_get() {
  local key="$1"
  local default_value="${2-}"
  local file_path="${3-}"
  local env_value="${!key-}"

  if [[ -n "$env_value" ]]; then
    printf '%s' "$env_value"
    return 0
  fi

  if [[ -n "$file_path" ]]; then
    local file_value
    file_value="$(env_contract_read_file_var "$file_path" "$key")"
    if [[ -n "$file_value" ]]; then
      printf '%s' "$file_value"
      return 0
    fi
  fi

  printf '%s' "$default_value"
}

env_contract_origin() {
  local key="$1"
  local file_path="${2-}"
  local default_value="${3-}"
  local env_value="${!key-}"

  if [[ -n "$env_value" ]]; then
    printf 'env'
    return 0
  fi

  if [[ -n "$file_path" ]]; then
    local file_value
    file_value="$(env_contract_read_file_var "$file_path" "$key")"
    if [[ -n "$file_value" ]]; then
      printf 'file'
      return 0
    fi
  fi

  if [[ -n "$default_value" ]]; then
    printf 'default'
  else
    printf 'empty'
  fi
}
