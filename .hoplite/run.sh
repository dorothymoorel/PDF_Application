#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
export TRANSLOKA_DATA_DIR="${TRANSLOKA_DATA_DIR:-${HOME}/.local/share/TransLoka-preview}"
export TRANSLOKA_OLLAMA_EXECUTABLE="${HOME}/.local/share/TransLoka-runtime/ollama/0.33.3/bin/ollama"
export OLLAMA_HOST=127.0.0.1:11434
export TRANSLOKA_OLLAMA_URL=http://127.0.0.1:11434
export OLLAMA_MODELS="${HOME}/.local/share/TransLoka-runtime/ollama-models"
export OLLAMA_CONTEXT_LENGTH=4096
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_NO_CLOUD=1
exec uv run --no-sync python scripts/start_local.py --with-ollama
