export type SetStatus = "draft" | "confirmed" | "reopened";
export type CompetitionSet = {
  id: string;
  name: string;
  scheduled_on: string | null;
  time_label: string;
  capacity: number;
  participant_count: number;
  checked_in_count: number;
  status: SetStatus;
  confirmed_at: string | null;
  version: number;
};
export type Route = {
  id: string;
  number: number;
  name: string;
  grade: string;
  points: number;
  is_active: boolean;
  version: number;
};
export type RouteGradePoint = {
  grade: string;
  points: number | null;
  effective_points: number;
  expected_version: number;
  route_count: number;
};
export type EventStage =
  "preparation" | "qualification" | "final" | "completed";
export type AbsoluteStage = "qualification" | "final" | "overall";
export type AbsoluteResults = {
  stage: AbsoluteStage; event_stage: EventStage; available: boolean; provisional: boolean;
  results: Array<{ participant_id: string; start_number: number; full_name: string; club: string; group_name: string;
    qualification_points: number | null; final_points: number | null; score: number | null; place: number | null; has_result: boolean }>;
};
export const getAbsoluteResults = (stage: AbsoluteStage) => request<AbsoluteResults>(`/api/v1/public/absolute-results?stage=${stage}`);
export type ExportItem = { key: string; title: string; block: "qualification" | "final" | "absolute" | "other";
  row_count: number; available: boolean; reason: string; warnings: string[] };
