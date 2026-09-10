import uuid
from datetime import date, datetime, time
from typing import Literal

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import ApplicationType, EventStage, ParticipantSource, SetStatus, Sex, UserRole
from app.participant_fields import normalize_merch_size


def normalize_staff_email(value: str) -> str:
    try:
        return validate_email(value, check_deliverability=False, test_environment=True).normalized
    except EmailNotValidError as error:
        raise ValueError("некорректный адрес") from error


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    assigned_route_id: uuid.UUID | None
    assigned_final_route_id: uuid.UUID | None
    permissions: list[str] = Field(default_factory=list)
    model_config = {"from_attributes": True}


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    assigned_route_id: uuid.UUID | None
    assigned_final_route_id: uuid.UUID | None
    is_active: bool
    version: int
    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=2, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole
    assigned_route_id: uuid.UUID | None = None
    assigned_final_route_id: uuid.UUID | None = None

    @field_validator("email", "full_name", mode="before")
    @classmethod
    def strip_user_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_staff_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("пароль не может состоять только из пробелов")
        return value


class UserUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: UserRole | None = None
    assigned_route_id: uuid.UUID | None = None
    assigned_final_route_id: uuid.UUID | None = None
    is_active: bool | None = None

    @field_validator("email", "full_name", mode="before")
    @classmethod
    def strip_optional_user_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        return normalize_staff_email(value) if value is not None else None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("пароль не может состоять только из пробелов")
        return value


class RolePermissionRead(BaseModel):
    role: UserRole
    permissions: list[str]


class RolePermissionsResponse(BaseModel):
    roles: list[RolePermissionRead]
    available_permissions: dict[str, str]


class RolePermissionUpdate(BaseModel):
    permissions: list[str]


class AuditRead(BaseModel):
    id: uuid.UUID
    actor_email: str
    actor_role: str
    action: str
    target_type: str
    target_id: str
    old_value: object | None
    new_value: object | None
    result: str
    created_at: datetime
    actor_name: str = ""
    target_label: str = ""
    details: str = ""


class AuditResponse(BaseModel):
    items: list[AuditRead]
    total: int


class SetRead(BaseModel):
    id: uuid.UUID
    name: str
    scheduled_on: date | None
    time_label: str
    capacity: int
    participant_count: int
    checked_in_count: int
    status: SetStatus
    confirmed_at: datetime | None
    version: int


class SetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scheduled_on: date | None = None
    start_time: time
    end_time: time
    capacity: int = Field(ge=1, le=10_000)

    @field_validator("name", mode="before")
    @classmethod
    def strip_set_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SetUpdate(SetCreate):
    expected_version: int = Field(ge=1)


class PublicSetRead(BaseModel):
    id: uuid.UUID
    name: str
    scheduled_on: date | None
    time_label: str
    capacity: int
    participant_count: int
    checked_in_count: int
    status: SetStatus
    confirmed_at: datetime | None


class RouteRead(BaseModel):
    id: uuid.UUID
    number: int
    name: str
    grade: str
    points: int
    is_active: bool
    version: int
    model_config = {"from_attributes": True}


class RouteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    grade: str = Field(min_length=1, max_length=20)

    @field_validator("name", "grade", mode="before")
    @classmethod
    def strip_route_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class RouteBulkCreate(BaseModel):
    count: int = Field(ge=1, le=100)
    grade: str = Field(min_length=1, max_length=20)


class RouteUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    grade: str | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None

    @field_validator("name", "grade", mode="before")
    @classmethod
    def strip_optional_route_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class RouteBulkPointsUpdate(BaseModel):
    from_grade: str = Field(min_length=1, max_length=20)
    to_grade: str = Field(min_length=1, max_length=20)
    points: int = Field(ge=0, le=1_000_000)
    expected_versions: dict[uuid.UUID, int]


class RouteGradePointRead(BaseModel):
    grade: str
    points: int | None
    effective_points: int
    expected_version: int
    route_count: int


class RouteGradePointsResponse(BaseModel):
    items: list[RouteGradePointRead]


class RouteGradePointInput(BaseModel):
    grade: str = Field(min_length=1, max_length=20)
    points: int | None = Field(default=None, ge=0, le=1_000_000)
    expected_version: int = Field(ge=1)


class RouteGradePointsUpdate(BaseModel):
    items: list[RouteGradePointInput]


class RouteGradePointsPreview(BaseModel):
    changed_grades: int
    affected_routes: int
    affected_participants: int


