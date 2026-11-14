from __future__ import annotations

from .downloader import MediaInfo
from .utils import escape, shorten

START = """🐙 <b>OctoLoad</b> — качаю видео, музыку и фото по ссылке.

Кинь мне ссылку, например:
<code>https://youtu.be/dQw4w9WgXcQ</code>

Работаю с YouTube, TikTok, Instagram, SoundCloud, Pinterest, X, Reddit, VK и ещё тысячей сайтов. Выбери формат кнопками — всё остальное сделаю сам."""

HELP = """<b>Как пользоваться</b>
1. Отправь ссылку.
2. Нажми «🎬 Видео», «🎵 MP3» или «🖼 Фото».

<b>Команды</b>
/video &lt;ссылка&gt; — сразу видео
/audio &lt;ссылка&gt; — сразу MP3
/photo &lt;ссылка&gt; — только фото

<b>Что важно знать</b>
• Файл — до {limit} МБ, это лимит Telegram.
• Плейлисты не качаю: одна ссылка — один файл.
• Приватные посты требуют cookies владельца бота.
• Фото — до {photos} штук за раз.

Скачивай только то, на что у тебя есть права 🙂"""

SEND_LINK = """Кинь ссылку на видео, трек или пост — я разберусь.

Например: <code>https://www.tiktok.com/@octo/video/123</code>"""

PROBING = "🔎 Смотрю ссылку…"

QUEUE = "⏳ В очереди — сейчас качаю другие ссылки…"

CANCELLED = "❌ Отменено."

UPLOADING = "📤 Отправляю в Telegram…"

TOO_BIG = """😕 Файл получился {size} — это больше лимита Telegram ({limit} МБ).

Нажми «🎵 MP3» на карточке выше — звук точно влезет."""

CARD_FOOTER = "\n\nВыбери формат 👇"


def card(info: MediaInfo) -> str:
    parts = [f"🎬 <b>{escape(shorten(info.title, 180))}</b>"]
    details: list[str] = []
    if info.uploader:
        details.append(f"👤 {escape(shorten(info.uploader, 80))}")
    meta = []
    if info.duration:
        from .utils import human_duration

        meta.append(f"⏱ {human_duration(info.duration)}")
    meta.append(escape(info.site))
    details.append(" · ".join(meta))
    parts.append("\n" + "\n".join(details))
    return "\n".join(parts) + CARD_FOOTER


def error(text: str) -> str:
    return f"😕 {text}"


def queued(position: str = "") -> str:
    return "⏳ В очереди…" if not position else f"⏳ В очереди: {position}"


def busy() -> str:
    return "⚠️ У тебя уже идёт загрузка. Дождись её окончания 🙂"


def rate_limited(minutes: int) -> str:
    return f"⏸ Слишком часто. Попробуй через {minutes} мин."


def stats_text(
    *,
    uptime: str,
    downloads: int,
    failures: int,
    cancelled: int,
    users: int,
    jobs: int,
) -> str:
    return (
        "<b>🐙 OctoLoad — статистика</b>\n"
        f"⏱ Аптайм: {uptime}\n"
        f"✅ Скачано: {downloads}\n"
        f"❌ Ошибок: {failures}\n"
        f"🚫 Отмен: {cancelled}\n"
        f"👥 Пользователей: {users}\n"
        f"🧠 Активных карточек: {jobs}"
    )
