param(
    [string]$OutputDirectory,
    [string]$Database = "climbhub",
    [string]$DatabaseUser = "climbhub",
    [string]$Container = "climbhub-postgres",
    [ValidateSet("manual", "automatic")]
    [string]$Source = "manual",
    [int]$AutomaticRetentionCount = 14
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $root "backups"
}
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($resolvedOutput) | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$fileName = "${Database}-${timestamp}-${Source}.dump"
$hostPath = Join-Path $resolvedOutput $fileName
$containerPath = "/tmp/${fileName}"

try {
    & docker exec $Container pg_dump --username $DatabaseUser --dbname $Database --format custom --file $containerPath
    if ($LASTEXITCODE -ne 0) { throw "Не удалось создать дамп базы данных." }

    & docker cp "${Container}:${containerPath}" $hostPath
    if ($LASTEXITCODE -ne 0) { throw "Не удалось скопировать дамп из контейнера." }

    & docker exec $Container pg_restore --list $containerPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Созданный дамп не прошел проверку pg_restore." }

    $size = (Get-Item -LiteralPath $hostPath).Length
    if ($size -le 0) { throw "Создан пустой файл резервной копии." }
    if ($Source -eq "automatic" -and $AutomaticRetentionCount -gt 0) {
        Get-ChildItem -LiteralPath $resolvedOutput -Filter "${Database}-*-automatic.dump" -File |
            Sort-Object LastWriteTime -Descending |
            Select-Object -Skip $AutomaticRetentionCount |
            Remove-Item -Force
    }
    Write-Output $hostPath
}
finally {
    & docker exec $Container rm -f $containerPath 2>$null | Out-Null
}
