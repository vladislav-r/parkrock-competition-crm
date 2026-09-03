import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Sex(str, enum.Enum):
    male = "male"
    female = "female"


class SetStatus(str, enum.Enum):
    draft = "draft"
    confirmed = "confirmed"
    reopened = "reopened"


class EventStage(str, enum.Enum):
    qualification = "qualification"
    final = "final"
    completed = "completed"


class UserRole(str, enum.Enum):
    reception = "reception"
    secretary = "secretary"
    chief_judge = "chief_judge"
    administrator = "administrator"
    route_judge = "route_judge"


class ApplicationType(str, enum.Enum):
    collective = "collective"
    individual = "individual"


class ParticipantSource(str, enum.Enum):
    import_file = "import_file"
    manual = "manual"


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.administrator)
    assigned_route_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("routes.id", ondelete="SET NULL"), nullable=True,
    )
    assigned_final_route_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("final_routes.id", ondelete="SET NULL"), nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class Event(Base):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(255))
    starts_on: Mapped[date] = mapped_column(Date)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    stage: Mapped[EventStage] = mapped_column(Enum(EventStage), nullable=False, default=EventStage.qualification)
    final_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sets: Mapped[list["CompetitionSet"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    routes: Mapped[list["Route"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    route_grade_points: Mapped[list["RouteGradePoint"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    groups: Mapped[list["AgeGroup"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    clubs: Mapped[list["Club"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    __mapper_args__ = {"version_id_col": version}


class Club(Base):
    __tablename__ = "clubs"
    __table_args__ = (UniqueConstraint(
        "event_id", "normalized_name", "normalized_representative",
        name="uq_club_event_name_representative",
    ),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200))
    representative: Mapped[str] = mapped_column(String(200), default="")
    normalized_representative: Mapped[str] = mapped_column(String(200), default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event: Mapped[Event] = relationship(back_populates="clubs")
    participants: Mapped[list["Participant"]] = relationship(back_populates="club_record")
    __mapper_args__ = {"version_id_col": version}


class AgeGroup(Base):
    __tablename__ = "age_groups"
    __table_args__ = (UniqueConstraint("event_id", "name", name="uq_age_group_event_name"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    sex: Mapped[Sex] = mapped_column(Enum(Sex))
    min_age: Mapped[int] = mapped_column(Integer)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    finalist_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    participates_in_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    bronze_min_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bronze_max_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    silver_min_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    silver_max_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gold_min_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gold_max_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualification_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    qualification_confirmed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), nullable=True,
    )
    qualification_signature: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event: Mapped[Event] = relationship(back_populates="groups")
    __mapper_args__ = {"version_id_col": version}


class CompetitionSet(Base):
    __tablename__ = "competition_sets"
    __table_args__ = (CheckConstraint("capacity > 0", name="ck_set_capacity_positive"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    time_label: Mapped[str] = mapped_column(String(100))
    capacity: Mapped[int] = mapped_column(Integer, default=50)
    status: Mapped[SetStatus] = mapped_column(Enum(SetStatus), default=SetStatus.draft)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event: Mapped[Event] = relationship(back_populates="sets")
    participants: Mapped[list["Participant"]] = relationship(back_populates="competition_set", foreign_keys="Participant.set_id")
    __mapper_args__ = {"version_id_col": version}


class Route(Base):
    __tablename__ = "routes"
    __table_args__ = (
        UniqueConstraint("event_id", "number", name="uq_route_event_number"),
        CheckConstraint("points >= 0", name="ck_route_points_nonnegative"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(150))
    grade: Mapped[str] = mapped_column(String(20))
    points: Mapped[int] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event: Mapped[Event] = relationship(back_populates="routes")
    __mapper_args__ = {"version_id_col": version}


class RouteGradePoint(Base):
    __tablename__ = "route_grade_points"
    __table_args__ = (
        UniqueConstraint("event_id", "grade", name="uq_route_grade_points_event_grade"),
        CheckConstraint("points IS NULL OR points >= 0", name="ck_route_grade_points_nonnegative"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    grade: Mapped[str] = mapped_column(String(20))
    points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event: Mapped[Event] = relationship(back_populates="route_grade_points")
    __mapper_args__ = {"version_id_col": version}


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("event_id", "start_number", name="uq_participant_event_start_number"),
        CheckConstraint("start_number > 0", name="ck_participant_start_number_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="RESTRICT"), index=True, nullable=False)
    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competition_sets.id"), index=True, nullable=False)
    start_number: Mapped[int] = mapped_column(Integer, nullable=False)
    surname: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    patronymic: Mapped[str] = mapped_column(String(100), default="")
    birth_date: Mapped[date] = mapped_column(Date)
    # В коллективной заявке указывается год, а не дата рождения.
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex: Mapped[Sex] = mapped_column(Enum(Sex))
    sport_rank: Mapped[str] = mapped_column(String(50), default="Без разряда")
    club: Mapped[str] = mapped_column(String(200))
    representative: Mapped[str] = mapped_column(String(200), default="")
    application_type: Mapped[ApplicationType] = mapped_column(Enum(ApplicationType), default=ApplicationType.individual)
    merch_size: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    merch_issued: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[ParticipantSource] = mapped_column(Enum(ParticipantSource), default=ParticipantSource.import_file)
    import_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operation_records.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    competition_set: Mapped[CompetitionSet] = relationship(back_populates="participants", foreign_keys=[set_id])
    club_record: Mapped[Club] = relationship(back_populates="participants")
    ascents: Mapped[list["Ascent"]] = relationship(cascade="all, delete-orphan")
    __mapper_args__ = {"version_id_col": version}


class ApplicationFile(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("event_id", "content_sha256", name="uq_application_event_content"),
        CheckConstraint("file_size > 0", name="ck_application_file_size_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(150))
    file_size: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    file_data: Mapped[bytes] = mapped_column(LargeBinary)
    participant_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overflow_sets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    import_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), nullable=True,
    )
    import_operation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operation_records.id", ondelete="SET NULL"), nullable=True,
    )


class Ascent(Base):
    __tablename__ = "ascents"
    __table_args__ = (UniqueConstraint("participant_id", "route_id", name="uq_ascent_participant_route"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"))
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class PublishedResult(Base):
    __tablename__ = "published_results"
    __table_args__ = (UniqueConstraint("participant_id", name="uq_published_participant"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("competition_sets.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"))
    group_name: Mapped[str] = mapped_column(String(100), index=True)
    completed_count: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)
    place: Mapped[int] = mapped_column(Integer, default=0)
    is_finalist: Mapped[bool] = mapped_column(Boolean, default=False)
    is_finisher: Mapped[bool] = mapped_column(Boolean, default=False)
    medal: Mapped[str | None] = mapped_column(String(10), nullable=True)
    completed_route_ids: Mapped[str] = mapped_column(String, default="")
    completed_routes_json: Mapped[str] = mapped_column(String, default="[]")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QualificationCategorySnapshot(Base):
    __tablename__ = "qualification_category_snapshots"
    __table_args__ = (UniqueConstraint("event_id", "age_group_id", name="uq_qualification_snapshot_group"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    age_group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("age_groups.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    sex: Mapped[Sex] = mapped_column(Enum(Sex))
    min_age: Mapped[int] = mapped_column(Integer)
    max_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer)
    finalist_count: Mapped[int] = mapped_column(Integer)
    settings_json: Mapped[str] = mapped_column(Text)
    signature: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class QualificationResultSnapshot(Base):
    __tablename__ = "qualification_result_snapshots"
    __table_args__ = (UniqueConstraint("category_snapshot_id", "participant_id", name="uq_qualification_snapshot_participant"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    category_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("qualification_category_snapshots.id", ondelete="CASCADE"), index=True,
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("participants.id", ondelete="RESTRICT"), index=True)
    start_number: Mapped[int] = mapped_column(Integer)
    surname: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    patronymic: Mapped[str] = mapped_column(String(100), default="")
    club: Mapped[str] = mapped_column(String(200))
    completed_count: Mapped[int] = mapped_column(Integer)
    points: Mapped[int] = mapped_column(Integer)
    place: Mapped[int] = mapped_column(Integer)
    is_finalist: Mapped[bool] = mapped_column(Boolean, default=False)
    exit_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_routes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FinalRoute(Base):
    __tablename__ = "final_routes"
    __table_args__ = (UniqueConstraint("event_id", "number", name="uq_final_route_event_number"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class FinalCategoryRoute(Base):
    __tablename__ = "final_category_routes"
    __table_args__ = (UniqueConstraint("age_group_id", "final_route_id", name="uq_final_category_route"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    age_group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("age_groups.id", ondelete="CASCADE"), index=True)
    final_route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("final_routes.id", ondelete="CASCADE"), index=True)


class FinalCategoryResult(Base):
    __tablename__ = "final_category_results"
    __table_args__ = (UniqueConstraint("qualification_result_snapshot_id", name="uq_final_result_snapshot"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    category_snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("qualification_category_snapshots.id", ondelete="CASCADE"), index=True)
    qualification_result_snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("qualification_result_snapshots.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("participants.id", ondelete="RESTRICT"), index=True)
    score_tenths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    zone_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    zone_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    place: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    __mapper_args__ = {"version_id_col": version}


class FinalRouteAttempt(Base):
    __tablename__ = "final_route_attempts"
    __table_args__ = (UniqueConstraint("final_category_result_id", "final_route_id", name="uq_final_result_route"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    final_category_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("final_category_results.id", ondelete="CASCADE"), index=True)
    final_route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("final_routes.id", ondelete="CASCADE"), index=True)
    zone_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class OperationRecord(Base):
    __tablename__ = "operation_records"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role", "permission", name="uq_role_permission"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), index=True)
    permission: Mapped[str] = mapped_column(String(100))
    is_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admins.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    actor_email: Mapped[str] = mapped_column(String(255), default="")
    actor_role: Mapped[str] = mapped_column(String(50), default="")
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str] = mapped_column(String(50), index=True)
    target_id: Mapped[str] = mapped_column(String(100), default="")
    old_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
