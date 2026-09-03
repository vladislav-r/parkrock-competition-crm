param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$TargetDatabase = "climbhub_restore_test",
    [string]$DatabaseUser = "climbhub",
    [string]$Container = "climbhub-postgres",
    [switch]$ConfirmRestore,
    [switch]$AllowWorkingDatabase
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmRestore) {
    throw "Для восстановления необходимо явно указать -ConfirmRestore."
}
if ($TargetDatabase -notmatch '^[a-zA-Z][a-zA-Z0-9_]*$') {
    throw "Недопустимое имя целевой базы данных."
}
if ($TargetDatabase -eq "climbhub" -and -not $AllowWorkingDatabase) {
    throw "Восстановление в рабочую базу запрещено без -AllowWorkingDatabase."
}

$resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path
$fileName = [System.IO.Path]::GetFileName($resolvedBackup)
$containerPath = "/tmp/restore-${fileName}"

try {
    & docker cp $resolvedBackup "${Container}:${containerPath}"
    if ($LASTEXITCODE -ne 0) { throw "Не удалось скопировать резервную копию в контейнер." }

    & docker exec $Container pg_restore --list $containerPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Файл не является исправной резервной копией PostgreSQL." }

    & docker exec $Container psql --username $DatabaseUser --dbname postgres --set ON_ERROR_STOP=1 `
        --command "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TargetDatabase' AND pid <> pg_backend_pid();"
    if ($LASTEXITCODE -ne 0) { throw "Не удалось завершить подключения к тестовой базе." }

    & docker exec $Container dropdb --username $DatabaseUser --if-exists $TargetDatabase
    if ($LASTEXITCODE -ne 0) { throw "Не удалось подготовить целевую базу." }
    & docker exec $Container createdb --username $DatabaseUser $TargetDatabase
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать целевую базу." }

    & docker exec $Container pg_restore --username $DatabaseUser --dbname $TargetDatabase `
        --exit-on-error --no-owner --no-privileges $containerPath
    if ($LASTEXITCODE -ne 0) { throw "Восстановление завершилось с ошибкой." }

    $tableCount = & docker exec $Container psql --username $DatabaseUser --dbname $TargetDatabase `
        --tuples-only --no-align --command "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';"
    if ($LASTEXITCODE -ne 0 -or [int]$tableCount -le 0) {
        throw "В восстановленной базе не найдены таблицы."
    }
    Write-Output "Восстановление завершено: база $TargetDatabase, таблиц: $tableCount"
}
finally {
    & docker exec $Container rm -f $containerPath 2>$null | Out-Null
}
