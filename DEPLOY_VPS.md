# Развёртывание ParkRock Hub на VPS

Production-схема запускает шесть контейнеров: `caddy`, `frontend`, `backend`, `postgres`, `prometheus` и `grafana`.
Наружу открыты только порты `80/443`. PostgreSQL и служебные порты приложения доступны только внутри Docker-сетей.

## 1. Подготовка VPS

Рекомендуемая ОС: актуальная Ubuntu LTS. На сервере должны быть установлены Docker Engine, Compose plugin и Git.
В firewall разрешите SSH, HTTP и HTTPS; порты `3000`, `8001` и `5432` открывать не нужно.

Укажите DNS A-запись домена на публичный IPv4 VPS и дождитесь обновления DNS.

## 2. Загрузка проекта

```bash
sudo mkdir -p /opt/parkrock
sudo chown "$USER":"$USER" /opt/parkrock
git clone <URL-РЕПОЗИТОРИЯ> /opt/parkrock
cd /opt/parkrock
cp .env.production.example .env.production
```

Заполните `.env.production`: домен CRM, адреса лендинга `LANDING_ORIGINS`, пароли PostgreSQL и Grafana, а также новый `JWT_SECRET`. Файл не должен попадать в Git.

Сгенерировать безопасные значения можно командами:

```bash
openssl rand -hex 32
openssl rand -hex 48
```

## 3. Первый запуск без переноса существующей базы

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Backend дождётся готовности PostgreSQL и применит Alembic-миграции автоматически. Caddy получит TLS-сертификат для `DOMAIN`.

Проверка:

```bash
curl -fsS "https://$(grep '^DOMAIN=' .env.production | cut -d= -f2)/health"
```

Интерфейсы будут доступны по адресам:

- `https://DOMAIN/` — публичные результаты;
- `https://DOMAIN/admin` — единый вход сотрудников;
- `https://DOMAIN/judge` — рабочее место судьи;
- `https://DOMAIN/docs` — документация API.
- `https://DOMAIN/monitoring/` — мониторинг FastAPI, PostgreSQL и логов; вход по `GRAFANA_ADMIN_USER` и `GRAFANA_ADMIN_PASSWORD` из `.env.production`. Панели ParkRock Hub, FastAPI Observability (16110) и PostgreSQL Database (9628) создаются автоматически.

## 4. Перенос текущей PostgreSQL

Перед переносом создайте и проверьте свежий `.dump` штатным разделом резервных копий. Скопируйте файл на VPS, например:

```bash
scp climbhub-YYYYMMDD-HHMMSS-manual.dump user@SERVER_IP:/opt/parkrock/import.dump
```

Для первичного импорта сначала поднимите только пустой PostgreSQL:

```bash
cd /opt/parkrock
docker compose --env-file .env.production -f docker-compose.prod.yml up -d postgres
docker compose --env-file .env.production -f docker-compose.prod.yml cp import.dump postgres:/tmp/import.dump
docker compose --env-file .env.production -f docker-compose.prod.yml exec postgres \
  pg_restore --list /tmp/import.dump >/dev/null
docker compose --env-file .env.production -f docker-compose.prod.yml exec postgres \
  pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --clean --if-exists --exit-on-error --no-owner --no-privileges /tmp/import.dump
docker compose --env-file .env.production -f docker-compose.prod.yml exec postgres rm -f /tmp/import.dump
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
```

Перед выполнением команд экспортируйте значения из `.env.production` в текущую shell-сессию:

```bash
set -a
source .env.production
set +a
```

После восстановления backend применит только недостающие миграции. Файл `import.dump` удаляйте с VPS только после проверки системы и создания новой production-копии.

## 5. Обновление приложения

```bash
cd /opt/parkrock
git pull --ff-only
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

Пересоздание контейнеров не удаляет данные. Никогда не выполняйте `docker compose down -v`: флаг `-v` удалит PostgreSQL, backup-файлы и данные TLS.

## 6. Резервные копии

Встроенный раздел резервных копий работает внутри backend-контейнера: образ содержит совместимые `pg_dump/pg_restore`, а файлы хранятся в volume `backups`.

Для защиты от потери всего VPS регулярно копируйте дампы во внешнее хранилище. Снимок самого VPS не заменяет проверенный PostgreSQL dump.

Просмотр журналов и состояния:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 backend
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=200 caddy
```