export const getExportCatalog = (token: string) => request<{ stage: EventStage; items: ExportItem[] }>("/api/v1/admin/exports/catalog", {}, token);
export async function downloadExport(token: string, item: ExportItem, confirmIncomplete = false) {
  const response = await fetch(`${API_URL}/api/v1/admin/exports/files/${encodeURIComponent(item.key)}.xlsx?confirm_incomplete=${confirmIncomplete}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Не удалось подготовить выгрузку" }));
    throw new ApiError(response.status, body.detail, typeof body.detail === "string" ? body.detail : body.detail.message ?? "Не удалось подготовить выгрузку");
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url; link.download = `${item.title}.xlsx`; document.body.appendChild(link); link.click(); link.remove();
  URL.revokeObjectURL(url);
}
export type EventInfo = {
  id: string;
  title: string;
  location: string;
  starts_on: string;
  stage: EventStage;
  qualification_started_at: string | null;
  final_started_at: string | null;
  completed_at: string | null;
  public_result_details_enabled: boolean;
  version: number;
  participant_count: number;
  sets: CompetitionSet[];
  routes: Route[];
  groups: Array<{
    id: string;
    name: string;
    sex: "male" | "female";
    min_age: number;
    max_age: number | null;
    version: number;
  }>;
};
export type ExportSettings = {
  competition_name: string;
  location: string;
  dates: string;
  official_name: string;
  official_qualification: string;
  event_version: number;
};
export type Medal = "gold" | "silver" | "bronze";
export type PublicResult = {
  participant_id: string;
  place: number | null;
  start_number: number;
  full_name: string;
  club: string;
  completed_count: number | null;
  points: number | null;
  has_result: boolean;
  is_finalist: boolean;
  is_finisher: boolean;
  medal: Medal | null;
  group_name: string;
  set_id: string;
};
export type PublicResults = {
  event_id: string;
  event_title: string;
  location: string;
  starts_on: string;
  stage: EventStage;
  details_enabled: boolean;
  updated_at: string | null;
  groups: string[];
  final_groups: string[];
  sets: Array<Omit<CompetitionSet, "version">>;
  results: PublicResult[];
};
export type PublicParticipant = {
  participant_id: string;
  place: number | null;
  is_finalist: boolean;
  is_finisher: boolean;
  medal: Medal | null;
  start_number: number;
  full_name: string;
  club: string;
  group_name: string;
  completed_count: number | null;
  points: number | null;
  has_result: boolean;
  completed_routes: Array<{
    number: number;
    name: string;
    grade: string;
    points: number;
  }>;
};
export type PublicFinalResults = {
  category_name: string;
  routes: Array<{ number: number; name: string }>;
  results: Array<{
    participant_id: string;
    place: number | null;
    start_number: number;
    full_name: string;
    club: string;
    qualification_place: number;
    exit_order: number | null;
    has_result: boolean;
    score: number;
    top_count: number;
    zone_count: number;
    attempts: Array<{
      route_number: number;
      zone_attempt: number | null;
      top_attempt: number | null;
    }>;
  }>;
  updated_at: string | null;
};

const CYRILLIC_SLUG: Record<string, string> = {
  а: "a",
  б: "b",
  в: "v",
  г: "g",
  д: "d",
  е: "e",
  ё: "e",
  ж: "zh",
  з: "z",
  и: "i",
  й: "y",
  к: "k",
  л: "l",
  м: "m",
  н: "n",
  о: "o",
  п: "p",
  р: "r",
  с: "s",
  т: "t",
  у: "u",
  ф: "f",
  х: "h",
  ц: "ts",
  ч: "ch",
  ш: "sh",
  щ: "sch",
  ы: "y",
  э: "e",
  ю: "yu",
  я: "ya",
  ь: "",
  ъ: "",
};

export function groupSlug(value: string) {
  return value
    .toLocaleLowerCase("ru")
    .split("")
    .map((char) => CYRILLIC_SLUG[char] ?? char)
    .join("")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}
export type ApplicationType = "collective" | "individual";
export type Participant = {
  id: string;
  club_id: string;
  set_id: string;
  checked_in_at: string | null;
  start_number: number;
  surname: string;
  name: string;
  patronymic: string;
  birth_date: string;
  birth_year: number;
  sex: "male" | "female";
  sport_rank: string;
  club: string;
  representative: string;
  application_type: ApplicationType;
  merch_size: string | null;
  is_paid: boolean;
  merch_issued: boolean;
  source: "import_file" | "manual";
  import_operation_id: string | null;
  group_name: string;
  completed_count: number;
  points: number;
  ascents: Array<{ route_id: string; completed: boolean }>;
  version: number;
};
export type ClubMember = {
  id: string;
  start_number: number;
  full_name: string;
  set_id: string;
  set_name: string;
  application_type: ApplicationType;
  checked_in: boolean;
  is_paid: boolean;
  merch_size: string | null;
  merch_issued: boolean;
  version: number;
};
export type Club = {
  id: string;
  version: number;
  name: string;
  representative: string;
  participant_count: number;
  collective_count: number;
  checked_in_count: number;
  paid_count: number;
  merch_issued_count: number;
  members: ClubMember[];
};
export type ImportPreviewRow = {
  row_number: number;
  values: Record<string, string>;
  errors: Record<string, string>;
  duplicate: boolean;
  valid: boolean;
};
export type ImportPreview = {
  filename: string;
  application_type: ApplicationType;
  total_rows: number;
  valid_rows: number;
  duplicate_rows: number;
  error_rows: number;
  rows: ImportPreviewRow[];
  overflow: SetOverflow[];
  can_import: boolean;
};
export type ApplicationFile = {
  id: string;
  filename: string;
  file_size: number;
  participant_count: number;
  duplicate_rows: number;
  overflow_sets: number;
  status: "pending" | "imported";
  uploaded_at: string;
  imported_at: string | null;
  import_count: number;
};
export type ParticipantCreatePayload = {
  set_id: string;
  allow_overflow: boolean;
  surname: string;
  name: string;
  patronymic: string;
  birth_date: string;
  sex: "male" | "female";
  sport_rank: string;
  club: string;
  representative: string;
  merch_size: string | null;
};
export type UserRole =
  "reception" | "secretary" | "chief_judge" | "administrator" | "route_judge";
export type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  assigned_route_id: string | null;
  assigned_final_route_id: string | null;
  permissions: string[];
};
export type StaffUser = {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  assigned_route_id: string | null;
  assigned_final_route_id: string | null;
  is_active: boolean;
  version: number;
};
export type RoleMatrix = {
  roles: Array<{ role: UserRole; permissions: string[] }>;
  available_permissions: Record<string, string>;
};
export type AuditEntry = {
  id: string;
  actor_email: string;
  actor_name: string;
  actor_role: string;
  action: string;
  target_type: string;
  target_id: string;
  target_label: string;
  details: string;
  old_value: unknown;
  new_value: unknown;
  result: string;
  created_at: string;
};
export type AgeCategory = {
  id?: string;
  expected_version?: number;
  name: string;
  sex: "male" | "female";
  min_age: number;
  max_age: number | null;
  finalist_count: number;
  bronze_min_points: number | null;
  bronze_max_points: number | null;
  silver_min_points: number | null;
  silver_max_points: number | null;
  gold_min_points: number | null;
  gold_max_points: number | null;
  participant_count?: number;
};
export type CategoryPreview = {
  participant_count: number;
  affected_participants: number;
  unassigned_participants: number;
  assignments: Record<string, number>;
  transitions: Array<{ from: string; to: string; count: number }>;
};
export type FinalStatus = {
  event_id: string;
  stage: EventStage;
  qualification_started_at: string | null;
  final_started_at: string | null;
  completed_at: string | null;
  event_version: number;
  all_categories_confirmed: boolean;
  all_final_categories_confirmed: boolean;
  snapshot_results: number;
  snapshot_finalists: number;
  categories: Array<{
    id: string;
    name: string;
    result_count: number;
    final_result_count: number;
    finalist_count: number;
    participates_in_final: boolean;
    confirmed: boolean;
    confirmed_at: string | null;
    final_confirmed: boolean;
    final_confirmed_at: string | null;
    expected_version: number;
  }>;
};
export type QualificationCategoryReview = {
  category_id: string;
  category_name: string;
  confirmed: boolean;
  results: Array<{
    participant_id: string;
    start_number: number;
    full_name: string;
    club: string;
    completed_count: number;
    points: number;
    place: number;
    is_finalist: boolean;
    exit_order: number | null;
  }>;
};
export type FinalRoute = {
  id: string;
  number: number;
  name: string;
  assigned_categories: string[];
};
export type FinalSetup = {
  event_version: number;
  routes: FinalRoute[];
  categories: Array<{
    id: string;
    name: string;
    short_name: string;
    participates: boolean;
    finalist_count: number;
    route_ids: string[];
  }>;
};
export type FinalCategoryResults = {
  category_id: string;
  category_name: string;
  routes: FinalRoute[];
  results: Array<{
    id: string;
    participant_id: string;
    start_number: number;
    full_name: string;
    club: string;
    qualification_place: number;
    exit_order: number | null;
    has_result: boolean;
    score: number;
    top_count: number;
    zone_count: number;
    top_attempts: number;
    zone_attempts: number;
    place: number | null;
    version: number;
    attempts: Array<{
      route_id: string;
      route_number: number;
      route_name: string;
      zone_attempt: number | null;
      top_attempt: number | null;
      score: number;
    }>;
  }>;
};
export type JudgeParticipant = {
  final_result_id: string;
  participant_id: string;
  category_id: string;
  category_name: string;
  start_number: number;
  full_name: string;
  club: string;
  qualification_place: number;
  exit_order: number | null;
  version: number;
  locked: boolean;
  zone_attempt: number | null;
  top_attempt: number | null;
  score: number;
};
export type JudgeWorkspace = {
  event_id: string;
  event_title: string;
  stage: EventStage;
  route: { id: string; number: number; name: string };
  participants: JudgeParticipant[];
  conflicts?: JudgeConflict[];
  submission_conflict_id?: string | null;
};
export type JudgeAttemptValue = { zone_attempt: number | null; top_attempt: number | null };
export type JudgeConflict = {
  id: string; final_result_id?: string; start_number: number; full_name: string;
  route_name: string; judge_name: string; submitted: JudgeAttemptValue;
  server_at_submission: JudgeAttemptValue; current?: JudgeAttemptValue | null;
  expected_version: number; can_apply_judge: boolean;
};
export const getJudgeConflicts = (token: string) =>
  request<JudgeConflict[]>("/api/v1/admin/final/judge-conflicts", {}, token);
export const resolveJudgeConflict = (token: string, conflict: JudgeConflict, choice: "server" | "judge", operationId: string) =>
  request(`/api/v1/admin/final/judge-conflicts/${conflict.id}/resolve`, {
    method: "POST", headers: operationHeaders(operationId),
    body: JSON.stringify({ choice, expected_version: conflict.expected_version }),
  }, token);
export type BackupSummary = {
  event?: {
    title: string;
    location: string;
    starts_on: string;
    stage: EventStage;
  } | null;
  counts: Record<string, number>;
};
export type BackupItem = {
  filename: string;
  created_at: string;
  size_bytes: number;
  source:
    | "manual"
    | "automatic"
    | "pre-restore"
    | "pre-reset"
    | "factory-zero"
    | "stage-transition"
    | "pre-rollback"
    | "upload"
    | "legacy";
  verified_at: string | null;
  checksum_sha256: string | null;
  summary: BackupSummary | null;
  differences: Record<string, number> | null;
  note: string;
};
export type BackupList = {
  items: BackupItem[];
  current: BackupSummary;
  directory: string;
};
export type CompetitionResetTarget =
  | "stage"
  | "qualification_results"
  | "final_results"
  | "final_setup"
  | "applications"
  | "participants"
  | "reception"
  | "clubs"
  | "sets"
  | "set_statuses"
  | "routes"
  | "categories"
  | "judge_assignments"
  | "publication"
  | "all";
export type CompetitionResetStatus = {
  stage: EventStage;
  qualification_started: boolean;
  counts: Record<Exclude<CompetitionResetTarget, "stage" | "all">, number>;
};

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ??
  (process.env.NODE_ENV === "production" ? "" : "http://localhost:8001");

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const isNativeForm =
    options.body instanceof URLSearchParams || options.body instanceof FormData;
  const requestOptions = {
    ...options,
    headers: {
      ...(isNativeForm ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  };
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, requestOptions);
  } catch (error) {
    if (!options.method || options.method === "GET") throw error;
    response = await fetch(`${API_URL}${path}`, requestOptions);
  }
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Ошибка запроса" }));
    const message =
      typeof body.detail === "string"
        ? body.detail
        : typeof body.detail?.message === "string"
          ? body.detail.message
          : Array.isArray(body.detail)
            ? body.detail
                .map(
                  (item: { loc?: string[]; msg?: string }) =>
                    `${item.loc?.at(-1) ?? "Поле"}: ${item.msg ?? "некорректное значение"}`,
                )
                .join("; ")
            : "Ошибка запроса";
    throw new ApiError(response.status, body.detail, message);
  }
  return response.json() as Promise<T>;
}

function operationHeaders(operationId?: string) {
  return { "X-Operation-Id": operationId ?? crypto.randomUUID() };
}

export function getPublicResults(group = "", setId = "") {
  const params = new URLSearchParams();
  if (group) params.set("group", group);
  if (setId) params.set("set_id", setId);
  return request<PublicResults>(`/api/v1/public/results?${params}`);
}
export const getPublicParticipant = (id: string) =>
  request<PublicParticipant>(`/api/v1/public/participants/${id}`);
export const getPublicFinalResults = (group: string) =>
  request<PublicFinalResults>(
    `/api/v1/public/final-results?${new URLSearchParams({ group })}`,
  );
export async function login(email: string, password: string) {
  const form = new URLSearchParams({ username: email, password });
  const result = await request<{ access_token: string }>("/api/v1/auth/login", {
    method: "POST",
    body: form,
  });
  return result.access_token;
}
export const getCurrentUser = (token: string) =>
  request<CurrentUser>("/api/v1/auth/me", {}, token);
export const logoutSession = (token: string) =>
  request<{ status: string }>("/api/v1/auth/logout", { method: "POST" }, token);
export const getAdminEvent = (token: string) =>
  request<EventInfo>("/api/v1/admin/event", {}, token);
export const updatePublicResultDetails = (
  token: string,
  enabled: boolean,
  expectedVersion: number,
) =>
  request<EventInfo>(
    "/api/v1/admin/event/public-result-details",
    {
      method: "PATCH",
      headers: operationHeaders(),
      body: JSON.stringify({ enabled, expected_version: expectedVersion }),
    },
    token,
  );
export const getExportSettings = (token: string) =>
  request<ExportSettings>("/api/v1/admin/exports/settings", {}, token);
export const updateExportSettings = (
  token: string,
  settings: Omit<ExportSettings, "event_version">,
  expectedVersion: number,
) =>
  request<ExportSettings>(
    "/api/v1/admin/exports/settings",
    {
      method: "PUT",
      headers: operationHeaders(),
      body: JSON.stringify({ ...settings, expected_version: expectedVersion }),
    },
    token,
  );
export const getCompetitionResetStatus = (token: string) =>
  request<CompetitionResetStatus>(
    "/api/v1/admin/competition/reset-status",
    {},
    token,
  );
export const resetCompetitionData = (
  token: string,
  target: CompetitionResetTarget,
) =>
  request<{
    status: string;
    target: CompetitionResetTarget;
    deleted: number;
    safety_backup: string;
    zero_backup: string | null;
  }>(
    "/api/v1/admin/competition/reset",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ target, confirmation: "СБРОСИТЬ" }),
    },
    token,
  );
export const getBackups = (token: string) =>
  request<BackupList>("/api/v1/admin/backups", {}, token);
export const createBackup = (token: string, note = "") =>
  request<BackupItem>(
    `/api/v1/admin/backups?${new URLSearchParams({ note })}`,
    { method: "POST", headers: operationHeaders() },
    token,
  );
export const verifyBackup = (token: string, filename: string) =>
  request<BackupItem>(
    `/api/v1/admin/backups/${encodeURIComponent(filename)}/verify`,
    { method: "POST", headers: operationHeaders() },
    token,
  );
export const deleteBackup = (
  token: string,
  filename: string,
  confirmation: string,
) =>
  request<{ status: string; filename: string }>(
    `/api/v1/admin/backups/${encodeURIComponent(filename)}`,
    {
      method: "DELETE",
      headers: operationHeaders(),
      body: JSON.stringify({ confirmation }),
    },
    token,
  );
export const restoreBackup = (
  token: string,
  filename: string,
  confirmation: string,
) =>
  request<{ status: string; restored: BackupItem; safety_backup: BackupItem }>(
    `/api/v1/admin/backups/${encodeURIComponent(filename)}/restore`,
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ confirmation }),
    },
    token,
  );
export const uploadBackup = (token: string, file: File, note = "") => {
  const body = new FormData();
  body.set("file", file);
  body.set("note", note);
  return request<BackupItem>(
    "/api/v1/admin/backups/upload",
    { method: "POST", headers: operationHeaders(), body },
    token,
  );
};
export async function downloadBackup(token: string, filename: string) {
  const response = await fetch(
    `${API_URL}/api/v1/admin/backups/${encodeURIComponent(filename)}/download`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok)
    throw new ApiError(
      response.status,
      null,
      "Не удалось скачать резервную копию",
    );
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}
export const getParticipants = (token: string, setId = "", search = "") => {
  const params = new URLSearchParams();
  if (setId) params.set("set_id", setId);
  if (search) params.set("search", search);
  return request<Participant[]>(
    `/api/v1/admin/participants?${params}`,
    {},
    token,
  );
};
export const updateAscent = (
  token: string,
  participantId: string,
  routeId: string,
  completed: boolean,
  expectedVersion: number,
) =>
  request<Participant>(
    `/api/v1/admin/participants/${participantId}/routes/${routeId}`,
    {
      method: "PATCH",
      headers: operationHeaders(),
      body: JSON.stringify({ completed, expected_version: expectedVersion }),
    },
    token,
  );
export const updateParticipantResults = (
  token: string,
  participantId: string,
  completedRouteIds: string[],
  expectedVersion: number,
) =>
  request<Participant>(
    `/api/v1/admin/participants/${participantId}/results`,
    {
      method: "PUT",
      headers: operationHeaders(),
      body: JSON.stringify({
        completed_route_ids: completedRouteIds,
        expected_version: expectedVersion,
      }),
    },
    token,
  );
export const updateParticipantSet = (
  token: string,
  participantId: string,
  setId: string,
  expectedVersion: number,
) =>
  request<Participant>(
    `/api/v1/admin/participants/${participantId}/set`,
    {
      method: "PATCH",
      headers: operationHeaders(),
      body: JSON.stringify({
        set_id: setId,
        expected_version: expectedVersion,
      }),
    },
    token,
  );
export const confirmParticipantCheckIn = (
  token: string,
  participantId: string,
  expectedVersion: number,
) =>
  request<Participant>(
    `/api/v1/admin/participants/${participantId}/check-in`,
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export type ReceptionStatusUpdate = {
  checked_in?: boolean;
  is_paid?: boolean;
  merch_issued?: boolean;
};
export const updateParticipantReception = (
  token: string,
  participantId: string,
  expectedVersion: number,
  update: ReceptionStatusUpdate,
) =>
  request<Participant>(
    `/api/v1/admin/participants/${participantId}/reception`,
    {
      method: "PATCH",
      headers: operationHeaders(),
      body: JSON.stringify({ ...update, expected_version: expectedVersion }),
    },
    token,
  );
export const getClubs = (token: string) =>
  request<Club[]>("/api/v1/admin/clubs", {}, token);
export type ClubUpdateResult = {
  id: string;
  name: string;
  representative: string;
  version: number;
  updated_participants: number;
  merged: boolean;
};
export const updateClub = (
  token: string,
  clubId: string,
  name: string,
  representative: string,
  expectedVersion: number,
  mergeDuplicate = false,
) =>
  request<ClubUpdateResult>(
    `/api/v1/admin/clubs/${clubId}`,
    {
      method: "PATCH",
      headers: operationHeaders(),
      body: JSON.stringify({
        name,
        representative,
        expected_version: expectedVersion,
        merge_duplicate: mergeDuplicate,
      }),
    },
    token,
  );
export const updateClubReceptionBulk = (
  token: string,
  clubId: string,
  members: ClubMember[],
  update: ReceptionStatusUpdate,
) =>
  request<{ updated: number }>(
    `/api/v1/admin/clubs/${clubId}/bulk`,
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({
        participant_ids: members.map((item) => item.id),
        expected_versions: Object.fromEntries(
          members.map((item) => [item.id, item.version]),
        ),
        ...update,
      }),
    },
    token,
  );
export const confirmSet = (
  token: string,
  setId: string,
  expectedVersion: number,
) =>
  request(
    `/api/v1/admin/sets/${setId}/confirm`,
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const reopenSet = (
  token: string,
  setId: string,
  expectedVersion: number,
) =>
  request(
    `/api/v1/admin/sets/${setId}/reopen`,
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export type SetPayload = {
  name: string;
  scheduled_on: string | null;
  start_time: string;
  end_time: string;
  capacity: number;
};
export const createSet = (token: string, payload: SetPayload) =>
  request<CompetitionSet>(
    "/api/v1/admin/sets",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify(payload),
    },
    token,
  );
export const updateSet = (
  token: string,
  setId: string,
  payload: SetPayload,
  expectedVersion: number,
) =>
  request<CompetitionSet>(
    `/api/v1/admin/sets/${setId}`,
    {
      method: "PATCH",
      headers: operationHeaders(),
      body: JSON.stringify({ ...payload, expected_version: expectedVersion }),
    },
    token,
  );
export const deleteSet = (
  token: string,
  setId: string,
  expectedVersion: number,
) =>
  request<{ status: string }>(
    `/api/v1/admin/sets/${setId}?expected_version=${expectedVersion}`,
    { method: "DELETE", headers: operationHeaders() },
    token,
  );
export type SetOverflow = {
  set_id: string;
  set_name: string;
  capacity: number;
  current: number;
  incoming: number;
  projected: number;
  overflow_by: number;
};
export const previewParticipantsImport = (
  token: string,
  file: File,
  applicationType: ApplicationType,
) => {
  const body = new FormData();
  body.set("file", file);
  return request<ImportPreview>(
    `/api/v1/admin/participants/import?preview=true&application_type=${applicationType}`,
    { method: "POST", headers: operationHeaders(), body },
    token,
  );
};
export const importParticipants = (
  token: string,
  file: File,
  applicationType: ApplicationType,
  skipDuplicates = false,
  allowOverflow = false,
) => {
  const body = new FormData();
  body.set("file", file);
  return request<{
    imported: number;
    skipped_duplicates: number;
    first_start_number: number;
    last_start_number: number;
  }>(
    `/api/v1/admin/participants/import?application_type=${applicationType}&skip_duplicates=${skipDuplicates}&allow_overflow=${allowOverflow}`,
    { method: "POST", headers: operationHeaders(), body },
    token,
  );
};
export const submitApplication = (file: File) => {
  const body = new FormData();
  body.set("file", file);
  return request<ApplicationFile>("/api/v1/public/applications", {
    method: "POST",
    body,
  });
};
export const getApplications = (token: string) =>
  request<ApplicationFile[]>("/api/v1/admin/applications", {}, token);
export const importApplication = (
  token: string,
  applicationId: string,
  skipDuplicates = false,
  allowOverflow = false,
) =>
  request<{
    imported: number;
    skipped_duplicates: number;
    first_start_number: number;
    last_start_number: number;
    status: string;
  }>(
    `/api/v1/admin/applications/${applicationId}/import?skip_duplicates=${skipDuplicates}&allow_overflow=${allowOverflow}`,
    { method: "POST", headers: operationHeaders() },
    token,
  );
export const deleteApplication = (token: string, applicationId: string) =>
  request<{ status: string; filename: string }>(
    `/api/v1/admin/applications/${applicationId}`,
    { method: "DELETE", headers: operationHeaders() },
    token,
  );
export async function downloadApplication(
  token: string,
  application: ApplicationFile,
) {
  const response = await fetch(
    `${API_URL}/api/v1/admin/applications/${application.id}/download`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Не удалось скачать заявку" }));
    throw new ApiError(
      response.status,
      body.detail,
      typeof body.detail === "string"
        ? body.detail
        : "Не удалось скачать заявку",
    );
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download = application.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}
export const createParticipant = (
  token: string,
  payload: ParticipantCreatePayload,
) =>
  request<Participant>(
    "/api/v1/admin/participants",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify(payload),
    },
    token,
  );
export const clearParticipants = (token: string, setId?: string) =>
  request<{ deleted: number; scope: string }>(
    `/api/v1/admin/demo/participants${setId ? `?set_id=${setId}` : ""}`,
    { method: "DELETE", headers: operationHeaders() },
    token,
  );
export const seedDemoParticipants = (token: string) =>
  request<{ created: number; per_group: number }>(
    "/api/v1/admin/demo/participants",
    { method: "POST", headers: operationHeaders() },
    token,
  );
export const seedDemoQualificationResults = (token: string) =>
  request<{ updated_participants: number; completed_ascents: number }>(
    "/api/v1/admin/demo/qualification-results",
    { method: "POST", headers: operationHeaders() },
    token,
  );
export const seedDemoFinalResults = (token: string) =>
  request<{ updated_categories: number; updated_finalists: number }>(
    "/api/v1/admin/demo/final-results",
    { method: "POST", headers: operationHeaders() },
    token,
  );
export const createRoute = (
  token: string,
  payload: { name: string; grade: string },
) =>
  request<Route>(
    "/api/v1/admin/routes",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify(payload),
    },
    token,
  );
export const createRoutes = (token: string, count: number, grade: string) =>
  request<Route[]>(
    "/api/v1/admin/routes/bulk",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ count, grade }),
    },
    token,
  );
export const updateRoute = (
  token: string,
  routeId: string,
  payload: Partial<Pick<Route, "name" | "grade" | "is_active">>,
  expectedVersion: number,
) =>
  request<Route>(
    `/api/v1/admin/routes/${routeId}`,
    {
      method: "PATCH",
      headers: operationHeaders(),
      body: JSON.stringify({ ...payload, expected_version: expectedVersion }),
    },
    token,
  );
export const deleteRoute = (
  token: string,
  routeId: string,
  expectedVersion: number,
) =>
  request<{ status: string; number: number }>(
    `/api/v1/admin/routes/${routeId}?expected_version=${expectedVersion}`,
    { method: "DELETE", headers: operationHeaders() },
    token,
  );
export const deleteAllRoutes = (token: string) =>
  request<{ deleted: number }>(
    "/api/v1/admin/routes",
    { method: "DELETE", headers: operationHeaders() },
    token,
  );
export const updateRoutePointsBulk = (
  token: string,
  payload: {
    from_grade: string;
    to_grade: string;
    points: number;
    expected_versions: Record<string, number>;
  },
) =>
  request<{ updated: number }>(
    "/api/v1/admin/routes/bulk-points",
    {
      method: "PATCH",
      headers: operationHeaders(),
      body: JSON.stringify(payload),
    },
    token,
  );
export const getRouteGradePoints = (token: string) =>
  request<{ items: RouteGradePoint[] }>(
    "/api/v1/admin/route-grade-points",
    {},
    token,
  );
export const previewRouteGradePoints = (
  token: string,
  items: Array<{
    grade: string;
    points: number | null;
    expected_version: number;
  }>,
) =>
  request<{
    changed_grades: number;
    affected_routes: number;
    affected_participants: number;
  }>(
    "/api/v1/admin/route-grade-points/preview",
    { method: "POST", body: JSON.stringify({ items }) },
    token,
  );
export const updateRouteGradePoints = (
  token: string,
  items: Array<{
    grade: string;
    points: number | null;
    expected_version: number;
  }>,
) =>
  request<{ items: RouteGradePoint[] }>(
    "/api/v1/admin/route-grade-points",
    {
      method: "PUT",
      headers: operationHeaders(),
      body: JSON.stringify({ items }),
    },
    token,
  );
export const getUsers = (token: string) =>
  request<StaffUser[]>("/api/v1/admin/users", {}, token);
export const getUserFinalRoutes = (token: string) =>
  request<FinalRoute[]>("/api/v1/admin/users/final-routes", {}, token);
export const createUser = (
  token: string,
  payload: {
    email: string;
    full_name: string;
    password: string;
    role: UserRole;
    assigned_final_route_id: string | null;
  },
) =>
  request<StaffUser>(
    "/api/v1/admin/users",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify(payload),
    },
    token,
  );
export const updateUser = (
  token: string,
  userId: string,
  payload: Partial<Omit<StaffUser, "id" | "version">> & {
    expected_version: number;
    password?: string;
  },
) =>
  request<StaffUser>(
    `/api/v1/admin/users/${userId}`,
    {
      method: "PATCH",
      headers: operationHeaders(),
      body: JSON.stringify(payload),
    },
    token,
  );
export const getRoleMatrix = (token: string) =>
  request<RoleMatrix>("/api/v1/admin/roles", {}, token);
export const updateRolePermissions = (
  token: string,
  role: UserRole,
  permissions: string[],
) =>
  request<{ role: UserRole; permissions: string[] }>(
    `/api/v1/admin/roles/${role}/permissions`,
    {
      method: "PUT",
      headers: operationHeaders(),
      body: JSON.stringify({ permissions }),
    },
    token,
  );
export const getAudit = (
  token: string,
  filters: { action?: string; actor?: string; result?: string } = {},
) => {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return request<{ items: AuditEntry[]; total: number }>(
    `/api/v1/admin/audit?${params}`,
    {},
    token,
  );
};
export const getAgeCategories = (token: string) =>
  request<{ categories: AgeCategory[] }>("/api/v1/admin/categories", {}, token);
export const previewAgeCategories = (
  token: string,
  categories: AgeCategory[],
) =>
  request<CategoryPreview>(
    "/api/v1/admin/categories/preview",
    { method: "POST", body: JSON.stringify({ categories }) },
    token,
  );
export const updateAgeCategories = (token: string, categories: AgeCategory[]) =>
  request<{
    updated: number;
    affected_participants: number;
    unassigned_participants: number;
  }>(
    "/api/v1/admin/categories",
    {
      method: "PUT",
      headers: operationHeaders(),
      body: JSON.stringify({ categories }),
    },
    token,
  );
export const getFinalStatus = (token: string) =>
  request<FinalStatus>("/api/v1/admin/final", {}, token);
export const getFinalSetup = (token: string) =>
  request<FinalSetup>("/api/v1/admin/final/setup", {}, token);
export const updateFinalCategoryParticipation = (
  token: string,
  groupId: string,
  participates: boolean,
  expectedEventVersion: number,
) =>
  request<FinalSetup>(
    `/api/v1/admin/final/categories/${groupId}/participation`,
    {
      method: "PUT",
      headers: operationHeaders(),
      body: JSON.stringify({
        participates,
        expected_event_version: expectedEventVersion,
      }),
    },
    token,
  );
export const updateFinalCategoryRoutes = (
  token: string,
  groupId: string,
  routeIds: string[],
  expectedEventVersion: number,
) =>
  request<FinalSetup>(
    `/api/v1/admin/final/categories/${groupId}/routes`,
    {
      method: "PUT",
      headers: operationHeaders(),
      body: JSON.stringify({
        route_ids: routeIds,
        expected_event_version: expectedEventVersion,
      }),
    },
    token,
  );
export const getFinalCategoryResults = (token: string, groupId: string) =>
  request<FinalCategoryResults>(
    `/api/v1/admin/final/categories/${groupId}/final-results`,
    {},
    token,
  );
export const updateFinalParticipantResults = (
  token: string,
  groupId: string,
  participantId: string,
  expectedVersion: number,
  attempts: Array<{
    route_id: string;
    zone_attempt: number | null;
    top_attempt: number | null;
  }>,
) =>
  request<FinalCategoryResults>(
    `/api/v1/admin/final/categories/${groupId}/participants/${participantId}/final-results`,
    {
      method: "PUT",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion, attempts }),
    },
    token,
  );
export const confirmFinalCategory = (
  token: string,
  groupId: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    `/api/v1/admin/final/categories/${groupId}/final-confirm`,
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const reopenFinalCategory = (
  token: string,
  groupId: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    `/api/v1/admin/final/categories/${groupId}/final-reopen`,
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const confirmAllFinalCategories = (
  token: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    "/api/v1/admin/final/final-results/confirm-all",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const reopenAllFinalCategories = (
  token: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    "/api/v1/admin/final/final-results/reopen-all",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const getJudgeWorkspace = (token: string) =>
  request<JudgeWorkspace>("/api/v1/judge/workspace", {}, token);
export const saveJudgeResult = (
  token: string,
  finalResultId: string,
  expectedVersion: number,
  zoneAttempt: number | null,
  topAttempt: number | null,
  operationId?: string,
) =>
  request<JudgeWorkspace>(
    `/api/v1/judge/results/${finalResultId}?preserve_conflict=true`,
    {
      method: "PUT",
      headers: operationHeaders(operationId),
      body: JSON.stringify({
        expected_version: expectedVersion,
        zone_attempt: zoneAttempt,
        top_attempt: topAttempt,
      }),
    },
    token,
  );
export const getQualificationCategoryResults = (
  token: string,
  groupId: string,
) =>
  request<QualificationCategoryReview>(
    `/api/v1/admin/final/categories/${groupId}/results`,
    {},
    token,
  );
export async function downloadQualificationSnapshotCsv(
  token: string,
  groupId: string,
  categoryName: string,
) {
  const response = await fetch(
    `${API_URL}/api/v1/admin/final/categories/${groupId}/snapshot.csv`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Не удалось подготовить выгрузку" }));
    throw new ApiError(
      response.status,
      body.detail,
      typeof body.detail === "string"
        ? body.detail
        : "Не удалось подготовить выгрузку",
    );
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download = `снимок-квалификации-${categoryName}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}
export async function downloadProtocolXlsx(
  token: string,
  stage: "qualification" | "final",
  groupId: string,
  categoryName: string,
) {
  const response = await fetch(
    `${API_URL}/api/v1/admin/exports/${stage}/${groupId}.xlsx`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok) {
    const body = await response
      .json()
      .catch(() => ({ detail: "Не удалось подготовить протокол" }));
    throw new ApiError(
      response.status,
      body.detail,
      typeof body.detail === "string"
        ? body.detail
        : "Не удалось подготовить протокол",
    );
  }
  const link = document.createElement("a");
  link.href = URL.createObjectURL(await response.blob());
  link.download =
    stage === "qualification"
      ? `протокол-квалификации-${categoryName}.xlsx`
      : `итоговый-протокол-${categoryName}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}
export const confirmQualificationCategory = (
  token: string,
  groupId: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    `/api/v1/admin/final/categories/${groupId}/confirm`,
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const reopenQualificationCategory = (
  token: string,
  groupId: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    `/api/v1/admin/final/categories/${groupId}/reopen`,
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const startQualification = (token: string, expectedVersion: number) =>
  request<FinalStatus>(
    "/api/v1/admin/final/qualification/start",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const cancelQualification = (token: string, expectedVersion: number) =>
  request<FinalStatus>(
    "/api/v1/admin/final/qualification/cancel",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const confirmAllQualificationCategories = (
  token: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    "/api/v1/admin/final/qualification/confirm-all",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const reopenAllQualificationCategories = (
  token: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    "/api/v1/admin/final/qualification/reopen-all",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const startFinal = (token: string, expectedVersion: number) =>
  request<FinalStatus>(
    "/api/v1/admin/final/start",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const cancelFinalDevelopment = (
  token: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    "/api/v1/admin/final/cancel",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const completeFestival = (token: string, expectedVersion: number) =>
  request<FinalStatus>(
    "/api/v1/admin/final/complete",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
export const reopenCompletedFestival = (
  token: string,
  expectedVersion: number,
) =>
  request<FinalStatus>(
    "/api/v1/admin/final/reopen",
    {
      method: "POST",
      headers: operationHeaders(),
      body: JSON.stringify({ expected_version: expectedVersion }),
    },
    token,
  );
