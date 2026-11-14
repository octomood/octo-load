"""A tiny fake Telegram Bot API used by scripts/e2e_local.py.

Only the handful of methods OctoLoad calls are implemented.
"""

from __future__ import annotations

import asyncio
import json
import time

from aiohttp import web

TOKEN = "123456:test-token"
CHAT_ID = 42
BOT_INFO = {
    "id": 1,
    "is_bot": True,
    "first_name": "OctoLoad",
    "username": "octo_test_bot",
    "can_join_groups": True,
    "can_read_all_group_messages": False,
    "supports_inline_queries": False,
}


def _message(text: str = "", message_id: int = 1, **extra: object) -> dict:
    payload = {
        "message_id": message_id,
        "date": int(time.time()),
        "chat": {"id": CHAT_ID, "type": "private", "first_name": "Tester"},
        "from": {"id": CHAT_ID, "is_bot": False, "first_name": "Tester"},
        "text": text,
    }
    payload.update(extra)
    return payload


class FakeBotAPI:
    def __init__(self, url: str, port: int = 8081, kind: str = "v") -> None:
        self.url = url
        self.port = port
        self.kind = kind
        self.updates: list[dict] = []
        self.calls: list[str] = []
        self.media_method: str | None = None
        self.media_bytes = 0
        self.media_seen = asyncio.Event()
        self.error: str | None = None
        self._offset = 0
        self._callback_queued = False
        self._next_update_id = 2
        self._runner: web.AppRunner | None = None

    def queue_update(self, update: dict) -> None:
        self.updates.append(update)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/bot{token}/{method}", self._handle)
        app.router.add_get("/bot{token}/{method}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await site.start()

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _handle(self, request: web.Request) -> web.Response:
        token = request.match_info["token"]
        method = request.match_info["method"]
        if token != TOKEN:
            return web.json_response({"ok": False, "error_code": 401}, status=401)

        self.calls.append(method)
        if method != "getUpdates":
            print(f"  [api] {method}")

        if method == "getMe":
            return web.json_response({"ok": True, "result": BOT_INFO})

        if method == "getUpdates":
            return web.json_response({"ok": True, "result": await self._get_updates(request)})

        if method in {"sendVideo", "sendAudio", "sendPhoto", "sendMediaGroup", "sendDocument"}:
            received = await self._drain(request)
            self.media_method = method
            self.media_bytes = received
            self.media_seen.set()
            result: object = _message("media", message_id=10)
            if method == "sendMediaGroup":
                result = [_message("media", message_id=10)]
            return web.json_response({"ok": True, "result": result})

        if method in {"sendMessage", "editMessageText", "editMessageCaption"}:
            payload = await self._json_or_form(request)
            if method == "editMessageText":
                self._maybe_queue_video_callback(payload)
            return web.json_response(
                {"ok": True, "result": _message("sent", message_id=2)}
            )

        if method in {"answerCallbackQuery", "deleteMessage", "sendChatAction", "setMyCommands"}:
            await request.read()
            return web.json_response({"ok": True, "result": True})

        await request.read()
        return web.json_response({"ok": True, "result": True})

    async def _get_updates(self, request: web.Request) -> list[dict]:
        payload = await self._json_or_form(request)
        offset = int(payload.get("offset") or 0)
        for _ in range(20):
            pending = [update for update in self.updates if update["update_id"] >= offset]
            if pending:
                print(f"  [api] getUpdates offset={offset} -> {pending[0]['update_id']}")
                return pending[:1]
            await asyncio.sleep(0.25)
        return []

    def _maybe_queue_video_callback(self, payload: dict) -> None:
        if self._callback_queued:
            return
        markup = payload.get("reply_markup")
        if isinstance(markup, str):
            try:
                markup = json.loads(markup)
            except json.JSONDecodeError:
                return
        if not isinstance(markup, dict):
            return
        for row in markup.get("inline_keyboard", []):
            for button in row:
                data = button.get("callback_data", "")
                if data.startswith(f"octo:{self.kind}:"):
                    self._callback_queued = True
                    print(f"  [api] queueing callback {data}")
                    self.queue_update(
                        {
                            "update_id": self._next_update_id,
                            "callback_query": {
                                "id": "cb-1",
                                "from": {
                                    "id": CHAT_ID,
                                    "is_bot": False,
                                    "first_name": "Tester",
                                },
                                "chat_instance": "1",
                                "data": data,
                                "message": _message("card", message_id=2),
                            },
                        }
                    )
                    self._next_update_id += 1
                    return

    @staticmethod
    async def _json_or_form(request: web.Request) -> dict:
        try:
            if request.content_type == "application/json":
                return await request.json()
            return dict(await request.post())
        except (json.JSONDecodeError, ValueError):
            return {}

    @staticmethod
    async def _drain(request: web.Request) -> int:
        total = 0
        async for chunk in request.content.iter_chunked(256 * 1024):
            total += len(chunk)
        return total
