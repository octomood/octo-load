# Деплой OctoLoad

Три рабочих варианта: **Oracle Cloud Always Free** (рекомендую), **Render Free** (без карты) и **свой ПК**. Ниже — точные команды.

---

## 1. Oracle Cloud Always Free — бесплатно навсегда, 24/7

Что даёт Always Free (по официальной документации Oracle на 2026 год):

- **2 OCPU / 12 ГБ RAM** (ARM Ampere A1, суммарно),
- 200 ГБ дискового пространства,
- **10 ТБ исходящего трафика в месяц**,
- 2 маленьких AMD-инстанса (1 ГБ RAM) — боту не хватит, бери ARM.

Нужна банковская карта для верификации (списывают и возвращают ~$1). Карта не обязана быть «зарплатной» — подойдёт обычная дебетовая.

### 1.1. Создать аккаунт и VM

1. Зарегистрируйся на [cloud.oracle.com/free](https://www.oracle.com/cloud/free/), выбери **домашний регион** поближе (Франкфурт/Амстердам/Стокгольм) — Always Free работает только в домашнем регионе.
2. **Compute → Instances → Create instance**:
   - Name: `octo-load`
   - Image: **Ubuntu 24.04** (aarch64)
   - Shape: **Ampere → VM.Standard.A1.Flex**, 2 OCPU, 12 GB RAM
   - Boot volume: 50 GB
   - Public IPv4: **Assign**
   - SSH keys: сгенерируй новую пару или вставь свой публичный ключ
3. Если пишет **«Out of host capacity»** — попробуй другое Availability Domain, другой регион или повтори через пару часов. Это нормальная проблема бесплатных ARM-инстансов.
4. Дождись статуса **Running** и запиши публичный IP.

### 1.2. Установить Docker на сервер

```bash
ssh -i ~/.ssh/octo.key ubuntu@<IP>

curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
```

### 1.3. Залить проект и запустить

На **своём компьютере**, из папки с проектом:

```bash
scp -i ~/.ssh/octo.key -r octo-load ubuntu@<IP>:~/
```

На сервере:

```bash
cd ~/octo-load
cp .env.example .env
nano .env        # вставь BOT_TOKEN и свой ADMIN_IDS (узнать ID: /id в боте)

docker compose up -d --build
docker compose logs -f
```

В логах должно появиться:

```
started as @octo_load_bot (id=...) upload limit 50 MB
```

Проверь бота в Telegram: `/start` → кинь ссылку.

> Порты открывать не нужно: бот сам ходит в Telegram по HTTPS. SSH-порт 22 в Oracle открыт по умолчанию.

### 1.4. Важно про «простаивающие» инстансы

Oracle может забрать Always Free инстанс, если за 7 дней он простаивает: 95-й перцентиль CPU < 20%, сеть < 20%, память < 20%. У бота с живыми пользователями сеть и CPU активны, но 100% гарантии нет.

Если это критично:

- если бот будет реально использоваться, риск реклейма небольшой: скачивания дают и сеть, и CPU;
- для полного спокойствия можно перейти на **Pay As You Go** — Always Free-лимиты при этом сохраняются и остаются бесплатными.

### 1.5. Обновления (важно!)

YouTube и TikTok регулярно ломают старые extractor'ы. Раз в неделю:

```bash
cd ~/octo-load
docker compose build --pull --no-cache
docker compose up -d
```

Можно повесить в cron:

```bash
(crontab -l 2>/dev/null; echo "0 4 * * 1 cd $HOME/octo-load && docker compose build --pull --no-cache && docker compose up -d >> $HOME/octo-update.log 2>&1") | crontab -
```

### 1.6. Вариант без Docker (systemd)

На сервере, из папки проекта:

```bash
sudo bash scripts/install.sh
sudo nano /etc/octo-load.env     # BOT_TOKEN
sudo systemctl restart octo-load
journalctl -u octo-load -f
```

Скрипт создаст пользователя `octo`, virtualenv, systemd-юнит и еженедельный cron на обновление yt-dlp.

---

## 2. Render Free — без карты, но с оговорками

Free-план Render: **0.1 CPU / 512 МБ RAM**, засыпает через 15 минут без входящего трафика, 750 часов в месяц. Для личного бота хватает, для десятков пользователей — нет.

1. Залей проект в GitHub:

   ```bash
   cd octo-load
   git init
   git add .
   git commit -m "OctoLoad"
   git branch -M main
   git remote add origin git@github.com:<ты>/octo-load.git
   git push -u origin main
   ```

2. [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint** → выбери репозиторий. Render увидит `render.yaml` и создаст web service.
3. Впиши `BOT_TOKEN` (и при желании `ADMIN_IDS`) → **Apply**.
4. Дождись деплоя, проверь логи: `started as @...`.
5. **Обязательно** подними keep-alive, иначе Render усыпит бота через 15 минут:
   - зарегистрируйся на [cron-job.org](https://cron-job.org) (бесплатно);
   - создай задачу: URL `https://<имя-сервиса>.onrender.com/healthz`, интервал **10 минут**.

Ограничения Render Free, о которых стоит знать:

- 750 часов/мес: 24/7 — это ~730 часов, впритык;
- Render может перезапускать сервис и блокировать высокий исходящий трафик;
- диск эфемерный (боту он не нужен — файлы временные);
- 512 МБ RAM: большие видео и 4K-склейка могут падать по памяти.

Если бот начнёт тормозить — переноси на Oracle.

---

## 3. Свой ПК / Raspberry Pi (systemd --user)

Работает, пока компьютер включён.

```bash
cd ~/octo-load
cp .env.example .env
nano .env                      # BOT_TOKEN

bash scripts/install-local.sh  # venv + systemd --user + автозапуск
systemctl --user status octo-load
journalctl --user -u octo-load -f
```

Скрипт включает `loginctl enable-linger`, поэтому бот стартует после входа в систему и живёт без открытого терминала. Он же ставит еженедельный таймер обновления экстракторов:

```bash
systemctl --user list-timers octo-load-update.timer
systemctl --user start octo-load-update.service   # обновить прямо сейчас
```

---

## 4. Большие файлы: локальный Bot API (до 2 ГБ)

Облачный Telegram Bot API режет загрузку ботом до **50 МБ**. Обход — свой [telegram-bot-api](https://github.com/tdlib/telegram-bot-api) в локальном режиме.

```bash
# на сервере: зависимости для сборки
sudo apt install -y cmake g++ git zlib1g-dev libssl-dev

git clone --recursive https://github.com/tdlib/telegram-bot-api.git
cd telegram-bot-api
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
sudo install -m 755 build/telegram-bot-api /usr/local/bin/
```

`api_id` и `api_hash` возьми на [my.telegram.org](https://my.telegram.org) → API development tools.

```bash
telegram-bot-api \
  --api-id=<API_ID> --api-hash=<API_HASH> \
  --local --http-port=8081 \
  --dir=/var/lib/telegram-bot-api
```

В `.env` бота:

```env
API_SERVER=http://127.0.0.1:8081
UPLOAD_LIMIT_MB=2000
```

Перезапусти бота. Теперь он сможет отправлять файлы до 2 ГБ (и быстрее, потому что файл не гоняется через облако Telegram).

---

## 5. Cookies для приватного контента

Instagram, возрастные YouTube-ролики и часть TikTok без авторизации не отдаются.

1. Установи в браузер расширение **Get cookies.txt LOCALLY** (Chrome/Firefox).
2. Зайди на нужный сайт, экспортируй cookies в формате Netscape.
3. Положи файл на сервер: `secrets/cookies.txt` (рядом с `docker-compose.yml`).
4. В `.env`:

   ```env
   COOKIES_FILE=/secrets/cookies.txt
   ```

5. `docker compose restart` (или `systemctl restart octo-load`).

⚠️ Cookies — это доступ к аккаунту. Не коммить их в git, не пересылай в чатах, используй отдельный аккаунт.

---

## 6. Обслуживание

```bash
# логи (Docker)
docker compose logs -f --tail=200

# логи (systemd)
journalctl -u octo-load -f

# рестарт
docker compose restart          # или: systemctl restart octo-load

# обновить yt-dlp/gallery-dl
docker compose build --pull --no-cache && docker compose up -d
# (systemd-вариант: scripts/update.sh)

# свободное место
df -h
docker system prune -f
```

Бэкапить нужно только `.env` и `secrets/` — всё остальное восстанавливается из репозитория.

---

## 7. Чек-лист безопасности

- [ ] `.env` и `secrets/` не попали в git (они в `.gitignore`).
- [ ] Токен бота не светился в скриншотах/логах.
- [ ] Если токен утёк — @BotFather → `/revoke`.
- [ ] SSH только по ключу, пароль root отключён (в Oracle так по умолчанию).
- [ ] `COOKIES_FILE` от отдельного аккаунта, а не от основного.
- [ ] Обновляй yt-dlp раз в неделю — это главная «уязвимость» любого такого бота.
