"""Explicitly download the approved trial model into the running local Ollama service."""

import json
import os
import subprocess
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

MODEL = "qwen3:4b-instruct-2507-q4_K_M"
DIGEST = "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
ALIAS = "transloka-qwen3-4b:trial"
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    executable = Path.home() / ".local/share/TransLoka-runtime/ollama/0.33.3/bin/ollama"
    opener = build_opener(ProxyHandler({}))
    with opener.open("http://127.0.0.1:11434/api/version", timeout=5) as response:
        if json.load(response).get("version") != "0.33.3":
            raise SystemExit("Start the pinned local Ollama runtime before provisioning.")
    environment = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11434", "OLLAMA_NO_CLOUD": "1"}
    subprocess.run([str(executable), "pull", MODEL], env=environment, check=True)
    with opener.open("http://127.0.0.1:11434/api/tags", timeout=10) as response:
        models = json.load(response)["models"]
    if not any(model["name"] == MODEL and model["digest"] == DIGEST for model in models):
        raise SystemExit("Model digest changed; review the upstream model before using it.")
    subprocess.run(
        [
            str(executable),
            "create",
            ALIAS,
            "-f",
            str(ROOT / "infrastructure/local/ollama-trial.Modelfile"),
        ],
        env=environment,
        check=True,
    )
    print(f"Verified {MODEL}; created CPU-bounded alias {ALIAS}.")


if __name__ == "__main__":
    main()
