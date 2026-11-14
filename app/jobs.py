from __future__ import annotations

import asyncio
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .downloader import MediaInfo

PHOTO_DOMAINS = (
    "pinterest.com",
    "pin.it",
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "reddit.com",
    "flickr.com",
    "tumblr.com",
    "vk.com",
    "deviantart.com",
    "artstation.com",
    "imgur.com",
    "pixiv.net",
    "danbooru.donmai.us",
    "weibo.com",
    "threads.net",
    "snapchat.com",
    "facebook.com",
    "bsky.app",
)


def photos_supported(url: str, extractor: str = "") -> bool:
    host = (urlparse(url).hostname or "").lower()
    if any(host == domain or host.endswith("." + domain) for domain in PHOTO_DOMAINS):
        return True
    extractor = extractor.lower()
    return any(domain.split(".")[0] in extractor for domain in PHOTO_DOMAINS)


@dataclass(slots=True)
class Job:
    id: str
    user_id: int
    url: str
    info: MediaInfo
    photos: bool
    created_at: float = field(default_factory=time.time)


class JobStore:
    def __init__(self, ttl: float = 1800) -> None:
        self._jobs: dict[str, Job] = {}
        self.ttl = ttl

    def add(self, user_id: int, url: str, info: MediaInfo) -> Job:
        job = Job(
            id=secrets.token_urlsafe(5),
            user_id=user_id,
            url=url,
            info=info,
            photos=photos_supported(url, info.extractor),
        )
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job and time.time() - job.created_at > self.ttl:
            self._jobs.pop(job_id, None)
            return None
        return job

    def cleanup(self) -> None:
        now = time.time()
        for job_id, job in list(self._jobs.items()):
            if now - job.created_at > self.ttl:
                self._jobs.pop(job_id, None)

    def __len__(self) -> int:
        return len(self._jobs)


class RateLimiter:
    def __init__(self, limit: int, window: float = 3600) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._calls = 0

    def check(self, user_id: int) -> tuple[bool, int]:
        """Return (allowed, minutes_to_wait)."""
        now = time.time()
        hits = self._hits[user_id]
        while hits and now - hits[0] > self.window:
            hits.popleft()

        self._calls += 1
        if self._calls % 500 == 0:
            self._prune(now)

        if len(hits) >= self.limit:
            wait = int((hits[0] + self.window - now) // 60) + 1
            return False, wait
        hits.append(now)
        return True, 0

    def _prune(self, now: float) -> None:
        for user_id, hits in list(self._hits.items()):
            if not hits or now - hits[-1] > self.window:
                self._hits.pop(user_id, None)


class UserGate:
    """Per-user and global concurrency limits."""

    def __init__(self, per_user: int, total: int) -> None:
        self.per_user = per_user
        self._counts: dict[int, int] = defaultdict(int)
        self._global = asyncio.Semaphore(total)

    @property
    def busy_global(self) -> bool:
        return self._global.locked()

    async def acquire(self, user_id: int) -> bool:
        if self._counts[user_id] >= self.per_user:
            return False
        self._counts[user_id] += 1
        await self._global.acquire()
        return True

    def release(self, user_id: int) -> None:
        count = self._counts.get(user_id, 0)
        if count <= 1:
            self._counts.pop(user_id, None)
        else:
            self._counts[user_id] = count - 1
        self._global.release()


class Stats:
    def __init__(self) -> None:
        self.started_at = time.time()
        self.downloads = 0
        self.failures = 0
        self.cancelled = 0
        self.users: set[int] = set()

    def seen(self, user_id: int) -> None:
        self.users.add(user_id)

    @property
    def uptime(self) -> str:
        seconds = int(time.time() - self.started_at)
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days:
            return f"{days} д {hours} ч"
        if hours:
            return f"{hours} ч {minutes} мин"
        return f"{minutes} мин"
