FROM postgres:16-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv

WORKDIR /app/backend

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY app ./app

RUN useradd --system --uid 10001 --create-home parkrock \
    && mkdir -p /backups /var/log/parkrock \
    && chown -R parkrock:parkrock /app /backups /var/log/parkrock

ENTRYPOINT []
USER parkrock
EXPOSE 8001

CMD ["python", "-m", "app.serve", "--forwarded-allow-ips=*"]
