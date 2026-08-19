# ============================================================
# DB dump script (for sharing with teammates) - Windows PowerShell
# ------------------------------------------------------------
# Dumps only the shared seed data from the centagging DB safely as
# UTF-8 and saves it gzip-compressed into docker/db/init/.
# The official postgres image automatically runs every .sql /
# .sql.gz file under docker-entrypoint-initdb.d in alphabetical
# order the FIRST time the container starts with an empty volume
# (.sql.gz files are gunzipped automatically). So once this file
# is committed and shared, teammates just run `docker compose up -d`
# and the seed users, SKU catalog, images, and embeddings restore
# automatically after schema.sql creates the current schema.
#
# Run from the project root, with the db container already up:
#   powershell -File scripts\deploy\dump_db.ps1
#
# NOTE: This file intentionally contains only ASCII text. Windows
# PowerShell 5.1 (powershell.exe) reads .ps1 files without a BOM
# using the system ANSI codepage, which can garble non-ASCII
# characters (e.g. Korean) and break string parsing. Keeping this
# script ASCII-only avoids that problem entirely.
# ============================================================
$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $ProjectRoot

if (-not (Test-Path ".env")) {
    Write-Error "No .env file found. Please run this from the project root."
    exit 1
}

# Load POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD from .env
$envVars = @{}
Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
        $envVars[$Matches[1]] = $Matches[2]
    }
}
$DB      = if ($envVars.ContainsKey("POSTGRES_DB"))       { $envVars["POSTGRES_DB"] }       else { "centagging" }
$DB_USER = if ($envVars.ContainsKey("POSTGRES_USER"))     { $envVars["POSTGRES_USER"] }     else { "centagging" }
$DB_PASS = if ($envVars.ContainsKey("POSTGRES_PASSWORD")) { $envVars["POSTGRES_PASSWORD"] } else { "change-me" }

$OutDir       = "docker/db/init"
$OutFile      = Join-Path $OutDir "zz-sku-catalog-embeddings.sql.gz"
$ContainerSql = "/tmp/zz-sku-catalog-embeddings.sql"
$ContainerTmp = "/tmp/zz-sku-catalog-embeddings.sql.gz"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "Checking db container status..."
$running = docker compose ps -q db
if (-not $running) {
    Write-Error "The db container is not running. Start it first with 'docker compose up -d db'."
    exit 1
}

Write-Host "Dumping seed data and gzip-compressing it inside the container (UTF-8, avoids Korean text corruption)..."
# Important: PowerShell's '>' redirection defaults to UTF-16 and can corrupt
# Korean text. To avoid that, we create and compress the SQL file entirely
# inside the container, then copy the binary (.gz) file out byte-for-byte.
# Keeping pg_dump and gzip as sequential commands also prevents a failed
# pg_dump from being hidden by a successful gzip process.
docker compose exec -T -e PGPASSWORD=$DB_PASS db sh -c `
    "set -e; rm -f '$ContainerSql' '$ContainerTmp'; pg_dump -U '$DB_USER' -d '$DB' --encoding=UTF8 --no-owner --no-privileges --data-only --table=public.app_user --table=public.sku_catalog --table=public.sku_image > '$ContainerSql'; gzip -9 -n -c '$ContainerSql' > '$ContainerTmp'; rm -f '$ContainerSql'"
if ($LASTEXITCODE -ne 0) {
    docker compose exec -T db rm -f $ContainerSql $ContainerTmp
    throw "Failed to create the seed data dump. The existing host dump was not changed."
}

Write-Host "Copying the dump file from the container to the host..."
docker compose cp "db:$ContainerTmp" $OutFile
if ($LASTEXITCODE -ne 0) {
    docker compose exec -T db rm -f $ContainerSql $ContainerTmp
    throw "Failed to copy the seed data dump from the container."
}
docker compose exec -T db rm -f $ContainerTmp

$sizeKB = [math]::Round((Get-Item $OutFile).Length / 1KB, 1)
Write-Host ""
Write-Host "Done: $OutFile ($sizeKB KB)"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1) git add $OutFile"
Write-Host "  2) git commit -m ""chore: add DB dump for auto-restore"""
Write-Host "  3) git push"
Write-Host ""
Write-Host "For teammates (after cloning the repo):"
Write-Host "  docker compose up -d"
Write-Host "  (this restores the DB automatically only if the postgres_data volume is empty)"
Write-Host ""
Write-Host "  If someone already ran the DB before, they need to reset the volume first:"
Write-Host "  docker compose down -v"
Write-Host "  docker compose up -d"
