#!/usr/bin/env python3
"""End-to-end smoke test: real bot, real download, fake Telegram API.

    .venv/bin/python scripts/e2e_local.py [url]

Starts tests/fake_bot_api.py, runs `python -m app` against it and sends
`/video <url>` as an incoming update. Passes when the bot uploads a file.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fake_bot_api import TOKEN, FakeBotAPI

DEFAULT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
KIND_NAMES = {"v": "video", "a": "audio", "p": "photos"}
API_PORT = 8081
BOT_PORT = 8099


async def main(url: str, kind: str = "v") -> int:
    fake = FakeBotAPI(url, port=API_PORT, kind=kind)
    await fake.start()

    work_dir = Path(tempfile.mkdtemp(prefix="octo-e2e-"))
    env = {
        **os.environ,
        "BOT_TOKEN": TOKEN,
        "API_SERVER": f"http://127.0.0.1:{API_PORT}",
        "PORT": str(BOT_PORT),
        "WORK_DIR": str(work_dir),
        "LOG_LEVEL": "INFO",
        "UPLOAD_LIMIT_MB": "50",
    }

    fake.queue_update(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": int(time.time()),
                "chat": {"id": 42, "type": "private", "first_name": "Tester"},
                "from": {"id": 42, "is_bot": False, "first_name": "Tester"},
                "text": url,
            },
        }
    )

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "app",
        cwd=str(ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    output: list[str] = []

    async def collect() -> None:
        assert process.stdout is not None
        async for raw in process.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            output.append(line)
            print(f"  [bot] {line}")

    reader = asyncio.create_task(collect())

    try:
        await asyncio.wait_for(fake.media_seen.wait(), timeout=240)
        print(
            f"\n✓ bot uploaded {KIND_NAMES.get(kind, kind)} "
            f"via {fake.media_method} ({fake.media_bytes} bytes over HTTP)"
        )
        print(f"✓ methods called: {sorted(set(fake.calls))}")
        return 0
    except TimeoutError:
        print(f"\n✗ timeout waiting for {KIND_NAMES.get(kind, kind)}")
        print("\n".join(output[-40:]))
        return 1
    finally:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 10)
        except TimeoutError:
            process.kill()
        reader.cancel()
        await fake.stop()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    kind = sys.argv[2] if len(sys.argv) > 2 else "v"
    raise SystemExit(asyncio.run(main(url, kind)))
