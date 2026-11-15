from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError
from aiogram.types import BotCommand, ErrorEvent, LinkPreviewOptions

from .config import Settings, load_settings
from .downloader import Downloader
from .handlers import router
from .jobs import JobStore, RateLimiter, Stats, UserGate

log = logging.getLogger("octo")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def _health_server(port: int) -> object:
    from aiohttp import web

    async def ok(_request: web.Request) -> web.Response:
        return web.Response(text="octo-load: ok")

    app = web.Application()
    app.router.add_get("/", ok)
    app.router.add_get("/healthz", ok)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("health endpoint on http://0.0.0.0:%s/healthz", port)
    return runner


async def run(settings: Settings) -> None:
    session = AiohttpSession()
    if settings.api_server:
        session = AiohttpSession(api=TelegramAPIServer.from_base(settings.api_server))
        log.info("using local Bot API server: %s", settings.api_server)

    bot = Bot(
        settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    jobs = JobStore(ttl=1800)
    stats = Stats()
    rate = RateLimiter(settings.rate_limit_per_hour)
    gate = UserGate(settings.per_user_concurrent, settings.max_concurrent)
    downloader = Downloader(settings)

    dp = Dispatcher()
    dp["settings"] = settings
    dp["jobs"] = jobs
    dp["stats"] = stats
    dp["rate"] = rate
    dp["gate"] = gate
    dp["downloader"] = downloader
    dp.include_router(router)

    health = None
    if settings.port:
        health = await _health_server(settings.port)

    public_url = settings.self_url or os.getenv("RENDER_EXTERNAL_URL", "").strip() or None
    keepalive_task = (
        asyncio.create_task(_keepalive_loop(public_url)) if public_url else None
    )
    cleanup_task = asyncio.create_task(_cleanup_loop(jobs))

    @dp.startup()
    async def on_startup() -> None:
        me = await bot.get_me()
        _cleanup_stale_jobs(settings)
        log.info(
            "started as @%s (id=%s), upload limit %s MB, jobs dir %s",
            me.username,
            me.id,
            settings.upload_limit_mb,
            settings.work_dir,
        )
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Запустить бота"),
                BotCommand(command="help", description="Как пользоваться"),
                BotCommand(command="video", description="Скачать видео"),
                BotCommand(command="audio", description="Скачать MP3"),
                BotCommand(command="photo", description="Скачать фото"),
            ]
        )

    @dp.shutdown()
    async def on_shutdown() -> None:
        await downloader.close()

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.exception("update failed: %s", event.exception, exc_info=event.exception)
        message = event.update.message or (
            event.update.callback_query.message if event.update.callback_query else None
        )
        if message is not None:
            try:
                await message.reply(
                    "😵 Упс, что-то пошло не так. Попробуй ещё раз.",
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            except Exception as exc:  # noqa: BLE001 - best effort only
                log.debug("could not notify user about error: %s", exc)
        return True

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            close_bot_session=False,
        )
    except TelegramConflictError:
        log.error(
            "Another instance of the bot is already running with this token. "
            "Stop it (or the duplicate deployment) and start again."
        )
        raise SystemExit(2) from None
    except TelegramUnauthorizedError:
        log.error(
            "Telegram rejected BOT_TOKEN. Check the token in .env / the environment "
            "(and revoke it in @BotFather if it leaked)."
        )
        raise SystemExit(3) from None
    finally:
        cleanup_task.cancel()
        if keepalive_task is not None:
            keepalive_task.cancel()
        if health is not None:
            await health.cleanup()  # type: ignore[attr-defined]
        await bot.session.close()
        log.info("stopped")


async def _keepalive_loop(base_url: str) -> None:
    """Ping our own public health endpoint so free PaaS instances stay awake."""
    import aiohttp

    target = base_url.rstrip("/") + "/healthz"
    log.info("self-ping enabled: %s every 10 min", target)
    while True:
        await asyncio.sleep(600)
        try:
            async with (
                aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as session,
                session.get(target) as response,
            ):
                await response.read()
                log.debug("self-ping: HTTP %s", response.status)
        except Exception as exc:  # noqa: BLE001 - keep-alive must never crash
            log.debug("self-ping failed: %s", exc)


async def _cleanup_loop(jobs: JobStore) -> None:
    while True:
        await asyncio.sleep(300)
        jobs.cleanup()


def _cleanup_stale_jobs(settings: Settings) -> None:
    """Remove temp dirs left behind by a crash or an abrupt restart."""
    cutoff = time.time() - 3600
    for path in settings.work_dir.glob("job-*"):
        try:
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


async def main() -> None:
    settings = load_settings()
    _configure_logging(settings.log_level)
    await run(settings)


if __name__ == "__main__":
    asyncio.run(main())
