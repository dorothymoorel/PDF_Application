#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo "This pinned Ollama bundle requires Linux x86_64." >&2
  exit 1
fi
for tool in curl sha256sum tar zstd; do
  command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool" >&2; exit 1; }
done

version=0.33.3
checksum=c13cea8f3389db4145f8a6cb88d1747242a48639d7c13e3bda7c1ebdc6eebb2f
root="${HOME}/.local/share/TransLoka-runtime/ollama"
target="${root}/${version}"
if [[ -x "${target}/bin/ollama" && -f "${target}/.verified-sha256" ]] &&
   [[ "$(cat "${target}/.verified-sha256")" == "$checksum" ]]; then
  echo "Verified Ollama ${version} is already installed."
  exit 0
fi
mkdir -p "$root"
stage="$(mktemp -d "${root}/.install-XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
curl --fail --location --retry 3 --output "${stage}/ollama.tar.zst" \
  "https://github.com/ollama/ollama/releases/download/v${version}/ollama-linux-amd64.tar.zst"
printf '%s  %s\n' "$checksum" "${stage}/ollama.tar.zst" | sha256sum --check --status
mkdir "${stage}/bundle"
tar --zstd --extract --file "${stage}/ollama.tar.zst" --directory "${stage}/bundle" \
  --no-same-owner --no-same-permissions
test -x "${stage}/bundle/bin/ollama"
printf '%s\n' "$checksum" > "${stage}/bundle/.verified-sha256"
if [[ -e "$target" ]]; then
  echo "Unverified installation already exists; move it aside before retrying." >&2
  exit 1
fi
mv "${stage}/bundle" "$target"
echo "Installed verified Ollama ${version}; no model has been downloaded yet."
