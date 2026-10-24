#!/usr/bin/env bash
# Run the CI gates locally, in CI's order, stopping at the first failure.
#
#   bash scripts/check.sh            # backend, then frontend
#   bash scripts/check.sh backend    # .github/workflows/backend_tests.yml
#
# The backend's database gates need a local Supabase stack (CLAUDE.md, Local
# Supabase); SUPABASE_WORKDIR names one started with another --workdir.
#   bash scripts/check.sh frontend   # .github/workflows/frontend_tests.yml
#
# Keep the steps in step with those workflows (tests/unit/test_check_script.py
# checks that both run every tools.lint gate).

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# A venv activated elsewhere (e.g. the main checkout from a worktree) must not
# stand in for this checkout's backend/.venv.
unset VIRTUAL_ENV

usage() {
  echo "usage: bash scripts/check.sh [backend|frontend]" >&2
  exit 2
}

gate() {
  local name=$1
  shift
  printf '\n==> %s\n' "$name"
  if ! "$@"; then
    printf '\ncheck.sh: gate failed: %s\n' "$name" >&2
    exit 1
  fi
}

backend_uv() {
  uv run --directory backend --locked "$@"
}

backend_tests_with_coverage() {
  backend_uv coverage run -m unittest discover -s tests -p "test_*.py" &&
    backend_uv coverage report
}

# The local Supabase stack's workdir: supabase/config.toml's unless set.
SUPABASE_WORKDIR=${SUPABASE_WORKDIR:-.}

# A path the Windows-native Supabase CLI and Python can open from Git Bash too.
native_path() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s
' "$1"; fi
}

# TEST_SUPABASE_* for the database tests: as set, or read from the running stack.
local_supabase_env() {
  if [[ -n "${TEST_SUPABASE_URL:-}" ]]; then
    return 0
  fi
  local exports
  if ! exports=$(bash scripts/supabase-test-env.sh "$SUPABASE_WORKDIR" 2>/dev/null); then
    cat >&2 <<EOF_HELP
check.sh: the database gates need a local Supabase stack. Start one with
  npx --prefix frontend supabase start --workdir $SUPABASE_WORKDIR
or set TEST_SUPABASE_URL, TEST_SUPABASE_DB_URL, TEST_SUPABASE_ANON_KEY and
TEST_SUPABASE_SERVICE_KEY (scripts/supabase-test-env.sh prints them).
EOF_HELP
    return 1
  fi
  eval "$exports"
}

backend_database_tests() {
  local_supabase_env &&
    backend_uv python -m unittest discover -s tests/db_integration -t .
}

backend_schema_snapshot() {
  local_supabase_env || return 1
  local dump status
  dump=$(mktemp)
  npx --prefix frontend supabase db dump --local --workdir "$SUPABASE_WORKDIR"     -f "$(native_path "$dump")" &&
    backend_uv python -m tools.check_schema_snapshot "$(native_path "$dump")"
  status=$?
  rm -f "$dump"
  return "$status"
}

frontend_npm() {
  npm --prefix frontend run "$@"
}

# Placeholder Supabase env, as in CI: the build reads no database.
frontend_build() {
  PUBLIC_SUPABASE_URL=http://127.0.0.1:9 \
    PUBLIC_SUPABASE_ANON_KEY=placeholder-anon-key \
    PUBLIC_ENABLE_NOTIFICATIONS=false \
    SUPABASE_SERVICE_KEY=placeholder-service-key \
    frontend_npm build
}

check_backend() {
  gate "backend: ruff check" backend_uv ruff check .
  gate "backend: ruff format --check" backend_uv ruff format --check .
  gate "backend: mypy" backend_uv mypy .
  # PYTHONUTF8: lint-imports crashes on Windows consoles without it.
  gate "backend: import contracts" env PYTHONUTF8=1 uv run --directory backend --locked lint-imports
  gate "backend: docstring budget" backend_uv python -m tools.lint.check_docstrings
  gate "backend: module size ratchet" backend_uv python -m tools.lint.check_module_size
  gate "backend: symbol reachability" backend_uv python -m tools.lint.check_symbol_reachability
  gate "backend: tests with coverage" backend_tests_with_coverage
  gate "backend: database tests" backend_database_tests
  gate "backend: migrations match the production schema" backend_schema_snapshot
}

check_frontend() {
  gate "frontend: lint" frontend_npm lint
  gate "frontend: typecheck" frontend_npm typecheck
  gate "frontend: tests with coverage" frontend_npm test:coverage
  gate "frontend: build" frontend_build
  # First run needs: npx --prefix frontend playwright install chromium
  gate "frontend: analytics E2E" frontend_npm test:e2e:analytics
}

case "${1:-all}" in
  backend) check_backend ;;
  frontend) check_frontend ;;
  all)
    check_backend
    check_frontend
    ;;
  *) usage ;;
esac

printf '\ncheck.sh: all gates passed\n'
