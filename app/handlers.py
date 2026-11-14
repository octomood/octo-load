from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    LinkPreviewOptions,
    Message,
)

from . import texts
from .config import Settings
from .downloader import DownloadCancelled, Downloader, MediaInfo, TooLarge, UserError
from .jobs import Job, JobStore, RateLimiter, Stats, UserGate
from .utils import (
    escape,
    extract_url,
    human_duration,
    human_size,
    human_speed,
    progress_bar,
    shorten,
    url_rejection_reason,
)

log = logging.getLogger(__name__)
router = Router(name="octo")

KINDS = {"v": "video", "a": "audio", "p": "photos"}
HEADERS = {
    "video": "⬇️ Скачиваю видео…",
    "audio": "⬇️ Скачиваю звук…",
    "photos": "🖼 Скачиваю фото…",
}


def card_keyboard(job: Job) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🎬 Видео", callback_data=f"octo:v:{job.id}"),
            InlineKeyboardButton(text="🎵 MP3", callback_data=f"octo:a:{job.id}"),
        ]
    ]
    if job.photos:
        rows.append(
            [InlineKeyboardButton(text="🖼 Фото", callback_data=f"octo:p:{job.id}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard(job_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✖️ Отмена", callback_data=f"octo:x:{job_id}")]
        ]
    )


async def safe_edit(
    message: Message,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.edit_text(
            text,
            reply_markup=markup,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            await message.edit_text(text, reply_markup=markup)
        except TelegramBadRequest:
            pass
    except TelegramBadRequest as exc:
        log.debug("edit skipped: %s", exc)


class ProgressView:
    """Throttled progress updates for a single download."""

    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        message_id: int,
        header: str,
        job_id: str,
        with_cancel: bool = True,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.header = header
        self.job_id = job_id
        self.with_cancel = with_cancel
        self.last_edit = 0.0
        self.last_time = time.monotonic()
        self.last_bytes = 0
        self.speed = 0.0
        self.finished = False

    async def __call__(self, done: int, total: int | None) -> None:
        now = time.monotonic()
        complete = bool(total) and done >= total
        if not complete and now - self.last_edit < 2.2:
            return
        if self.finished:
            return
        self.finished = complete

        delta_t = now - self.last_time
        if delta_t > 0.15 and done >= self.last_bytes:
            instant = (done - self.last_bytes) / delta_t
            self.speed = instant if not self.speed else self.speed * 0.6 + instant * 0.4
        self.last_time, self.last_bytes = now, done
        self.last_edit = now

        try:
            await self.bot.edit_message_text(
                self._render(done, total),
                chat_id=self.chat_id,
                message_id=self.message_id,
                reply_markup=cancel_keyboard(self.job_id) if self.with_cancel else None,
            )
        except TelegramRetryAfter as exc:
            log.debug("progress flood wait %s", exc.retry_after)
        except TelegramBadRequest as exc:
            log.debug("progress edit skipped: %s", exc)

    def _render(self, done: int, total: int | None) -> str:
        if total and done >= total * 0.995:
            header = "🎛 Собираю файл…"
        else:
            header = self.header

        if total:
            percent = min(100.0, done / total * 100)
            lines = [
                f"<b>{header}</b>",
                f"{progress_bar(percent)} {percent:.0f}%",
            ]
            stats = f"{human_size(done)} / {human_size(total)}"
            if self.speed:
                stats += f" · {human_speed(self.speed)}"
                remaining = (total - done) / self.speed if self.speed > 0 else 0
                if 0 < remaining < 3600:
                    stats += f" · {human_duration(remaining)}"
            lines.append(stats)
            return "\n".join(lines)

        return f"<b>{header}</b>\n{human_size(done)} скачано"


def _caption(info: MediaInfo) -> str:
    text = f"🐙 <b>{escape(shorten(info.title, 200))}</b>"
    if info.uploader:
        text += f"\n👤 {escape(shorten(info.uploader, 90))}"
    return text


async def _send_result(
    bot: Bot,
    chat_id: int,
    path: Path | list[Path],
    kind: str,
    job: Job,
) -> None:
    info = job.info
    if kind == "video":
        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)
        await bot.send_video(
            chat_id,
            FSInputFile(path) if isinstance(path, Path) else FSInputFile(path[0]),
            caption=_caption(info),
            supports_streaming=True,
            duration=info.duration or 0,
        )
    elif kind == "audio":
        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_VOICE)
        await bot.send_audio(
            chat_id,
            FSInputFile(path) if isinstance(path, Path) else FSInputFile(path[0]),
            caption=_caption(info),
            title=shorten(info.title, 64),
            performer=shorten(info.uploader or "", 64) or None,
            duration=info.duration or 0,
        )
    else:
        photos = [path] if isinstance(path, Path) else list(path)
        if len(photos) == 1:
            await bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
            await bot.send_photo(chat_id, FSInputFile(photos[0]), caption=_caption(info))
        else:
            media = [
                InputMediaPhoto(
                    media=FSInputFile(photo),
                    caption=_caption(info) if index == 0 else None,
                )
                for index, photo in enumerate(photos)
            ]
            await bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
            await bot.send_media_group(chat_id, media)


