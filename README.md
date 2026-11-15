# 🐙 OctoLoad

Telegram-бот, который скачивает **видео, музыку и фото по ссылке**: YouTube, TikTok, Instagram, SoundCloud, Pinterest, X/Twitter, Reddit, VK и ещё больше тысячи сайтов.

<p align="center">
  <img src="assets/logo.png" width="180" alt="OctoLoad">
</p>

## Что умеет

- 🔗 Кидаешь ссылку → бот показывает карточку с названием, автором и длительностью.
- 🎬 **Видео** — лучшее качество, которое влезает в лимит Telegram (H.264/MP4, со звуком).
- 🎵 **MP3** — вытаскивает звук и отправляет аудио с тегами.
- 🖼 **Фото** — галереи Pinterest, Instagram, TikTok-слайдшоу и других сайтов (до 10 штук за раз).
- 🖼 Прямые ссылки на картинки (`.jpg`, `.png`, `.webp`) тоже понимаю.
- 📊 Прогресс скачивания, скорость и кнопка отмены.
- 🧵 Очередь и лимиты: 3 загрузки одновременно, 1 на пользователя, 20 ссылок в час.
- 🛡 Проверка ссылок (никаких `localhost`/приватных IP), безопасные имена файлов, автоочистка временных папок.

## Деплой в один клик

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/octomood/octo-load)

Бесплатный Render: 512 МБ RAM, 720p, самопинг раз в 10 минут (не засыпает). Нужен только аккаунт Render — карта не требуется. Подробности и альтернативы — в [DEPLOY.md](DEPLOY.md).

## Быстрый старт

```bash
cd octo-load
cp .env.example .env
# вставь токен от @BotFather в BOT_TOKEN
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app
```

Для автозапуска вместе с компьютером (Linux, systemd):

```bash
bash scripts/install-local.sh
```

Нужен `ffmpeg` в `PATH` (для склейки видео и конвертации в MP3):

```bash
# Ubuntu/Debian
sudo apt install ffmpeg
# Arch
sudo pacman -S ffmpeg
# macOS
brew install ffmpeg
```

## Настройка бота в @BotFather

1. `/newbot` → имя **OctoLoad** → username, например `octo_load_bot` или `octoload_bot`.
2. `/setdescription` → «Скачиваю видео, музыку и фото по ссылке. Кинь ссылку — выбери формат.»
3. `/setabouttext` → «🐙 Видео, музыка и фото из YouTube, TikTok, Pinterest, SoundCloud и других сайтов.»
4. `/setuserpic` → загрузи `assets/logo.png`.
5. `/setcommands` → список ниже (бот также ставит его сам при старте).

```
start - Запустить бота
help - Как пользоваться
video - Скачать видео
audio - Скачать MP3
photo - Скачать фото
```

## Команды

| Команда | Что делает |
|---|---|
| `/start` | Приветствие и пример ссылки |
| `/help` | Инструкция и лимиты |
| `/video <ссылка>` | Сразу скачать видео |
| `/audio <ссылка>` | Сразу скачать MP3 |
| `/photo <ссылка>` | Сразу скачать фото |
| `/id` | Показать твой Telegram ID |
| `/stats` | Статистика (только для `ADMIN_IDS`) |

## Переменные окружения

Все настройки — в `.env` (шаблон: `.env.example`).

| Переменная | По умолчанию | Зачем |
|---|---|---|
| `BOT_TOKEN` | — | Токен от @BotFather, обязателен |
| `ADMIN_IDS` | пусто | Твои ID через запятую для `/stats` |
| `UPLOAD_LIMIT_MB` | `50` | Лимит файла; больше 50 — только с локальным Bot API |
| `MAX_CONCURRENT` | `3` | Сколько загрузок идёт одновременно |
| `PER_USER_CONCURRENT` | `1` | Сколько загрузок на одного пользователя |
| `RATE_LIMIT_PER_HOUR` | `20` | Ссылок в час на пользователя |
| `MAX_PHOTOS` | `10` | Фото в одной галерее (максимум Telegram — 10) |
| `WORK_DIR` | `./data` | Временные файлы |
| `COOKIES_FILE` | пусто | `cookies.txt` для приватного/возрастного контента |
| `PROXY` | пусто | Прокси для yt-dlp и gallery-dl |
| `API_SERVER` | пусто | Локальный Bot API (`http://127.0.0.1:8081`) |
| `PORT` | пусто | Порт health-эндпоинта `/healthz` (нужен на Render) |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `YTDLP_EXTRA_ARGS` | пусто | Доп. аргументы yt-dlp |

