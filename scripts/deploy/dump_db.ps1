# ============================================================
# DB dump script (for sharing with teammates) - Windows PowerShell
# ------------------------------------------------------------
# Dumps the centagging DB (running via docker compose) safely as
# UTF-8 and saves it gzip-compressed into docker/db/init/.
# The official postgres image automatically runs every .sql /
# .sql.gz file under docker-entrypoint-initdb.d in alphabetical
# order the FIRST time the container starts with an empty volume
# (.sql.gz files are gunzipped automatically). So once this file
# is committed and shared, teammates just run `docker compose up -d`
# and the DB (schema + data + embeddings) restores automatically.
#
# Run from the project root, with the db container already up:
#   powershell -File scripts\deploy\dump_db.ps1
#
# NOTE: This file intentionally contains only ASCII text. Windows
# PowerShell 5.1 (powershell.exe) reads .ps1 files without a BOM
# using the system ANSI codepage, which can garble non-ASCII
# characters (e.g. Korean) and break string parsing. Keeping this
# script ASCII-only avoids that problem entirely.
#
# NOTE (data-only dump): This script dumps data only (--data-only).
# The schema (tables/indexes/constraints) is always owned by
# schema.sql, so a schema change made later (e.g. a new table with
# a foreign key into an existing table) can never make an older
# dump's DROP/CREATE statements conflict with the current schema.
# (Dumping the schema too, via --clean, previously caused restores
# to fail outright once a newer table referenced an older table's
# primary key that the dump tried to drop.)
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

# For version control: bump this to v2, v3, ... when you want to record a
# new data snapshot. IMPORTANT: when committing a new version, also delete
# (git rm) the previous version's file under docker/db/init/. If more than
# one data dump is left in that folder, Docker runs ALL of them on init and
# re-inserts the same rows twice, which fails on a primary-key conflict.
# Only one data dump file should ever exist in that folder at a time.
$DumpVersion = "v1"

$OutDir       = "docker/db/init"
$OutFile      = Join-Path $OutDir "zz-sku-catalog-embeddings-$DumpVersion.sql.gz"
$ContainerTmp = "/tmp/zz-sku-catalog-embeddings-$DumpVersion.sql.gz"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "Checking db container status..."
$running = docker compose ps -q db
if (-not $running) {
    Write-Error "The db container is not running. Start it first with 'docker compose up -d db'."
    exit 1
}

Write-Host "Running pg_dump and gzip-compressing it inside the container (UTF-8, avoids Korean text corruption)..."
# Important: PowerShell's '>' redirection defaults to UTF-16 and can corrupt
# Korean text. To avoid that, we run pg_dump | gzip entirely inside the
# container's own shell to produce a binary (.gz) file, then copy that file
# out byte-for-byte with `docker compose cp`. The host console's encoding is
# never involved, so this is safe.
docker compose exec -T -e PGPASSWORD=$DB_PASS db sh -c `
    "pg_dump -U '$DB_USER' -d '$DB' --encoding=UTF8 --no-owner --no-privileges --data-only --disable-triggers | gzip -9 > '$ContainerTmp'"

Write-Host "Copying the dump file from the container to the host..."
docker compose cp "db:$ContainerTmp" $OutFile
docker compose exec -T db rm -f $ContainerTmp

$sizeKB = [math]::Round((Get-Item $OutFile).Length / 1KB, 1)
Write-Host ""
Write-Host "Done: $OutFile ($sizeKB KB)"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1) git add $OutFile"
Write-Host "     (if an older version file is still under docker/db/init/, git rm it too)"
Write-Host "  2) git commit -m ""chore: add DB dump for auto-restore ($DumpVersion)"""
Write-Host "  3) git push"
Write-Host ""
Write-Host "For teammates (after cloning the repo):"
Write-Host "  docker compose up -d"
Write-Host "  (this restores the DB automatically only if the postgres_data volume is empty)"
Write-Host ""
Write-Host "  If someone already ran the DB before, they need to reset the volume first:"
Write-Host "  docker compose down -v"
Write-Host "  docker compose up -d"
Write-Host ""
Write-Host "Note: this dump is data-only. schema.sql runs first and creates"
Write-Host "the tables/indexes/constraints; this file only fills in the data."