class GroupRead(BaseModel):
    id: uuid.UUID
    name: str
    sex: Sex
    min_age: int
    max_age: int | None
    version: int
    model_config = {"from_attributes": True}


class AgeCategoryInput(BaseModel):
    id: uuid.UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=1, max_length=100)
    sex: Sex
    min_age: int = Field(ge=0, le=120)
    max_age: int | None = Field(default=None, ge=0, le=120)
    finalist_count: int = Field(default=10, ge=0, le=1000)
    bronze_min_points: int | None = Field(default=None, ge=0)
    bronze_max_points: int | None = Field(default=None, ge=0)
    silver_min_points: int | None = Field(default=None, ge=0)
    silver_max_points: int | None = Field(default=None, ge=0)
    gold_min_points: int | None = Field(default=None, ge=0)
    gold_max_points: int | None = Field(default=None, ge=0)

    @field_validator("name", mode="before")
    @classmethod
    def strip_category_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class AgeCategoriesUpdate(BaseModel):
    categories: list[AgeCategoryInput] = Field(min_length=2)


class AgeCategoryRead(AgeCategoryInput):
    id: uuid.UUID
    expected_version: int
    participant_count: int


class AgeCategoriesResponse(BaseModel):
    categories: list[AgeCategoryRead]


class AgeCategoriesPreview(BaseModel):
    participant_count: int
    affected_participants: int
    unassigned_participants: int
    assignments: dict[str, int]
    transitions: list[dict[str, object]]


class EventRead(BaseModel):
    id: uuid.UUID
    title: str
    location: str
    starts_on: date
    stage: EventStage
    qualification_started_at: datetime | None
    final_started_at: datetime | None
    completed_at: datetime | None
    public_result_details_enabled: bool
    version: int
    participant_count: int
    sets: list[SetRead]
    routes: list[RouteRead]
    groups: list[GroupRead]


class ExportSettingsRead(BaseModel):
    competition_name: str
    location: str
    dates: str
    official_name: str
    official_qualification: str
    event_version: int


