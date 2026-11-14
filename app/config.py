from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_UPLOAD_LIMIT_MB = 50  # cloud Bot API hard limit


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer, got {raw!r}") from exc


def _ids(name: str) -> frozenset[int]:
    raw = os.getenv(name, "")
    values = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            values.add(int(chunk))
        except ValueError as exc:
            raise SystemExit(f"{name} must contain numeric user ids, got {chunk!r}") from exc
    return frozenset(values)


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admins: frozenset[int] = field(default_factory=frozenset)
    work_dir: Path = Path("data")
    upload_limit_mb: int = DEFAULT_UPLOAD_LIMIT_MB
    max_concurrent: int = 3
    per_user_concurrent: int = 1
    rate_limit_per_hour: int = 20
    max_photos: int = 10
    cookies_file: Path | None = None
    proxy: str | None = None
    api_server: str | None = None
    port: int | None = None
    log_level: str = "INFO"
    ytdlp: str = "yt-dlp"
    gallerydl: str = "gallery-dl"
    extra_args: tuple[str, ...] = ()

    @property
    def upload_limit_bytes(self) -> int:
        return self.upload_limit_mb * 1024 * 1024

    @property
    def safe_limit_bytes(self) -> int:
        # Leave a little headroom for container overhead and metadata.
        return max(1, self.upload_limit_bytes - 1_000_000)

    @property
    def is_local_api(self) -> bool:
        return bool(self.api_server)


def load_settings() -> Settings:
    # .env is convenient locally and harmless in containers (env vars win).
    load_dotenv(override=False)

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "BOT_TOKEN is not set. Create a bot with @BotFather, then put the token "
            "into .env or the environment."
        )

    work_dir = Path(os.getenv("WORK_DIR", "data")).expanduser()
    work_dir.mkdir(parents=True, exist_ok=True)

    cookies_raw = os.getenv("COOKIES_FILE", "").strip()
    cookies_file = Path(cookies_raw).expanduser() if cookies_raw else None
    if cookies_file and not cookies_file.is_file():
        raise SystemExit(f"COOKIES_FILE does not exist: {cookies_file}")

    port_raw = os.getenv("PORT", "").strip()
    port = int(port_raw) if port_raw else None

    limit = _int("UPLOAD_LIMIT_MB", DEFAULT_UPLOAD_LIMIT_MB)
    if limit < 1:
        raise SystemExit("UPLOAD_LIMIT_MB must be positive")
    limit = min(limit, 2000)

    return Settings(
        bot_token=token,
        admins=_ids("ADMIN_IDS"),
        work_dir=work_dir,
        upload_limit_mb=limit,
        max_concurrent=max(1, _int("MAX_CONCURRENT", 3)),
        per_user_concurrent=max(1, _int("PER_USER_CONCURRENT", 1)),
        rate_limit_per_hour=max(1, _int("RATE_LIMIT_PER_HOUR", 20)),
        max_photos=min(10, max(1, _int("MAX_PHOTOS", 10))),
        cookies_file=cookies_file,
        proxy=os.getenv("PROXY", "").strip() or None,
        api_server=os.getenv("API_SERVER", "").strip() or None,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        ytdlp=os.getenv("YTDLP_BIN", "yt-dlp"),
        gallerydl=os.getenv("GALLERYDL_BIN", "gallery-dl"),
        extra_args=tuple(shlex.split(os.getenv("YTDLP_EXTRA_ARGS", ""))),
    )
