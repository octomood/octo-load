from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from app.downloader import Downloader, MediaInfo, _find_file, _normalize_photo
from app.jobs import JobStore, RateLimiter, UserGate, photos_supported
from app.utils import (
    extract_url,
    human_duration,
    human_size,
    progress_bar,
    shorten,
    url_rejection_reason,
)


class UrlTests(unittest.TestCase):
    def test_extract_plain(self) -> None:
        self.assertEqual(
            extract_url("смотри https://youtu.be/abc?t=1 круто"),
            "https://youtu.be/abc?t=1",
        )

    def test_extract_strips_punctuation(self) -> None:
        self.assertEqual(
            extract_url("(https://example.com/a)."), "https://example.com/a"
        )
        self.assertEqual(
            extract_url("https://ru.wikipedia.org/wiki/Кот_(значения)"),
            "https://ru.wikipedia.org/wiki/Кот_(значения)",
        )

    def test_extract_none(self) -> None:
        self.assertIsNone(extract_url("просто текст"))

    def test_reject_localhost(self) -> None:
        reason = asyncio.run(url_rejection_reason("http://localhost:8080/x"))
        self.assertIsNotNone(reason)

    def test_reject_private_ip(self) -> None:
        reason = asyncio.run(url_rejection_reason("http://127.0.0.1/x"))
        self.assertIsNotNone(reason)

    def test_reject_bad_scheme(self) -> None:
        reason = asyncio.run(url_rejection_reason("ftp://example.com/x"))
        self.assertIsNotNone(reason)


class FormatTests(unittest.TestCase):
    def test_size(self) -> None:
        self.assertEqual(human_size(0), "0 Б")
        self.assertEqual(human_size(999), "999 Б")
        self.assertIn("КБ", human_size(2048))
        self.assertIn("МБ", human_size(5 * 1024 * 1024))

    def test_duration(self) -> None:
        self.assertEqual(human_duration(65), "1:05")
        self.assertEqual(human_duration(3725), "1:02:05")
        self.assertEqual(human_duration(None), "—")

    def test_bar(self) -> None:
        self.assertEqual(progress_bar(0, 10), "▱" * 10)
        self.assertEqual(progress_bar(100, 10), "▰" * 10)
        self.assertEqual(len(progress_bar(45, 10)), 10)

    def test_shorten(self) -> None:
        self.assertEqual(shorten("abc", 10), "abc")
        self.assertEqual(len(shorten("abcdefghijk", 10)), 10)


class JobTests(unittest.TestCase):
    def test_photo_detection(self) -> None:
        self.assertTrue(photos_supported("https://www.pinterest.com/pin/1/"))
        self.assertTrue(photos_supported("https://pin.it/abc"))
        self.assertTrue(photos_supported("https://www.tiktok.com/@a/photo/1"))
        self.assertFalse(photos_supported("https://youtu.be/abc"))

    def test_store_ttl(self) -> None:
        store = JobStore(ttl=0.01)
        info = MediaInfo(
            url="https://example.com",
            title="t",
            uploader="u",
            duration=1,
            thumbnail=None,
            extractor="Test",
        )
        job = store.add(1, "https://example.com", info)
        self.assertIsNotNone(store.get(job.id))
        time.sleep(0.02)
        self.assertIsNone(store.get(job.id))

    def test_rate_limiter(self) -> None:
        limiter = RateLimiter(limit=2, window=60)
        self.assertEqual(limiter.check(1)[0], True)
        self.assertEqual(limiter.check(1)[0], True)
        allowed, minutes = limiter.check(1)
        self.assertFalse(allowed)
        self.assertGreaterEqual(minutes, 1)
        self.assertTrue(limiter.check(2)[0])

    def test_gate(self) -> None:
        async def scenario() -> None:
            gate = UserGate(per_user=1, total=2)
            self.assertTrue(await gate.acquire(1))
            self.assertFalse(await gate.acquire(1))
            gate.release(1)
            self.assertTrue(await gate.acquire(1))
            gate.release(1)

        asyncio.run(scenario())


class DownloaderHelperTests(unittest.TestCase):
    def test_find_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "video.mp4").write_bytes(b"x" * 100)
            (folder / "video.part").write_bytes(b"x")
            found = _find_file(folder, "video")
            self.assertEqual(found, folder / "video.mp4")

    def test_normalize_photo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "p.png"
            Image.new("RGBA", (4000, 4000), (255, 0, 0, 128)).save(source)
            result = _normalize_photo(source)
            self.assertEqual(result.suffix, ".jpg")
            with Image.open(result) as image:
                self.assertLessEqual(max(image.size), 2560)

    def test_friendly_failure(self) -> None:
        self.assertIn("поддерживается", Downloader._friendly_failure(["ERROR: Unsupported URL"]))
        self.assertIn(
            "блокирует", Downloader._friendly_failure(["ERROR: HTTP Error 403: Forbidden"])
        )
        self.assertIn("недоступно", Downloader._friendly_failure(["ERROR: Video unavailable"]))


if __name__ == "__main__":
    unittest.main()