class ExportSettingsUpdate(BaseModel):
    competition_name: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)
    dates: str = Field(min_length=1, max_length=255)
    official_name: str = Field(min_length=1, max_length=255)
    official_qualification: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=1)

    @field_validator(
        "competition_name", "location", "dates", "official_name", "official_qualification",
        mode="before",
    )
    @classmethod
    def strip_export_fields(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class QualificationCategoryStatus(BaseModel):
    id: uuid.UUID
    name: str
    result_count: int
    final_result_count: int
    finalist_count: int
    participates_in_final: bool
    confirmed: bool
    confirmed_at: datetime | None
    final_confirmed: bool
    final_confirmed_at: datetime | None
    expected_version: int


class FinalStatusResponse(BaseModel):
    event_id: uuid.UUID
    stage: EventStage
    qualification_started_at: datetime | None
    final_started_at: datetime | None
    completed_at: datetime | None
    event_version: int
    categories: list[QualificationCategoryStatus]
    all_categories_confirmed: bool
    all_final_categories_confirmed: bool
    snapshot_results: int
    snapshot_finalists: int


class QualificationResultReview(BaseModel):
    participant_id: uuid.UUID
    start_number: int
    full_name: str
    club: str
    completed_count: int
    points: int
    place: int
    is_finalist: bool
    exit_order: int | None


class QualificationCategoryReview(BaseModel):
    category_id: uuid.UUID
    category_name: str
    confirmed: bool
    results: list[QualificationResultReview]


class FinalRouteRead(BaseModel):
    id: uuid.UUID
    number: int
    name: str
    assigned_categories: list[str] = Field(default_factory=list)


class FinalCategorySetup(BaseModel):
    id: uuid.UUID
    name: str
    short_name: str
    participates: bool
    finalist_count: int
    route_ids: list[uuid.UUID] = Field(default_factory=list)


class FinalSetupResponse(BaseModel):
    event_version: int
    routes: list[FinalRouteRead]
    categories: list[FinalCategorySetup]


class FinalCategoryRoutesUpdate(BaseModel):
    expected_event_version: int = Field(ge=1)
    route_ids: list[uuid.UUID] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def distinct_routes(self):
        if len(set(self.route_ids)) != 4:
            raise ValueError("Для категории нужно выбрать четыре разные трассы")
        return self


class FinalCategoryParticipationUpdate(BaseModel):
    expected_event_version: int = Field(ge=1)
    participates: bool


class FinalAttemptInput(BaseModel):
    route_id: uuid.UUID
    zone_attempt: int | None = Field(default=None, ge=1, le=999)
    top_attempt: int | None = Field(default=None, ge=1, le=999)


class FinalResultUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    attempts: list[FinalAttemptInput] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def distinct_attempt_routes(self):
        if len({item.route_id for item in self.attempts}) != 4:
            raise ValueError("Результаты должны быть указаны для каждой из четырех трасс без повторов")
        return self


class FinalRouteAttemptRead(BaseModel):
    route_id: uuid.UUID
    route_number: int
    route_name: str
    zone_attempt: int | None
    top_attempt: int | None
    score: float


class FinalParticipantResultRead(BaseModel):
    id: uuid.UUID
    participant_id: uuid.UUID
    start_number: int
    full_name: str
    club: str
    qualification_place: int
    exit_order: int | None
    score: float
    top_count: int
    zone_count: int
    top_attempts: int
    zone_attempts: int
    place: int | None
    has_result: bool
    version: int
    attempts: list[FinalRouteAttemptRead]


class FinalCategoryResultsResponse(BaseModel):
    category_id: uuid.UUID
    category_name: str
    routes: list[FinalRouteRead]
    results: list[FinalParticipantResultRead]


class JudgeFinalRouteRead(BaseModel):
    id: uuid.UUID
    number: int
    name: str


class JudgeParticipantRead(BaseModel):
    final_result_id: uuid.UUID
    participant_id: uuid.UUID
    category_id: uuid.UUID
    category_name: str
    start_number: int
    full_name: str
    club: str
    qualification_place: int
    exit_order: int | None
    version: int
    locked: bool
    zone_attempt: int | None
    top_attempt: int | None
    score: float


class JudgeWorkspaceResponse(BaseModel):
    event_id: uuid.UUID
    event_title: str
    stage: EventStage
    route: JudgeFinalRouteRead
    participants: list[JudgeParticipantRead]
    conflicts: list[dict] = Field(default_factory=list)
    submission_conflict_id: uuid.UUID | None = None


class JudgeConflictResolution(BaseModel):
    choice: Literal["server", "judge"]
    expected_version: int = Field(ge=1)


class JudgeResultCreate(BaseModel):
    expected_version: int = Field(ge=1)
    zone_attempt: int | None = Field(default=None, ge=1, le=999)
    top_attempt: int | None = Field(default=None, ge=1, le=999)

    @model_validator(mode="after")
    def attempts_are_consistent(self):
        if self.zone_attempt is not None and self.top_attempt is not None and self.zone_attempt > self.top_attempt:
            raise ValueError("Попытка зоны не может быть позже попытки топа")
        return self


class AscentRead(BaseModel):
    route_id: uuid.UUID
    completed: bool


class ParticipantRead(BaseModel):
    id: uuid.UUID
    club_id: uuid.UUID
    set_id: uuid.UUID
    checked_in_at: datetime | None
    start_number: int
    surname: str
    name: str
    patronymic: str
    birth_date: date
    birth_year: int
    sex: Sex
    sport_rank: str
    club: str
    representative: str
    application_type: ApplicationType
    merch_size: str | None
    is_paid: bool
    merch_issued: bool
    source: ParticipantSource
    import_operation_id: uuid.UUID | None
    group_name: str
    completed_count: int
    points: int
    ascents: list[AscentRead]
    version: int


class ApplicationRead(BaseModel):
    id: uuid.UUID
    filename: str
    file_size: int
    participant_count: int
    duplicate_rows: int
    overflow_sets: int
    status: Literal["pending", "imported"]
    uploaded_at: datetime
    imported_at: datetime | None
    import_count: int
    model_config = {"from_attributes": True}


class AscentUpdate(BaseModel):
    completed: bool
    expected_version: int = Field(ge=1)


class ParticipantResultsUpdate(BaseModel):
    completed_route_ids: list[uuid.UUID]
    expected_version: int = Field(ge=1)


class MoveParticipant(BaseModel):
    set_id: uuid.UUID
    expected_version: int = Field(ge=1)


class ParticipantCreate(BaseModel):
    set_id: uuid.UUID
    allow_overflow: bool = False
    surname: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    patronymic: str = Field(default="", max_length=100)
    birth_date: date
    sex: Sex
    sport_rank: str = Field(min_length=1, max_length=50)
    club: str = Field(min_length=1, max_length=200)
    representative: str = Field(default="", max_length=200)
    merch_size: str | None = Field(default=None, max_length=30)

    @field_validator("surname", "name", "patronymic", "sport_rank", "club", "representative", "merch_size", mode="before")
    @classmethod
    def strip_participant_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("merch_size", mode="before")
    @classmethod
    def validate_merch_size(cls, value: object) -> str | None:
        return normalize_merch_size(value)


class VersionedAction(BaseModel):
    expected_version: int = Field(ge=1)


class ParticipantReceptionUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    checked_in: bool | None = None
    is_paid: bool | None = None
    merch_issued: bool | None = None

    @model_validator(mode="after")
    def contains_change(self):
        if self.checked_in is None and self.is_paid is None and self.merch_issued is None:
            raise ValueError("Укажите хотя бы один изменяемый статус")
        return self


class ClubMemberRead(BaseModel):
    id: uuid.UUID
    start_number: int
    full_name: str
    set_id: uuid.UUID
    set_name: str
    application_type: ApplicationType
    checked_in: bool
    is_paid: bool
    merch_size: str | None
    merch_issued: bool
    version: int


class ClubRead(BaseModel):
    id: uuid.UUID
    version: int
    name: str
    representative: str
    participant_count: int
    collective_count: int
    checked_in_count: int
    paid_count: int
    merch_issued_count: int
    members: list[ClubMemberRead]


class ClubUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    representative: str = Field(default="", max_length=200)
    expected_version: int = Field(ge=1)
    merge_duplicate: bool = False

    @field_validator("name", "representative", mode="before")
    @classmethod
    def strip_club_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class ClubBulkAction(BaseModel):
    participant_ids: list[uuid.UUID] = Field(min_length=1)
    expected_versions: dict[uuid.UUID, int]
    checked_in: bool | None = None
    is_paid: bool | None = None
    merch_issued: bool | None = None

    @model_validator(mode="after")
    def valid_action(self):
        changes = [self.checked_in is not None, self.is_paid is not None, self.merch_issued is not None]
        if sum(changes) != 1:
            raise ValueError("Массовая операция должна изменять ровно один статус")
        if len(set(self.participant_ids)) != len(self.participant_ids):
            raise ValueError("Список участников содержит повторы")
        if set(self.expected_versions) != set(self.participant_ids):
            raise ValueError("Версии должны быть указаны для всех участников")
        return self


class PublicResultRead(BaseModel):
    participant_id: uuid.UUID
    place: int | None
    start_number: int
    full_name: str
    club: str
    completed_count: int | None
    points: int | None
    has_result: bool
    is_finalist: bool
    is_finisher: bool
    medal: Literal["gold", "silver", "bronze"] | None
    group_name: str
    set_id: uuid.UUID


class PublicResultsResponse(BaseModel):
    event_id: uuid.UUID
    event_title: str
    location: str
    starts_on: date
    stage: EventStage
    details_enabled: bool
    updated_at: datetime | None
    groups: list[str]
    final_groups: list[str]
    sets: list[PublicSetRead]
    results: list[PublicResultRead]


class PublicFinalRouteRead(BaseModel):
    number: int
    name: str


class PublicFinalAttemptRead(BaseModel):
    route_number: int
    zone_attempt: int | None
    top_attempt: int | None


class PublicFinalResultRead(BaseModel):
    participant_id: uuid.UUID
    place: int | None
    start_number: int
    full_name: str
    club: str
    qualification_place: int
    exit_order: int | None
    has_result: bool
    score: float
    top_count: int
    zone_count: int
    attempts: list[PublicFinalAttemptRead]


class PublicFinalResultsResponse(BaseModel):
    category_name: str
    routes: list[PublicFinalRouteRead]
    results: list[PublicFinalResultRead]
    updated_at: datetime | None


class CompletedRouteRead(BaseModel):
    number: int
    name: str
    grade: str
    points: int


class PublicParticipantRead(BaseModel):
    participant_id: uuid.UUID
    place: int | None
    is_finalist: bool
    is_finisher: bool
    medal: Literal["gold", "silver", "bronze"] | None
    start_number: int
    full_name: str
    club: str
    group_name: str
    completed_count: int | None
    points: int | None
    has_result: bool
    completed_routes: list[CompletedRouteRead]


class PublicResultDetailsUpdate(BaseModel):
    enabled: bool
    expected_version: int = Field(ge=1)
