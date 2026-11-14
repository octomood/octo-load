from __future__ import annotations

import asyncio
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from PIL import Image, ImageOps

from .config import Settings

ProgressCallback = Callable[[int, int | None], Awaitable[None]]

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


class UserError(Exception):
    """An error whose message is safe and useful to show to the user."""


class DownloadCancelled(Exception):
    """The user cancelled the job."""


class TooLarge(UserError):
    def __init__(self, size: int) -> None:
        self.size = size
        super().__init__("Файл больше лимита Telegram")


@dataclass(slots=True)
class MediaInfo:
    url: str
    title: str
    uploader: str | None
    duration: int | None
    thumbnail: str | None
    extractor: str
    is_live: bool = False

    @property
    def site(self) -> str:
        name = (self.extractor or "link").split(":")[0].split(" ")[0]
        return name[:1].upper() + name[1:] if name else "Ссылка"


def _module_cmd(binary: str, module: str) -> list[str]:
    if Path(binary).exists():
        return [binary]
    found = shutil.which(binary)
    if found:
        return [found]
    return [sys.executable, "-m", module]


class Downloader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._active: dict[str, asyncio.subprocess.Process] = {}
        self._cancelled: set[str] = set()
        self._ytdlp = _module_cmd(settings.ytdlp, "yt_dlp")
        self._gallerydl = _module_cmd(settings.gallerydl, "gallery_dl")

    # ---------------------------------------------------------------- helpers

    def _base_args(self) -> list[str]:
        args = [
            *self._ytdlp,
            "--ignore-config",
            "--no-warnings",
            "--no-playlist",
            "--no-mtime",
            "--socket-timeout",
            "20",
            "--retries",
            "3",
            "--fragment-retries",
            "5",
        ]
        if self.settings.proxy:
            args += ["--proxy", self.settings.proxy]
        if self.settings.cookies_file:
            args += ["--cookies", str(self.settings.cookies_file)]
        args += list(self.settings.extra_args)
        return args

    async def cancel(self, job_id: str) -> bool:
        process = self._active.get(job_id)
        if process is None or process.returncode is not None:
            return False
        self._cancelled.add(job_id)
        try:
            process.terminate()
        except ProcessLookupError:
            return False
        return True

    async def close(self) -> None:
        """Terminate every child process (used on shutdown)."""
        for process in list(self._active.values()):
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
        for process in list(self._active.values()):
            try:
                await asyncio.wait_for(process.wait(), 5)
            except (TimeoutError, ProcessLookupError):
                pass
        self._active.clear()

    async def _exec(
        self,
        args: list[str],
        *,
        timeout: float,
        job_id: str | None = None,
        on_line: Callable[[str], None] | None = None,
        cwd: Path | None = None,
    ) -> tuple[int, list[str]]:
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(cwd) if cwd else None,
                limit=64 * 1024 * 1024,
            )
        except FileNotFoundError as exc:
            raise UserError(
                "На сервере не установлен yt-dlp или gallery-dl — напиши администратору."
            ) from exc

        if job_id:
            self._active[job_id] = process

        lines: list[str] = []

        async def read() -> None:
            assert process.stdout is not None
            async for raw in process.stdout:
                line = raw.decode("utf-8", "replace").rstrip()
                lines.append(line)
                if len(lines) > 300:
                    del lines[:100]
                if on_line:
                    on_line(line)

        reader = asyncio.create_task(read())
        try:
            await asyncio.wait_for(process.wait(), timeout)
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise UserError("Загрузка заняла слишком много времени и была остановлена.") from exc
        finally:
            try:
                await asyncio.wait_for(reader, 5)
            except (TimeoutError, asyncio.CancelledError):
                reader.cancel()
            if job_id:
                self._active.pop(job_id, None)

        if job_id:
            was_cancelled = job_id in self._cancelled
            self._cancelled.discard(job_id)
            if was_cancelled:
                raise DownloadCancelled()
        return process.returncode or 0, lines

    @staticmethod
    def _friendly_failure(lines: list[str]) -> str:
        tail = "\n".join(lines[-80:]).lower()
        if "unsupported url" in tail:
            return "Этот сайт пока не поддерживается 😕 Попробуй другую ссылку."
        if "cancelled" in tail:
            return "Загрузка отменена."
        if any(word in tail for word in ("private", "login", "sign in", "log in", "cookies")):
            return (
                "Контент приватный или требует входа. Для таких ссылок нужны cookies — "
                "это настраивается на сервере бота."
            )
        if any(word in tail for word in ("video unavailable", "not available", "removed")):
            return "Видео недоступно: удалено, заблокировано или скрыто автором."
        if "age" in tail and "confirm" in tail:
            return "YouTube просит подтвердить возраст — без cookies такое не скачать."
        if "404" in tail or "not found" in tail:
            return "По этой ссылке ничего не нашлось (404)."
        if any(word in tail for word in ("403", "forbidden", "blocked")):
            return "Сайт блокирует скачивание с этого сервера. Попробуй позже или другую ссылку."
        if "ffmpeg" in tail:
            return "Не удалось обработать файл (ffmpeg). Попробуй другой формат или ссылку."
        if "timed out" in tail or "timeout" in tail:
            return "Сайт не ответил вовремя. Попробуй ещё раз."
        return "Не получилось скачать 😕 Попробуй другую ссылку или формат."

    # ------------------------------------------------------------------ probe

    async def probe(self, url: str) -> MediaInfo:
        args = self._base_args() + ["-J", "--no-download", url]
        code, lines = await self._exec(args, timeout=90)
        if code != 0:
            raise UserError(self._friendly_failure(lines))

        payload = _extract_json(lines)
        if payload is None:
            raise UserError(self._friendly_failure(lines))

        if payload.get("_type") == "playlist" and payload.get("entries"):
            payload = payload["entries"][0]

        if payload.get("is_live"):
            raise UserError("Прямые эфиры не скачиваю — дождись окончания записи или дай ссылку на видео.")

        title = payload.get("title") or payload.get("description") or "Без названия"
        return MediaInfo(
            url=payload.get("webpage_url") or url,
            title=str(title)[:300],
            uploader=payload.get("uploader") or payload.get("channel") or payload.get("creator"),
            duration=int(payload["duration"]) if payload.get("duration") else None,
            thumbnail=payload.get("thumbnail"),
            extractor=str(payload.get("extractor_key") or payload.get("extractor") or ""),
            is_live=bool(payload.get("is_live")),
        )

    # -------------------------------------------------------------- downloads

    async def download_video(
        self,
        url: str,
        dest: Path,
        *,
        job_id: str,
        on_progress: ProgressCallback,
    ) -> Path:
        cap = max(1_000_000, self.settings.safe_limit_bytes)
        cap_mb = cap // (1024 * 1024)
        selector = (
            f"bv*[filesize<{cap_mb}M][ext=mp4]+ba[filesize<{cap_mb}M][ext=m4a]"
            f"/b[filesize<{cap_mb}M][ext=mp4]"
            f"/bv*[filesize<{cap_mb}M]+ba[filesize<{cap_mb}M]"
            f"/b[filesize<{cap_mb}M]/bv*+ba/b"
        )
        args = self._base_args() + [
            "--newline",
            "--progress-delta",
            "1",
            "--progress-template",
            "dl:%(progress.downloaded_bytes)s/%(progress.total_bytes_estimate)s",
            "-f",
            selector,
            "--merge-output-format",
            "mp4",
            "--remux-video",
            "mp4",
            "--concurrent-fragments",
            "4",
            "-o",
            str(dest / "video.%(ext)s"),
            url,
        ]

        parser = _ProgressParser(on_progress)
        code, lines = await self._exec(args, timeout=1800, job_id=job_id, on_line=parser.feed)
        await parser.flush()
        if code != 0:
            raise UserError(self._friendly_failure(lines))

        path = _find_file(dest, "video")
        if path is None:
            raise UserError(self._friendly_failure(lines))
        if path.stat().st_size > self.settings.upload_limit_bytes:
            raise TooLarge(path.stat().st_size)
        return path

    async def download_audio(
        self,
        url: str,
        dest: Path,
        *,
        job_id: str,
        on_progress: ProgressCallback,
    ) -> Path:
        args = self._base_args() + [
            "--newline",
            "--progress-delta",
            "1",
            "--progress-template",
            "dl:%(progress.downloaded_bytes)s/%(progress.total_bytes_estimate)s",
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "--embed-metadata",
            "-o",
            str(dest / "audio.%(ext)s"),
            url,
        ]
        parser = _ProgressParser(on_progress)
        code, lines = await self._exec(args, timeout=1800, job_id=job_id, on_line=parser.feed)
        await parser.flush()
        if code != 0:
            raise UserError(self._friendly_failure(lines))

        path = _find_file(dest, "audio")
        if path is None:
            raise UserError(self._friendly_failure(lines))
        if path.stat().st_size > self.settings.upload_limit_bytes:
            raise TooLarge(path.stat().st_size)
        return path

    async def download_photos(
        self,
        url: str,
        dest: Path,
        *,
        job_id: str,
        limit: int,
    ) -> list[Path]:
        args = [
            *self._gallerydl,
            "--config-ignore",
            "-q",
            "-D",
            str(dest),
            "--range",
            f"1-{max(1, limit)}",
            "-R",
            "3",
        ]
        if self.settings.cookies_file:
            args += ["-C", str(self.settings.cookies_file)]
        if self.settings.proxy:
            args += ["--proxy", self.settings.proxy]
        args.append(url)

        code, lines = await self._exec(args, timeout=600, job_id=job_id)
        raw = [
            path
            for path in dest.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ]
        if not raw:
            if code != 0:
                raise UserError(self._friendly_failure(lines))
            raise UserError(
                "Фото по ссылке не нашлись. Возможно, пост приватный или это видео — "
                "попробуй кнопку «Видео»."
            )

        raw.sort(key=lambda path: (str(path.parent), path.name))
        prepared: list[Path] = []
        for path in raw[:limit]:
            try:
                prepared.append(await asyncio.to_thread(_normalize_photo, path))
            except Exception:  # noqa: BLE001 - corrupt/unsupported image, just skip it
                continue
        if not prepared:
            raise UserError("Не удалось подготовить фото к отправке.")
        return prepared


