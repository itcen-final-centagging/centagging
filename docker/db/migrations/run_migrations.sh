#!/bin/sh

set -eu

for migration_path in /migrations/*.sql; do
  psql --set=ON_ERROR_STOP=1 \
    --host="$POSTGRES_HOST" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --file="$migration_path"
done
