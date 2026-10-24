#!/usr/bin/env bash
# Print the TEST_SUPABASE_* exports the database tests read, for a running
# local stack (`supabase start`):
#
#   eval "$(bash scripts/supabase-test-env.sh)"            # supabase/config.toml's stack
#   eval "$(bash scripts/supabase-test-env.sh <workdir>)"  # a stack started with --workdir
#
# Reads only `supabase status` of a local stack; the tests still check every
# URL and key is local before connecting.

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

workdir=${1:-.}
status=$(npx --prefix frontend supabase status -o env --workdir "$workdir")
eval "$status"

printf 'export TEST_SUPABASE_URL=%q\n' "$API_URL"
printf 'export TEST_SUPABASE_DB_URL=%q\n' "$DB_URL"
printf 'export TEST_SUPABASE_ANON_KEY=%q\n' "$ANON_KEY"
printf 'export TEST_SUPABASE_SERVICE_KEY=%q\n' "$SERVICE_ROLE_KEY"