# --------------------------------------------------------------------- module helpers


def _extract_json(lines: list[str]) -> dict | None:
    text = "\n".join(lines)
    start = text.find("{")
    while start != -1:
        try:
            value = json.loads(text[start:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)
    return None


def _find_file(directory: Path, stem: str) -> Path | None:
    candidates = [
        path
        for path in directory.glob(f"{stem}.*")
        if path.is_file() and path.suffix != ".part"
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)


def _normalize_photo(path: Path) -> Path:
    if (
        path.suffix.lower() in {".jpg", ".jpeg"}
        and path.stat().st_size <= 9_500_000
    ):
        return path

    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode in {"RGBA", "LA", "P"}:
            image = image.convert("RGBA")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        image.thumbnail((2560, 2560))

        target = path.with_suffix(".jpg")
        quality = 90
        while True:
            image.save(target, "JPEG", quality=quality, optimize=True)
            if target.stat().st_size <= 9_500_000 or quality <= 50:
                break
            quality -= 10
    return target


class _ProgressParser:
    def __init__(self, callback: ProgressCallback) -> None:
        self.callback = callback
        self.done = 0
        self.total: int | None = None
        self._task: asyncio.Task | None = None

    def feed(self, line: str) -> None:
        if not line.startswith("dl:"):
            return
        raw_done, _, raw_total = line[3:].partition("/")
        try:
            self.done = int(float(raw_done))
        except ValueError:
            return
        try:
            self.total = int(float(raw_total)) if raw_total not in {"", "NA", "None"} else None
        except ValueError:
            self.total = None
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.callback(self.done, self.total))

    async def flush(self) -> None:
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, 10)
            except (TimeoutError, asyncio.CancelledError):
                pass
        if self.done:
            await self.callback(self.done, self.total)
