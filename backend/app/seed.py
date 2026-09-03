import os
from datetime import date, datetime, timezone

from sqlalchemy import func, select

from app.db import SessionLocal
from app.clubs import get_or_create_club
from app.models import Admin, AgeGroup, Ascent, CompetitionSet, Event, Participant, Route, SetStatus, Sex
from app.security import hash_password
from app.services import publish_set


PEOPLE = [
    ("Волков", "Артем", "Север", Sex.male), ("Лукин", "Егор", "Высота", Sex.male),
    ("Вяткин", "Вадим", "Гранит", Sex.male), ("Артеменко", "Руслан", "Скала", Sex.male),
    ("Нагорничных", "Яромир", "Вертикаль", Sex.male), ("Шулев", "Гавриил", "Пик", Sex.male),
    ("Бондарев", "Платон", "Высота", Sex.male), ("Попов", "Матвей", "Неолит", Sex.male),
    ("Туношенский", "Иван", "Север", Sex.male), ("Ганичев", "Максим", "Гранит", Sex.male),
    ("Соловьев", "Петр", "Пик", Sex.male), ("Лукашевич", "Роман", "Вертикаль", Sex.male),
    ("Морозова", "Анна", "Север", Sex.female), ("Белова", "Мария", "Высота", Sex.female),
    ("Орлова", "Елена", "Гранит", Sex.female), ("Соколова", "Дарья", "Скала", Sex.female),
    ("Лебедева", "Алиса", "Вертикаль", Sex.female), ("Козлова", "Софья", "Пик", Sex.female),
]

SURNAMES = [
    "Иванов", "Петров", "Смирнов", "Кузнецов", "Васильев", "Федоров", "Михайлов", "Новиков",
    "Алексеев", "Николаев", "Степанов", "Павлов", "Семенов", "Голубев", "Виноградов", "Богданов",
]
MALE_NAMES = ["Александр", "Михаил", "Даниил", "Илья", "Никита", "Кирилл", "Тимофей", "Арсений"]
FEMALE_NAMES = ["Екатерина", "Полина", "Виктория", "Варвара", "Ксения", "Арина", "Милана", "Таисия"]
CLUBS = ["Север", "Высота", "Гранит", "Скала", "Вертикаль", "Пик", "Неолит", "Альпика"]
TARGET_SET_OCCUPANCY = [50, 50, 30]


def fill_demo_participants(db, event: Event, sets: list[CompetitionSet]) -> None:
    next_number = (db.scalar(select(func.max(Participant.start_number)).where(
        Participant.event_id == event.id)) or 100) + 1
    generated_index = 0
    for competition_set, target in zip(sets, TARGET_SET_OCCUPANCY, strict=False):
        current = db.scalar(select(func.count()).select_from(Participant).where(
            Participant.set_id == competition_set.id, Participant.archived_at.is_(None))) or 0
        for _ in range(max(0, target - current)):
            sex = Sex.male if generated_index % 2 == 0 else Sex.female
            names = MALE_NAMES if sex == Sex.male else FEMALE_NAMES
            surname = SURNAMES[generated_index % len(SURNAMES)]
            if sex == Sex.female and not surname.endswith("а"):
                surname = f"{surname}а"
            club = CLUBS[generated_index % len(CLUBS)]
            club_record = get_or_create_club(db, event.id, club, f"Представитель клуба {club}")
            birth_year = 2002 + (generated_index % 14)
            db.add(Participant(
                event_id=event.id, set_id=competition_set.id, club_id=club_record.id, start_number=next_number,
                surname=surname, name=names[generated_index % len(names)],
                patronymic="Александрович" if sex == Sex.male else "Александровна",
                birth_date=date(birth_year, (generated_index % 12) + 1, (generated_index % 27) + 1),
                birth_year=birth_year,
                sex=sex, sport_rank="1 юношеский" if birth_year >= 2010 else "2 взрослый",
                club=club, representative=f"Представитель клуба {club}", checked_in_at=None,
            ))
            next_number += 1
            generated_index += 1


