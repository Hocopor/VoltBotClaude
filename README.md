# VOLTAGE

VOLTAGE — это AI-бот для криптотрейдинга с веб-интерфейсом, FastAPI backend, React frontend и деплоем через Docker Compose. Публичный доступ предполагается через Cloudflare Tunnel.

## Что внутри

- `backend/` — FastAPI, SQLAlchemy, Alembic, бизнес-логика бота
- `frontend/` — React + Vite интерфейс
- `nginx/` — reverse proxy для frontend, API и WebSocket
- `scripts/` — скрипты деплоя и обновления
- `docker-compose.yml` — production-стек

## Стек

- Python 3.12
- FastAPI
- PostgreSQL 16
- Redis 7
- React 18 + Vite
- Nginx
- Cloudflare Tunnel
- Docker Compose

## Архитектура деплоя

Прод-схема одна:

1. `cloudflared` работает в Docker
2. Tunnel ходит к `nginx` по имени сервиса `http://nginx:80`
3. `nginx` проксирует:
   - `/` -> frontend
   - `/api/` -> backend
   - `/ws/` -> backend WebSocket
   - `/health` -> backend healthcheck
4. На хосте `nginx` публикуется только на loopback:
   - `127.0.0.1:${APP_PORT}:80`

Это значит:

- наружу не нужно открывать `80/443` для приложения
- публичный доступ должен идти через Cloudflare Tunnel
- локальная проверка origin выполняется через `127.0.0.1:${APP_PORT}`

## Быстрый старт на сервере

### 1. Подготовить сервер

```bash
sudo apt-get update
sudo apt-get install -y git
git clone <your-repo> voltage-bot
cd voltage-bot
```

### 2. Создать `.env`

```bash
cp .env.example .env
nano .env
```

Минимально обязательные переменные:

```env
POSTGRES_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-password>
SECRET_KEY=<long-random-string>
CLOUDFLARE_TUNNEL_TOKEN=<cloudflare-tunnel-token>
ALLOWED_ORIGINS=https://your-subdomain.yourdomain.com
APP_PORT=8088
APP_AUTH_LOGIN=admin
APP_AUTH_PASSWORD_HASH=<bcrypt-hash>
```

Обычно также понадобятся:

```env
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
DEEPSEEK_API_KEY=...
OPENAI_CLIENT_ID=...
OPENAI_CLIENT_SECRET=...
OPENAI_REDIRECT_URI=https://your-subdomain.yourdomain.com/api/auth/codex/callback
```

Важно:

- `BYBIT_API_KEY`, `BYBIT_API_SECRET` и `DEEPSEEK_API_KEY` задаются только в серверном `.env`
- веб-интерфейс не должен быть источником правды для боевых API-ключей
- UI используется для настроек режима и поведения, а не для хранения production-секретов
- для полноценного исторического `BTC dominance` в backtest можно дополнительно задать `COINMARKETCAP_API_KEY`
- без `COINMARKETCAP_API_KEY` backtest использует реальный исторический `Fear & Greed` и прозрачный fallback для `BTC dominance`

```bash
docker compose exec backend python -c "from app.security import hash_password; print(hash_password('CHANGE_ME_PASSWORD'))"
```

Примечания:

- `APP_PORT` — локальный порт на хосте, только для loopback-доступа
- `ALLOWED_ORIGINS` должен совпадать с вашим публичным доменом
- `.env` не коммитится в git

### 3. Запустить деплой

```bash
chmod +x scripts/deploy.sh scripts/update.sh
sudo bash scripts/deploy.sh
```

Что делает скрипт:

- устанавливает Docker, если его нет
- проверяет Docker Compose plugin
- собирает образы
- поднимает `postgres`, `redis`, `backend`, `frontend`, `nginx`, `cloudflared`
- ждёт успешный ответ от `http://127.0.0.1:${APP_PORT}/health`
- пишет полный лог в `logs/deploy/`

### 4. Проверить, что origin жив

Если `APP_PORT=8088`, то:

```bash
curl http://127.0.0.1:8088/health
docker compose ps
docker compose logs --tail 50 backend nginx cloudflared
```

Ожидаемо:

- `/health` возвращает JSON со статусом `ok`
- контейнеры `backend`, `nginx`, `cloudflared`, `postgres`, `redis` запущены

## Настройка Cloudflare Tunnel

После первого запуска контейнер `cloudflared` уже будет поднят с вашим token-based tunnel.

В Cloudflare Zero Trust:

1. Откройте `Networks -> Tunnels`
2. Найдите tunnel, соответствующий вашему токену
3. Добавьте `Public Hostname`
4. Укажите нужный поддомен, например `trading.yourdomain.com`
5. В качестве origin service укажите:

```text
http://nginx:80
```

Важно:

- не указывайте `http://localhost:80`
- tunnel находится внутри Docker-сети и должен обращаться к origin по имени сервиса

После этого приложение должно открываться по адресу:

```text
https://your-subdomain.yourdomain.com
```

## Обновление

```bash
sudo bash scripts/update.sh
```

Скрипт:

- останавливает текущий стек
- пересобирает образы без кэша
- поднимает контейнеры заново
- ждёт успешный healthcheck
- пишет полный лог в `logs/deploy/`

## Полезные команды

Просмотр статуса:

```bash
docker compose ps
```

Логи:

```bash
docker compose logs -f backend nginx cloudflared
```

Логи deploy/update-скриптов:

```bash
ls -lah logs/deploy
tail -n 200 logs/deploy/deploy-*.log
tail -n 200 logs/deploy/update-*.log
```

Проверка health:

```bash
curl http://127.0.0.1:8088/health
```

Рестарт backend:

```bash
docker compose restart backend
```

Рестарт tunnel:

```bash
docker compose restart cloudflared
```

Остановка стека:

```bash
docker compose down
```

Подключение к PostgreSQL:

```bash
docker compose exec postgres psql -U voltage voltage
```

## Переменные окружения

Основные переменные из `.env.example`:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `REDIS_PASSWORD`
- `SECRET_KEY`
- `DEBUG`
- `BYBIT_API_KEY`
- `BYBIT_API_SECRET`
- `BYBIT_TESTNET`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `OPENAI_CLIENT_ID`
- `OPENAI_CLIENT_SECRET`
- `OPENAI_REDIRECT_URI`
- `CLOUDFLARE_TUNNEL_TOKEN`
- `APP_PORT`
- `APP_AUTH_LOGIN`
- `APP_AUTH_PASSWORD_HASH`
- `APP_AUTH_COOKIE_SECURE`
- `APP_AUTH_SESSION_TTL_HOURS`
- `ALLOWED_ORIGINS`
- `LOG_LEVEL`

## Безопасность

- не коммитьте `.env`
- держите `nginx` только на loopback-порту, как в compose
- не давайте Bybit API ключам права на вывод средств
- публичный трафик должен идти через Cloudflare Tunnel, а не через прямую публикацию `80/443`

## Что важно знать

- текущий деплой рассчитан на один production-стек
- Cloudflare Tunnel является обязательной частью схемы доступа
- приложение не предполагает отдельный внешний TLS-терминатор на самом сервере
- для локальной проверки используйте `127.0.0.1:${APP_PORT}`
