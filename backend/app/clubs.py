import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Club


def normalize_club_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def get_or_create_club(db: Session, event_id, name: str, representative: str = "") -> Club:
    clean_name = re.sub(r"\s+", " ", name.strip())
    clean_representative = re.sub(r"\s+", " ", representative.strip())
    normalized = normalize_club_name(clean_name)
    normalized_representative = normalize_club_name(clean_representative)
    club = db.scalar(select(Club).where(
        Club.event_id == event_id,
        Club.normalized_name == normalized,
        Club.normalized_representative == normalized_representative,
    ))
    if club:
        return club
    club = Club(
        event_id=event_id, name=clean_name, normalized_name=normalized,
        representative=clean_representative, normalized_representative=normalized_representative,
    )
    db.add(club)
    db.flush()
    return club
