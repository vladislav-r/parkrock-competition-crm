"""Cross-category standings; does not change category places or finalist selection."""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgeGroup, Event, EventStage, FinalCategoryResult, FinalRouteAttempt, QualificationCategorySnapshot, QualificationResultSnapshot


def absolute_rows(db: Session, event: Event, stage: str) -> list[dict]:
    from app.routers.public import live_result_rows

    live = live_result_rows(db, event)
    snapshots = {row.participant_id: row for row in db.scalars(select(QualificationResultSnapshot).where(
        QualificationResultSnapshot.event_id == event.id)).all()}
    categories = {row.id: row for row in db.scalars(select(QualificationCategorySnapshot).where(
        QualificationCategorySnapshot.event_id == event.id)).all()}
    participating_groups = set(db.scalars(select(AgeGroup.id).where(AgeGroup.event_id == event.id,
        AgeGroup.participates_in_final.is_(True), AgeGroup.finalist_count > 0)).all())
    finals = {row.participant_id: row for row in db.scalars(select(FinalCategoryResult).join(
        QualificationCategorySnapshot, QualificationCategorySnapshot.id == FinalCategoryResult.category_snapshot_id).where(
        FinalCategoryResult.event_id == event.id, QualificationCategorySnapshot.age_group_id.in_(participating_groups))).all()}
    attempt_counts = {}
    for result_id in db.scalars(select(FinalRouteAttempt.final_category_result_id).where(FinalRouteAttempt.event_id == event.id)).all():
        attempt_counts[result_id] = attempt_counts.get(result_id, 0) + 1
    frozen = event.stage in (EventStage.final, EventStage.completed)
    rows = []
    for item in live:
        participant = item["participant"]
        snapshot = snapshots.get(participant.id) if frozen else None
        final = finals.get(participant.id) if frozen else None
        if stage == "final" and not final:
            continue
        qualification = snapshot.points if snapshot else (None if frozen else item["points"])
        final_points = final.score_tenths if final and final.id in attempt_counts else None
        score = (qualification * 10 if qualification is not None else None) if stage == "qualification" else final_points
        if stage == "overall":
            score = (qualification or 0) * 10 + (final_points or 0) if qualification is not None or final_points is not None else None
        medal = item["medal"] if not frozen else None
        if snapshot:
            settings = json.loads(categories[snapshot.category_snapshot_id].settings_json)
            for color in ("gold", "silver", "bronze"):
                minimum, maximum = settings.get(f"{color}_min_points"), settings.get(f"{color}_max_points")
                if minimum is not None and snapshot.points >= minimum and (maximum is None or snapshot.points <= maximum):
                    medal = color
                    break
        rows.append({
            "participant_id": str(participant.id), "start_number": snapshot.start_number if snapshot else participant.start_number,
            "full_name": f"{snapshot.surname} {snapshot.name}" if snapshot else f"{participant.surname} {participant.name}",
            "club": participant.club,
            "group_name": categories[snapshot.category_snapshot_id].name if snapshot else item["group_name"],
            "qualification_points": qualification, "final_points": final_points / 10 if final_points is not None else None,
            "score": score / 10 if score is not None else None, "place": None,
            "has_result": score is not None, "is_finalist": (snapshot.is_finalist and categories[snapshot.category_snapshot_id].age_group_id in participating_groups) if snapshot else (False if frozen else item["is_finalist"]),
            "medal": medal, "birth_year": participant.birth_year or participant.birth_date.year,
            "sport_rank": participant.sport_rank,
            "final_attempt_count": attempt_counts.get(final.id, 0) if final else 0,
        })
    rows.sort(key=lambda row: (not row["has_result"], -(row["score"] or 0), row["full_name"].casefold(), row["start_number"]))
    previous, place = None, None
    for position, row in enumerate(rows, 1):
        if row["has_result"]:
            if row["score"] != previous:
                place = position
            row["place"], previous = place, row["score"]
    return rows
