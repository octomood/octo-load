#!/usr/bin/env python3
"""Download a real link with the same code path the bot uses.

Usage:
    .venv/bin/python scripts/selftest.py <url> [video|audio|photos]
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Settings
from app.downloader import Downloader, UserError


async def main(url: str, kind: str) -> int:
    work_dir = Path(tempfile.mkdtemp(prefix="octo-selftest-"))
    settings = Settings(bot_token="selftest", work_dir=work_dir)
    downloader = Downloader(settings)

    print(f"→ probing {url}")
    info: MediaInfo | None = None
    try:
        info = await downloader.probe(url)
    except UserError as exc:
        if kind != "photos":
            print(f"✗ probe failed: {exc}")
            return 1
        print(f"  (probe skipped: {exc})")

    if info is None:
        from app.downloader import MediaInfo

        info = MediaInfo(url, url, None, None, None, "gallery")

    print(f"  title:    {info.title}")
    print(f"  uploader: {info.uploader}")
    print(f"  duration: {info.duration}")
    print(f"  extractor:{info.extractor}")

    last = 0.0

    async def progress(done: int, total: int | None) -> None:
        nonlocal last
        if done - last < 1_000_000 and done != total:
            return
        last = done
        pct = f"{done / total * 100:.0f}%" if total else "?"
        print(f"  ⬇ {pct} ({done} bytes)")

    print(f"→ downloading as {kind}")
    try:
        if kind == "video":
            path = await downloader.download_video(
                url, work_dir, job_id="selftest", on_progress=progress
            )
        elif kind == "audio":
            path = await downloader.download_audio(
                url, work_dir, job_id="selftest", on_progress=progress
            )
        else:
            path = await downloader.download_photos(
                url, work_dir, job_id="selftest", limit=settings.max_photos
            )
    except UserError as exc:
        print(f"✗ download failed: {exc}")
        return 1

    files = path if isinstance(path, list) else [path]
    for file in files:
        print(f"✓ {file} — {file.stat().st_size / 1024 / 1024:.1f} MB")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(
        asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "video"))
    )
