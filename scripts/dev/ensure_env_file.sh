#!/usr/bin/env bash
set -euo pipefail

ENV_FILE_PATH="${1:-.env.dev}"
ENV_EXAMPLE_PATH="${2:-.env.dev.example}"

if [[ ! -f "$ENV_FILE_PATH" ]]; then
  if [[ -f "$ENV_EXAMPLE_PATH" ]]; then
    cp "$ENV_EXAMPLE_PATH" "$ENV_FILE_PATH"
    echo "ℹ️  Utworzono $ENV_FILE_PATH na podstawie $ENV_EXAMPLE_PATH."
    echo "ℹ️  Uzupełnij klucze/secrets w $ENV_FILE_PATH (jeśli wymagane) i uruchom ponownie start."
  else
    echo "⚠️  Brak $ENV_FILE_PATH i $ENV_EXAMPLE_PATH. Start użyje wartości domyślnych tam, gdzie to możliwe."
  fi
  exit 0
fi

# Sync keys that exist in example but are missing from the dev file.
if [[ ! -f "$ENV_EXAMPLE_PATH" ]]; then
  exit 0
fi

added=0
while IFS= read -r line; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" != *=* ]] && continue
  key="${line%%=*}"
  key="${key//[[:space:]]/}"
  [[ -z "$key" ]] && continue
  if ! grep -qE "^[[:space:]]*${key}[[:space:]]*=" "$ENV_FILE_PATH" 2>/dev/null; then
    echo "$line" >> "$ENV_FILE_PATH"
    echo "ℹ️  Dodano brakujący klucz $key do $ENV_FILE_PATH."
    added=$((added + 1))
  fi
done < "$ENV_EXAMPLE_PATH"

if [[ $added -gt 0 ]]; then
  echo "ℹ️  Zsynchronizowano $added brakujących kluczy z $ENV_EXAMPLE_PATH do $ENV_FILE_PATH."
fi