def seed() -> None:
    if os.getenv("PARKROCK_ALLOW_DEMO_SEED") != "1":
        raise RuntimeError("Создание демоданных разрешено только явной командой scripts\\seed-demo.ps1")
    db = SessionLocal()
    try:
        existing_event = db.scalar(select(Event).order_by(Event.starts_on.desc()))
        if existing_event:
            existing_sets = list(db.scalars(select(CompetitionSet).where(
                CompetitionSet.event_id == existing_event.id).order_by(CompetitionSet.name)).all())
            fill_demo_participants(db, existing_event, existing_sets)
            db.commit()
            return

        admin = Admin(email="admin@parkrock.test", full_name="Администратор",
                      password_hash=hash_password("demo1234"))
        event = Event(title="ParkRock Fest 2026", location="Скалодром ParkRock", starts_on=date(2026, 10, 17))
        db.add_all([admin, event])
        db.flush()
        group_specs = [
            ("Мальчики 7-9", Sex.male, 7, 9), ("Девочки 7-9", Sex.female, 7, 9),
            ("Мальчики 10-12", Sex.male, 10, 12), ("Девочки 10-12", Sex.female, 10, 12),
            ("Юноши 13-14", Sex.male, 13, 14), ("Девушки 13-14", Sex.female, 13, 14),
            ("Юноши 15-16", Sex.male, 15, 16), ("Девушки 15-16", Sex.female, 15, 16),
            ("Юноши 17-18", Sex.male, 17, 18), ("Девушки 17-18", Sex.female, 17, 18),
            ("Мужчины", Sex.male, 19, None), ("Женщины", Sex.female, 19, None),
        ]
        db.add_all([AgeGroup(event_id=event.id, name=name, sex=sex, min_age=minimum,
                    max_age=maximum, sort_order=index, finalist_count=0 if minimum == 7 and maximum == 9 else 10,
                    participates_in_final=not (minimum == 7 and maximum == 9))
                    for index, (name, sex, minimum, maximum) in enumerate(group_specs)])
        sets = [
            CompetitionSet(event_id=event.id, name="Сет 1", time_label="09:00-12:00", capacity=50),
            CompetitionSet(event_id=event.id, name="Сет 2", time_label="13:00-16:00", capacity=50),
            CompetitionSet(event_id=event.id, name="Сет 3", time_label="17:00-20:00", capacity=50),
        ]
        db.add_all(sets)
        routes = [Route(event_id=event.id, number=i, name=f"Трасса {i}", grade=grade,
                        points=0, sort_order=i, is_active=True)
                  for i, grade in enumerate([
                      "5B", "5C", "6A", "6A+", "6B", "6B+", "6C", "6C+", "7A", "7A+", "7B", "7B+"
                  ], start=1)]
        db.add_all(routes)
        db.flush()
        participants = []
        for index, (surname, name, club, sex) in enumerate(PEOPLE, start=1):
            competition_set = sets[0] if index <= 12 else sets[1]
            club_record = get_or_create_club(db, event.id, club, f"Представитель клуба {club}")
            participant = Participant(
                event_id=event.id, set_id=competition_set.id, club_id=club_record.id, start_number=100 + index,
                surname=surname, name=name,
                patronymic="Александрович" if sex == Sex.male else "Александровна",
                birth_date=date(2012 if index <= 12 else 2010, 4, (index % 25) + 1), sex=sex,
                birth_year=2012 if index <= 12 else 2010,
                sport_rank="1 юношеский", club=club, representative=f"Представитель клуба {club}",
                checked_in_at=datetime.now(timezone.utc),
            )
            db.add(participant)
            participants.append(participant)
        db.flush()
        for index, participant in enumerate(participants):
            completed_count = max(1, 12 - (index % 11))
            for route in routes[:completed_count]:
                db.add(Ascent(participant_id=participant.id, route_id=route.id, is_completed=True))
        fill_demo_participants(db, event, sets)
        db.flush()
        publish_set(db, sets[0].id)
        sets[0].status = SetStatus.confirmed
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
    print("Тестовые данные готовы. Вход: admin@parkrock.test / demo1234")