async def _download_and_send(
    *,
    bot: Bot,
    chat_id: int,
    job: Job,
    kind: str,
    status: Message,
    settings: Settings,
    downloader: Downloader,
    gate: UserGate,
    stats: Stats,
) -> None:
    if not await gate.acquire(job.user_id):
        await safe_edit(status, texts.busy())
        return

    dest = Path(tempfile.mkdtemp(dir=settings.work_dir, prefix="job-"))
    view = ProgressView(
        bot,
        chat_id,
        status.message_id,
        HEADERS[kind],
        job.id,
        with_cancel=kind != "photos",
    )

    try:
        if kind == "photos":
            await safe_edit(status, HEADERS[kind])
            path: Path | list[Path] = await downloader.download_photos(
                job.url, dest, job_id=job.id, limit=settings.max_photos
            )
        elif kind == "audio":
            path = await downloader.download_audio(
                job.url, dest, job_id=job.id, on_progress=view
            )
        else:
            path = await downloader.download_video(
                job.url, dest, job_id=job.id, on_progress=view
            )

        await safe_edit(status, texts.UPLOADING)
        await _send_result(bot, chat_id, path, kind, job)
        stats.downloads += 1
        try:
            await status.delete()
        except TelegramBadRequest:
            pass
    except DownloadCancelled:
        stats.cancelled += 1
        await safe_edit(status, texts.CANCELLED)
    except TooLarge as exc:
        stats.failures += 1
        await safe_edit(
            status,
            texts.TOO_BIG.format(
                size=human_size(exc.size),
                limit=settings.upload_limit_mb,
            ),
        )
    except UserError as exc:
        stats.failures += 1
        await safe_edit(status, texts.error(str(exc)))
    except TelegramBadRequest as exc:
        stats.failures += 1
        if "too large" in str(exc).lower():
            await safe_edit(
                status,
                texts.TOO_BIG.format(
                    size="больше лимита",
                    limit=settings.upload_limit_mb,
                ),
            )
        else:
            log.exception("telegram send failed")
            await safe_edit(
                status, texts.error("Telegram не принял файл. Попробуй другой формат.")
            )
    except Exception:
        stats.failures += 1
        log.exception("download failed for %s", job.url)
        await safe_edit(
            status, texts.error("Что-то сломалось на моей стороне. Попробуй ещё раз.")
        )
    finally:
        gate.release(job.user_id)
        shutil.rmtree(dest, ignore_errors=True)


