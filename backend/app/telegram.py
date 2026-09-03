import logging

import httpx

from app.config import settings


logger = logging.getLogger(__name__)

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def send_application_document(
    *, filename: str, content: bytes, participant_count: int,
) -> None:
    """Send a saved landing-page application to the configured Telegram chat."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
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
                files={"document": (filename, content, XLSX_CONTENT_TYPE)},
            )
            response.raise_for_status()
    except Exception as error:
        # Telegram is a duplicate delivery channel: its outage must not reject an
        # application that has already been safely saved in the database.
        logger.warning(
            "Could not duplicate application to Telegram (%s)",
            type(error).__name__,
        )
