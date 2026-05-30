from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SCRIPT = os.getenv("SLACK_RECEIPTS_CHANNELS_SCRIPT", "").strip()
STORE = Path(
    os.getenv(
        "SLACK_RECEIPTS_CHANNELS_STORE",
        "~/.local/state/slack-receipts/slack-channels.json",
    )
).expanduser()


class SlackChannelsAdapter:
    def __init__(self, script: str | Path = SCRIPT):
        self.script = Path(script).expanduser() if str(script).strip() else None

    def _run(self, *args: str) -> str:
        if self.script is None:
            raise RuntimeError("SLACK_RECEIPTS_CHANNELS_SCRIPT is not configured")
        result = subprocess.run(
            [str(self.script), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def resolve(self, name: str) -> str:
        return self._run("resolve", name)

    def fetch(self, name: str) -> str:
        return self._run("fetch", name)

    def list_mappings(self) -> dict[str, str]:
        if not STORE.exists():
            return {}
        data = json.loads(STORE.read_text(encoding="utf-8"))
        return data.get("channels", {})