async def _handle_link(
    message: Message,
    *,
    url: str,
    kind: str | None,
    settings: Settings,
    downloader: Downloader,
    jobs: JobStore,
    stats: Stats,
    rate: RateLimiter,
    gate: UserGate,
) -> None:
    user = message.from_user
    if user is None:
        return
    stats.seen(user.id)

    allowed, minutes = rate.check(user.id)
    if not allowed:
        await message.reply(texts.rate_limited(minutes))
        return

    reason = await url_rejection_reason(url)
    if reason:
        await message.reply(texts.error(reason))
        return

    status = await message.answer(texts.PROBING)
    try:
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        info = await downloader.probe(url)
    except UserError as exc:
        await safe_edit(status, texts.error(str(exc)))
        return
    except Exception:
        log.exception("probe failed for %s", url)
        await safe_edit(status, texts.error("Не смог прочитать ссылку. Попробуй ещё раз."))
        return

    job = jobs.add(user.id, url, info)

    if kind is None:
        await safe_edit(status, texts.card(info), card_keyboard(job))
        return

    await _download_and_send(
        bot=message.bot,
        chat_id=message.chat.id,
        job=job,
        kind=kind,
        status=status,
        settings=settings,
        downloader=downloader,
        gate=gate,
        stats=stats,
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        texts.START,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📖 Помощь", callback_data="octo:help")]
            ]
        ),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    await message.answer(
        texts.HELP.format(
            limit=settings.upload_limit_mb,
            photos=settings.max_photos,
        ),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@router.message(Command("video", "audio", "photo"))
async def cmd_direct(
    message: Message,
    command: CommandObject,
    settings: Settings,
    downloader: Downloader,
    jobs: JobStore,
    stats: Stats,
    rate: RateLimiter,
    gate: UserGate,
) -> None:
    kind = {"video": "video", "audio": "audio", "photo": "photos"}[command.command]
    url = extract_url(command.args or "")
    if not url:
        await message.reply(
            f"Дай ссылку: <code>/{command.command} https://…</code>",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return
    await _handle_link(
        message,
        url=url,
        kind=kind,
        settings=settings,
        downloader=downloader,
        jobs=jobs,
        stats=stats,
        rate=rate,
        gate=gate,
    )


@router.message(F.text.regexp(r"https?://") & ~F.text.startswith("/"))
async def on_link(
    message: Message,
    settings: Settings,
    downloader: Downloader,
    jobs: JobStore,
    stats: Stats,
    rate: RateLimiter,
    gate: UserGate,
) -> None:
    url = extract_url(message.text or "")
    if not url:
        await message.reply(texts.SEND_LINK)
        return
    await _handle_link(
        message,
        url=url,
        kind=None,
        settings=settings,
        downloader=downloader,
        jobs=jobs,
        stats=stats,
        rate=rate,
        gate=gate,
    )


@router.message(F.text)
async def on_text(message: Message) -> None:
    await message.reply(
        texts.SEND_LINK,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@router.callback_query(F.data == "octo:help")
async def cb_help(callback: CallbackQuery, settings: Settings) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            texts.HELP.format(
                limit=settings.upload_limit_mb,
                photos=settings.max_photos,
            )
        )


@router.callback_query(F.data.startswith("octo:"))
async def on_download_button(
    callback: CallbackQuery,
    settings: Settings,
    downloader: Downloader,
    jobs: JobStore,
    stats: Stats,
    gate: UserGate,
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer()
        return
    _, code, job_id = parts

    job = jobs.get(job_id)
    if job is None:
        await callback.answer("Ссылка устарела — кинь её заново 🙂", show_alert=True)
        return
    if callback.from_user.id != job.user_id:
        await callback.answer("Это чужая ссылка 🙂", show_alert=True)
        return

    if code == "x":
        stopped = await downloader.cancel(job_id)
        await callback.answer("Отменяю…" if stopped else "Уже нечего отменять")
        return

    kind = KINDS.get(code)
    if kind is None:
        await callback.answer()
        return

    if kind == "photos" and not job.photos:
        await callback.answer("На этом сайте нет фото 🙂", show_alert=True)
        return

    await callback.answer()

    chat_id = callback.message.chat.id if callback.message else callback.from_user.id
    status = await callback.bot.send_message(chat_id, "⏳ Готовлю загрузку…")
    await _download_and_send(
        bot=callback.bot,
        chat_id=chat_id,
        job=job,
        kind=kind,
        status=status,
        settings=settings,
        downloader=downloader,
        gate=gate,
        stats=stats,
    )


@router.message(Command("stats"))
async def cmd_stats(
    message: Message,
    settings: Settings,
    jobs: JobStore,
    stats: Stats,
) -> None:
    if message.from_user is None or message.from_user.id not in settings.admins:
        return
    await message.answer(
        texts.stats_text(
            uptime=stats.uptime,
            downloads=stats.downloads,
            failures=stats.failures,
            cancelled=stats.cancelled,
            users=len(stats.users),
            jobs=len(jobs),
        )
    )


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    if message.from_user:
        await message.reply(f"Твой ID: <code>{message.from_user.id}</code>")
