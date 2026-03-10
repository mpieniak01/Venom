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
fi
