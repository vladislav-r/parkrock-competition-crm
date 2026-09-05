import logging

import httpx
from sqlalchemy.engine import make_url

from app.config import settings


logger = logging.getLogger(__name__)

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSM_CONTENT_TYPE = "application/vnd.ms-excel.sheet.macroEnabled.12"


def telegram_delivery_enabled() -> bool:
    database_name = make_url(settings.database_url).database or ""
    return bool(
        not database_name.endswith("_test")
        and settings.telegram_bot_token
        and settings.telegram_chat_id
    )


async def send_application_document(
    *, filename: str, content: bytes, participant_count: int,
) -> None:
    """Send a saved landing-page application to the configured Telegram chat."""
    if not telegram_delivery_enabled():
        return

    caption = (
        "Новая заявка с лендинга\n"
        f"Файл: {filename}\n"
        f"Участников: {participant_count}"
    )
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendDocument"

    try:
        # Telegram advertises IPv6 on some networks where the route itself is
        # unavailable. Bind to IPv4 so delivery does not stall on that route.
        transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
        async with httpx.AsyncClient(transport=transport, timeout=30.0) as client:
            response = await client.post(
                url,
                data={"chat_id": settings.telegram_chat_id, "caption": caption},
                files={"document": (
                    filename,
                    content,
                    XLSM_CONTENT_TYPE if filename.lower().endswith(".xlsm") else XLSX_CONTENT_TYPE,
                )},
            )
            response.raise_for_status()
    except Exception as error:
        # Telegram is a duplicate delivery channel: its outage must not reject an
        # application that has already been safely saved in the database.
        logger.warning(
            "Could not duplicate application to Telegram (%s)",
            type(error).__name__,
        )
