#!/bin/sh
# Mirror Supabase locally: pgvector resolves through the `extensions` schema, then apply migrations in order.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "ALTER ROLE \"$POSTGRES_USER\" SET search_path = \"\$user\", public, extensions"
for f in /migrations/*.sql; do
  echo "applying $f"
  psql -1 -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$f"
done
