"""Public readers consume immutable, server-built publications."""
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app.db import SessionLocal, engine
from app import publication
from app.models import Ascent, Event, EventStage, Participant, PublicPublication, Route, Sex
from app.routers import public
from conftest import refresh_publication
from test_stage8_judge import prepare_final


@pytest.fixture
def scored_participant(festival):
    with SessionLocal() as db:
        participant = Participant(event_id=festival["event_id"], set_id=festival["first_set_id"],
            club_id=festival["club_id"], start_number=1, surname="Первый", name="Участник",
            birth_date=date(2000, 1, 1), sex=Sex.male, club="Тестовый клуб")
        db.add(participant)
        db.flush()
        db.add(Ascent(participant_id=participant.id, route_id=festival["route_ids"][0], is_completed=True))
        db.get(Event, festival["event_id"]).public_result_details_enabled = True
        db.commit()
        return participant.id


def forbid_calculation(*args, **kwargs):
    raise AssertionError("Public GET must never calculate results")


def test_missing_publication_does_not_build_on_request(client, festival, monkeypatch):
    monkeypatch.setattr(public, "live_result_rows", forbid_calculation)
    response = client.get("/api/v1/public/results")
    assert response.status_code == 503
    with SessionLocal() as db:
        assert db.scalar(select(PublicPublication)) is None


def test_readers_share_frozen_version_and_filters(client, festival, scored_participant, monkeypatch):
    refresh_publication()
    first = client.get("/api/v1/public/results").json()
    assert first["publication_version"] and first["published_at"]
    assert first["results"][0]["points"] == 100
    with SessionLocal() as db:
        db.get(Route, festival["route_ids"][0]).points = 450
        db.commit()
    with monkeypatch.context() as patch:
        patch.setattr(public, "live_result_rows", forbid_calculation)
        for name in ("build_results", "build_absolute_results", "build_public_team_results", "build_participant_detail"):
            patch.setattr(public, name, forbid_calculation)
        for _ in range(4):
            assert client.get("/api/v1/public/results").json() == first
        filtered = client.get("/api/v1/public/results", params={"group": "Мужчины", "set_id": str(festival["first_set_id"])}).json()
        assert filtered["results"] == first["results"]
        assert not client.get("/api/v1/public/results?group=Неизвестная").json()["results"]
        absolute = client.get("/api/v1/public/absolute-results").json()
        detail = client.get(f"/api/v1/public/participants/{scored_participant}").json()
        team = client.get("/api/v1/public/team-results").json()
        assert absolute["results"][0]["score"] == detail["points"] == 100
        assert {item["publication_version"] for item in (absolute, detail, team)} == {first["publication_version"]}
    refresh_publication()
    latest = client.get("/api/v1/public/results").json()
    assert latest["publication_version"] != first["publication_version"]
    assert latest["results"][0]["points"] == 450
    pinned = client.get("/api/v1/public/absolute-results", params={"publication_version": first["publication_version"]}).json()
    assert pinned["results"][0]["score"] == 100
    assert pinned["publication_version"] == first["publication_version"]


def test_closing_details_and_unpublishing_take_effect_immediately(client, festival, scored_participant):
    refresh_publication()
    url = f"/api/v1/public/participants/{scored_participant}"
    assert client.get(url).status_code == 200
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).public_result_details_enabled = False
        db.commit()
    assert client.get(url).status_code == 403
    assert client.get("/api/v1/public/results").json()["details_enabled"] is False
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).is_public = False
        db.commit()
    for path in ("results", "absolute-results", "team-results", "final-results?group=Мужчины", f"participants/{scored_participant}"):
        assert client.get("/api/v1/public/" + path).status_code == 404


def test_final_and_aggregate_tables_share_publication(client, festival, auth_headers):
    prepare_final(client, festival, auth_headers)
    refresh_publication()
    paths = ["results", "final-results?group=Мужчины", "absolute-results?stage=qualification",
             "absolute-results?stage=final", "absolute-results?stage=overall", "team-results", "team-results?stage=final"]
    responses = [client.get("/api/v1/public/" + path) for path in paths]
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["publication_version"] for response in responses}) == 1
    assert len({response.json()["published_at"] for response in responses}) == 1


def test_failure_retains_last_complete_publication(client, festival, scored_participant, monkeypatch):
    refresh_publication()
    old = client.get("/api/v1/public/results").json()
    def fail_build(db, event):
        raise RuntimeError("simulated failed publication")
    monkeypatch.setattr(publication, "build_publication", fail_build)
    with pytest.raises(RuntimeError, match="simulated"):
        refresh_publication()
    assert client.get("/api/v1/public/results").json() == old
    with SessionLocal() as db:
        assert len(list(db.scalars(select(PublicPublication)))) == 1


def test_database_lock_and_due_interval_prevent_duplicate_work(client, festival, monkeypatch):
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": publication.PUBLICATION_LOCK})
        with monkeypatch.context() as patch:
            patch.setattr(publication, "build_publication", forbid_calculation)
            assert refresh_publication() is False
    assert refresh_publication() is True
    monkeypatch.setattr(publication, "build_publication", forbid_calculation)
    assert publication.refresh_publications() is False