## Хостинг: где держать бесплатно

Подробная инструкция и команды — в [DEPLOY.md](DEPLOY.md). Коротко:

| Вариант | Цена | Плюсы | Минусы |
|---|---|---|---|
| **Oracle Cloud Always Free** | 0 ₽ навсегда | 2 vCPU / 12 ГБ ARM, 10 ТБ трафика, реальный 24/7 | Нужна карта для верификации, бывает «out of capacity» |
| **Render Free** | 0 ₽ | Без карты, деплой из GitHub | 0.1 CPU / 512 МБ, засыпает через 15 мин без пинга, 750 ч/мес |
| **Свой ПК / Raspberry Pi** | 0 ₽ | Всё под контролем | Работает, только пока включён компьютер |
| Google Cloud e2-micro | 0 ₽ | 1 vCPU / 1 ГБ всегда | Всего 1 ГБ исходящего трафика в месяц — для видео не хватит |

**Вывод:** для «бесплатно и навсегда, 24/7» лучший вариант — Oracle Cloud Always Free. Render — если карты нет и хватает одного пользователя.

## Лимиты Telegram

- Облачный Bot API разрешает ботам отправлять файлы **до 50 МБ**. Бот подбирает формат под лимит; если не влезло — предлагает MP3.
- Хочешь **до 2 ГБ** — подними локальный Bot API server и укажи `API_SERVER` + `UPLOAD_LIMIT_MB=2000` (инструкция в DEPLOY.md).
- Приватные посты (Instagram, возрастные YouTube) требуют `cookies.txt` владельца бота. Без них бот честно скажет, что нужна авторизация.

## Поддерживаемые сайты

Всё, что умеет [yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md): YouTube, Shorts, TikTok, Instagram Reels, SoundCloud, VK, X/Twitter, Reddit, Facebook, Twitch, Vimeo, Rutube, Дзен и сотни других. Фото-галереи — через [gallery-dl](https://github.com/mikf/gallery-dl): Pinterest, Instagram, TikTok, Flickr, Tumblr, ArtStation, Pixiv и т.д.

Плейлисты не скачиваются: одна ссылка — один файл.

## Как это устроено

```
app/
├── main.py        # запуск, polling, health-сервер, graceful shutdown
├── handlers.py    # команды, карточка ссылки, кнопки, прогресс, отправка
├── downloader.py  # yt-dlp / gallery-dl, парсинг прогресса, ошибки, фото
├── jobs.py        # карточки ссылок, лимиты, очередь, статистика
├── texts.py       # все тексты бота (RU)
├── config.py      # настройки из env
└── utils.py       # форматирование, проверка URL
```

- `yt-dlp` и `gallery-dl` запускаются отдельными процессами — бот не блокируется и может убить зависшую загрузку.
- Прогресс читается из `--progress-template` и редактируется не чаще раза в ~2 секунды.
- Каждая загрузка — своя временная папка, которая удаляется в `finally`.
- Ссылки проверяются на приватные IP (защита от SSRF).
- Токен нигде не логируется.

## Тесты

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Проверка реального скачивания тем же кодом, что и в боте:

```bash
.venv/bin/python scripts/selftest.py "https://youtu.be/..." video
.venv/bin/python scripts/selftest.py "https://soundcloud.com/..." audio
.venv/bin/python scripts/selftest.py "https://www.pinterest.com/pin/..." photos
```

## Частые проблемы

| Симптом | Причина и решение |
|---|---|
| Бот молчит | Неверный `BOT_TOKEN`, либо запущено два экземпляра (`409 Conflict` в логах) |
| «Сайт блокирует скачивание» | IP хостинга в блоке (TikTok/Reddit/Instagram). Помогает `PROXY` или cookies |
| «Контент приватный» | Нужен `COOKIES_FILE` |
| «Файл больше лимита» | Жми MP3 или подними локальный Bot API |
| Перестал качать YouTube | Обнови extractor: `pip install -U yt-dlp` и перезапусти бота |
| `ERROR: ffmpeg not found` | Установи ffmpeg (в Docker он уже внутри) |
| Pinterest качается долго | Pinterest throttлит серверные IP; помогает `PROXY` или cookies |

## Дисклеймер

Бот — инструмент. Скачивай только то, на что у тебя есть права, и соблюдай правила сайтов и авторские права. Автор не несёт ответственности за использование бота третьими лицами.

## Лицензия

MIT — см. [LICENSE](LICENSE).
