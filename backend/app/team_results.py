"""Club standings from confirmed category places, shared by public UI and exports."""
from collections import defaultdict
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (AgeGroup, Club, Event, EventStage, FinalCategoryResult, FinalRouteAttempt,
    JudgeResultConflict, Participant, QualificationCategorySnapshot, QualificationResultSnapshot)
from app.services import final_group_participates

FSR_POINTS = (100, 80, 65, 55, 51, 47, 43, 40, 37, 34, 31, 28, 26, 24, 22,
              20, 18, 16, 14, 12, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)
FSR_SOURCES = [
    {"title": "Действующие правила соревнований ФСР", "url": "https://rusclimbing.ru/docs/pravila-sorevnovaniy/"},
    {"title": "Положение на 2026 год · приложение 2, страница 48", "url": "https://rusclimbing.ru/upload/iblock/b08/32xj3kh3cb9g4ijdjgsj1s27sx0slgq2/2026_pol.pdf#page=48"},
    {"title": "Нормативные документы ФСР", "url": "https://rusclimbing.ru/docs/normativnye-dokumenty/"},
]


class AmbiguousFsrTie(ValueError):
    pass


def place_points(place: int, count: int) -> Fraction:
    outside = min(count, max(0, place + count - 1 - 30))
    if outside and outside * 2 == count:
        raise AmbiguousFsrTie(f"Места {place}–{place + count - 1}: требуется официальное разъяснение ФСР для границы топ-30")
    if outside * 2 > count:
        return Fraction(0)
    return Fraction(sum(FSR_POINTS[p - 1] for p in range(place, min(30, place + count - 1) + 1)), count)


def rank_teams(groups: list[dict], clubs: dict[str, str], quota: int) -> tuple[list[dict], list[str]]:
    teams = {}
    issues = []
    for group in groups:
        ties = defaultdict(list)
        for row in group["rows"]:
            if row["place"] is not None:
                ties[row["place"]].append(row)
        members = defaultdict(list)
        for place, rows in ties.items():
            try:
                points = place_points(place, len(rows))
            except AmbiguousFsrTie as error:
                issues.append(f"{group['name']}: {error}")
                continue
            for row in rows:
                if row["club_id"] in clubs:
                    members[row["club_id"]].append({**row, "points": points})
        for club_id, rows in members.items():
            team = teams.setdefault(club_id, {"club_id": club_id, "club": clubs[club_id], "points": Fraction(0), "groups": []})
            # Equal contributions are interchangeable. Bib order only makes the explanation stable.
            rows.sort(key=lambda row: (-row["points"], row["start_number"]))
            selected = [row for row in rows[:quota] if row["points"] > 0]
            subtotal = sum((row["points"] for row in selected), Fraction(0))
            team["points"] += subtotal
            team["groups"].append({"name": group["name"], "points": subtotal, "members": selected})
    if issues:
        return [], issues
    ordered = sorted(teams.values(), key=lambda row: (-row["points"], row["club"].casefold(), row["club_id"]))
    previous, place = None, None
    for position, team in enumerate(ordered, 1):
        score = team["points"]
        if score != previous:
            place = position
        team["place"], previous = place, score
        team["points_exact"] = str(score)
        team["points"] = float(score)
        for group in team["groups"]:
            group["points"] = float(group["points"])
            for member in group["members"]:
                member["points_exact"] = str(member["points"])
                member["points"] = float(member["points"])
    return ordered, []


def team_results(db: Session, event: Event, stage: str, status=None) -> dict:
    from app.routers.admin_final import status_response, qualification_state

    response = {"stage": stage, "quota": event.team_quota, "available": False, "reason": "",
                "issues": [], "results": [], "sources": FSR_SOURCES}
    frozen = event.stage in (EventStage.final, EventStage.completed)
    reason = ""
    if event.stage == EventStage.preparation or (stage == "final" and not frozen):
        reason = "Командный зачёт появится после подтверждения всех итоговых результатов этапа"
    else:
        status = status or status_response(db, event)
        if stage == "qualification" and not frozen and not status.all_categories_confirmed:
            reason = "Ожидаем подтверждения всех итоговых результатов квалификации"
        if stage == "final" and not status.all_final_categories_confirmed:
            reason = "Ожидаем подтверждения всех итоговых результатов финала"
        if stage == "final" and db.scalar(select(JudgeResultConflict.id).where(
            JudgeResultConflict.event_id == event.id, JudgeResultConflict.resolution.is_(None)).limit(1)):
            reason = "Ожидаем разрешения конфликтов результатов финала"
    if reason:
        response["reason"] = reason
        return response
    people = {p.id: p for p in db.scalars(select(Participant).where(Participant.event_id == event.id)).all()}
    clubs = {str(c.id): c.name for c in db.scalars(select(Club).where(Club.event_id == event.id)).all()}

    def row(person, place, number, name):
        return {"participant_id": str(person.id), "club_id": str(person.club_id) if person.club_id else None,
                "place": place, "start_number": number, "full_name": name}

    groups = []
    if stage == "qualification" and not frozen:
        categories, grouped, _ = qualification_state(db, event)
        groups = [{"name": category.name, "rows": [row(r["participant"], r["place"],
            r["participant"].start_number, f"{r['participant'].surname} {r['participant'].name}")
            for r in grouped[category.name]]} for category in categories]
    else:
        categories = list(db.scalars(select(QualificationCategorySnapshot).where(
            QualificationCategorySnapshot.event_id == event.id).order_by(QualificationCategorySnapshot.sort_order)).all())
        snapshots = list(db.scalars(select(QualificationResultSnapshot).where(QualificationResultSnapshot.event_id == event.id)).all())
        finals = {r.qualification_result_snapshot_id: r for r in db.scalars(select(FinalCategoryResult).where(FinalCategoryResult.event_id == event.id)).all()} if stage == "final" else {}
        with_attempts = set(db.scalars(select(FinalRouteAttempt.final_category_result_id).where(FinalRouteAttempt.event_id == event.id)).all()) if stage == "final" else set()
        participating = {g.id for g in db.scalars(select(AgeGroup).where(AgeGroup.event_id == event.id)).all() if final_group_participates(g)}
        for category in categories:
            if stage == "final" and category.age_group_id not in participating:
                continue
            rows = []
            for snapshot in snapshots:
                if snapshot.category_snapshot_id != category.id:
                    continue
                final = finals.get(snapshot.id)
                if stage == "final" and (not final or final.id not in with_attempts):
                    continue
                rows.append(row(people[snapshot.participant_id], final.place if stage == "final" else snapshot.place,
                    snapshot.start_number, f"{snapshot.surname} {snapshot.name}"))
            groups.append({"name": category.name, "rows": rows})
    results, issues = rank_teams(groups, clubs, event.team_quota)
    response.update(results=results, issues=issues, available=not issues,
        reason="Расчёт ожидает разъяснения ФСР по равным местам на границе топ-30" if issues else "")
    return response