def test_publication_is_atomic_and_uses_one_database_snapshot(client, festival, scored_participant, monkeypatch):
    refresh_publication()
    old = client.get("/api/v1/public/results").json()
    original = publication.build_publication
    def concurrent_change(db, event):
        # Publisher already opened its repeatable-read snapshot before this commit.
        with SessionLocal() as writer:
            writer.get(Route, festival["route_ids"][0]).points = 450
            writer.commit()
        assert client.get("/api/v1/public/results").json() == old
        return original(db, event)
    with monkeypatch.context() as patch:
        patch.setattr(publication, "build_publication", concurrent_change)
        refresh_publication()
    middle = client.get("/api/v1/public/results").json()
    assert middle["publication_version"] != old["publication_version"]
    assert middle["results"][0]["points"] == 100
    assert client.get("/api/v1/public/absolute-results").json()["results"][0]["score"] == 100
    refresh_publication()
    assert client.get("/api/v1/public/results").json()["results"][0]["points"] == 450
    assert client.get("/api/v1/public/absolute-results").json()["results"][0]["score"] == 450
    assert client.get("/api/v1/public/results", params={"publication_version": old["publication_version"]}).status_code == 200
    with SessionLocal() as db:
        assert len(list(db.scalars(select(PublicPublication)))) == 3
        oldest = db.scalar(select(PublicPublication).order_by(PublicPublication.version))
        oldest.published_at -= timedelta(seconds=61)
        db.commit()
    refresh_publication()
    expired = client.get("/api/v1/public/results", params={"publication_version": old["publication_version"]})
    assert expired.status_code == 409
    assert client.get("/api/v1/public/results", params={"publication_version": middle["publication_version"]}).status_code == 200
    with SessionLocal() as db:
        assert len(list(db.scalars(select(PublicPublication)))) == 3


@pytest.mark.parametrize("stage, elapsed, expected", [
    (EventStage.qualification, 15, False),
    (EventStage.qualification, 31, True),
    (EventStage.final, 5, False),
    (EventStage.final, 15, True),
])
def test_publisher_respects_current_stage_interval(client, festival, stage, elapsed, expected):
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).stage = stage
        db.commit()
    refresh_publication()
    with SessionLocal() as db:
        db.scalar(select(PublicPublication)).published_at -= timedelta(seconds=elapsed)
        db.commit()
    assert publication.refresh_publications() is expected


def test_version_cannot_resolve_to_another_festival(client, festival):
    refresh_publication()
    old = client.get("/api/v1/public/results").json()["publication_version"]
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).is_public = False
        db.add(Event(title="Другой фестиваль", location="Другое место", starts_on=date(2027, 1, 1),
                     stage=EventStage.preparation, is_public=True))
        db.commit()
    refresh_publication()
    current = client.get("/api/v1/public/results").json()
    assert current["event_title"] == "Другой фестиваль"
    assert current["publication_version"] != old
    assert client.get("/api/v1/public/results", params={"publication_version": old}).status_code == 409


def test_stage_change_hides_old_snapshot_and_publishes_without_waiting(client, festival, scored_participant):
    refresh_publication()
    old = client.get("/api/v1/public/results").json()["publication_version"]
    with SessionLocal() as db:
        db.get(Event, festival["event_id"]).stage = EventStage.final
        db.commit()
    for path in ("results", "absolute-results", "team-results", f"participants/{scored_participant}"):
        response = client.get("/api/v1/public/" + path)
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "1"
        assert client.get("/api/v1/public/" + path, params={"publication_version": old}).status_code == 409
    assert publication.refresh_publications() is True
    fresh = client.get("/api/v1/public/results").json()
    assert fresh["stage"] == "final"
    assert fresh["publication_version"] != old


def test_same_stage_invalidation_is_transactional_and_excludes_publisher(client, festival):
    refresh_publication()
    old = client.get("/api/v1/public/results").json()
    with SessionLocal() as db:
        event = db.get(Event, festival["event_id"])
        publication.invalidate_publications(db, event)
        assert refresh_publication() is False
        assert client.get("/api/v1/public/results").json() == old
        db.rollback()
    assert client.get("/api/v1/public/results").json() == old
    with SessionLocal() as db:
        publication.invalidate_publications(db, db.get(Event, festival["event_id"]))
        assert refresh_publication() is False
        db.commit()
    assert client.get("/api/v1/public/results").status_code == 503
    assert client.get("/api/v1/public/results", params={"publication_version": old["publication_version"]}).status_code == 409
    assert publication.refresh_publications() is True
    assert client.get("/api/v1/public/results").json()["publication_version"] != old["publication_version"]


def test_retention_keeps_last_two_even_when_both_are_old(client, festival):
    refresh_publication()
    refresh_publication()
    with SessionLocal() as db:
        versions = list(db.scalars(select(PublicPublication).order_by(PublicPublication.version)))
        old, previous = (str(item.publication_id) for item in versions)
        for item in versions:
            item.published_at -= timedelta(seconds=61)
        db.commit()
    refresh_publication()
    assert client.get("/api/v1/public/results", params={"publication_version": old}).status_code == 409
    assert client.get("/api/v1/public/results", params={"publication_version": previous}).status_code == 200
    with SessionLocal() as db:
        assert len(list(db.scalars(select(PublicPublication)))) == 2
