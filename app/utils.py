from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import unquote, urlparse

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING = ".,;:!?»…\"'"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def extract_url(text: str) -> str | None:
    match = _URL_RE.search(text or "")
    if not match:
        return None
    url = match.group(0)
    # Keep balanced parentheses inside the URL (Wikipedia-style links), strip the rest.
    while url and url[-1] in _TRAILING:
        url = url[:-1]
    while url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url


def is_image_url(url: str) -> bool:
    return Path(unquote(urlparse(url).path)).suffix.lower() in IMAGE_SUFFIXES


def human_size(num: float | None) -> str:
    if not num or num < 0:
        return "0 Б"
    units = ("Б", "КБ", "МБ", "ГБ", "ТБ")
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "Б":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}".replace(".", ",")
        value /= 1024
    return f"{value:.1f} ТБ"


def human_duration(seconds: float | None) -> str:
    if not seconds or seconds < 0:
        return "—"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def human_speed(bps: float | None) -> str:
    if not bps or bps <= 0:
        return ""
    return f"{human_size(bps)}/с"


def progress_bar(percent: float, width: int = 10) -> str:
    percent = max(0.0, min(100.0, percent))
    filled = round(percent / 100 * width)
    return "▰" * filled + "▱" * (width - filled)


def escape(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def shorten(text: str | None, limit: int = 120) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


async def url_rejection_reason(url: str) -> str | None:
    """Return a human-readable reason when the URL must not be fetched."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return "Ссылка должна начинаться с http:// или https://"
    host = parsed.hostname
    if not host:
        return "В ссылке нет адреса сайта"
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return "Локальные адреса не поддерживаются"

    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return "Не удалось найти этот сайт — проверь ссылку"

    if not infos:
        return "Не удалось найти этот сайт — проверь ссылку"

    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if not address.is_global:
            return "Приватные и локальные адреса не поддерживаются"

    return None
