"""The local-only guard rejects production-shaped URLs and keys."""

import base64
import json
import unittest
from unittest.mock import patch

from tests.db_integration.local_guard import (
    NOT_LOCAL_EXIT_STATUS,
    NotLocalDatabaseError,
    abort_unless_local,
    abort_unless_local_postgres,
    ensure_local_key,
    ensure_local_postgres_url,
    ensure_local_supabase,
    ensure_local_url,
)

# The demo service-role key every `supabase start` prints.
LOCAL_SERVICE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)


def _unsigned_jwt(claims: dict[str, object]) -> str:
    def encode(part: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(part).encode()).decode().rstrip("=")

    return f"{encode({'alg': 'HS256', 'typ': 'JWT'})}.{encode(claims)}.signature"


HOSTED_SERVICE_KEY = _unsigned_jwt(
    {"iss": "supabase", "ref": "abcdefghijklmnopqrst", "role": "service_role"}
)


class TestEnsureLocalUrl(unittest.TestCase):
    def test_accepts_loopback_hosts(self) -> None:
        for url in (
            "http://127.0.0.1:54321",
            "http://localhost:54321/rest/v1",
            "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
            "http://[::1]:54321",
        ):
            with self.subTest(url=url):
                ensure_local_url(url)

    def test_rejects_hosted_and_pooler_hosts(self) -> None:
        for url in (
            "https://abcdefghijklmnopqrst.supabase.co",
            "postgresql://postgres.abcdefghijklmnopqrst:pw@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
            "postgresql://postgres:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres",
            "http://127.0.0.1.example.com:54321",
            "http://localhost.supabase.co",
            "",
            "not a url",
        ):
            with self.subTest(url=url), self.assertRaises(NotLocalDatabaseError):
                ensure_local_url(url)


class TestEnsureLocalPostgresUrl(unittest.TestCase):
    def test_accepts_the_local_stack(self) -> None:
        ensure_local_postgres_url(
            "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
        )
        ensure_local_postgres_url(
            "postgresql://postgres:postgres@localhost:54322/postgres?hostaddr=127.0.0.1"
        )

    def test_rejects_settings_that_override_the_host(self) -> None:
        local = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
        for url in (
            f"{local}?host=db.abcdefghijklmnopqrst.supabase.co",
            f"{local}?host=127.0.0.1,db.abcdefghijklmnopqrst.supabase.co",
            f"{local}?hostaddr=203.0.113.7",
            f"{local}?service=production",
            f"{local}?servicefile=/tmp/pg_service.conf",
            "postgresql://postgres:pw@db.abcdefghijklmnopqrst.supabase.co:5432/postgres",
            f"{local}?not_a_setting=1",
        ):
            with self.subTest(url=url), self.assertRaises(NotLocalDatabaseError):
                ensure_local_postgres_url(url)


class TestPostgresEnvironmentDefaults(unittest.TestCase):
    local = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

    def test_rejects_libpq_environment_that_redirects_the_connection(self) -> None:
        for environ in (
            {"PGHOSTADDR": "203.0.113.7"},
            {"PGSERVICE": "production"},
            {"PGSERVICEFILE": "/tmp/pg_service.conf"},
        ):
            with (
                self.subTest(environ=environ),
                self.assertRaises(NotLocalDatabaseError),
            ):
                ensure_local_postgres_url(self.local, environ)

    def test_accepts_a_loopback_hostaddr_and_unrelated_variables(self) -> None:
        ensure_local_postgres_url(self.local, {"PGHOSTADDR": "127.0.0.1"})
        ensure_local_postgres_url(self.local, {"PGHOST": "db.x.supabase.co"})


class TestEnsureLocalKey(unittest.TestCase):
    def test_accepts_the_local_demo_key(self) -> None:
        ensure_local_key(LOCAL_SERVICE_KEY)

    def test_rejects_a_key_naming_a_hosted_project(self) -> None:
        with self.assertRaisesRegex(NotLocalDatabaseError, "abcdefghijklmnopqrst"):
            ensure_local_key(HOSTED_SERVICE_KEY)

    def test_rejects_a_demo_issuer_with_a_project_ref(self) -> None:
        with self.assertRaises(NotLocalDatabaseError):
            ensure_local_key(_unsigned_jwt({"iss": "supabase-demo", "ref": "abc"}))

    def test_rejects_other_issuers_and_non_jwt_keys(self) -> None:
        for key in (
            _unsigned_jwt({"iss": "supabase", "role": "anon"}),
            _unsigned_jwt({"role": "anon"}),
            "sb_secret_abcdefghijklmnopqrstuv",
            "placeholder-service-key",
            "a.!!!.c",
            "",
        ):
            with self.subTest(key=key), self.assertRaises(NotLocalDatabaseError):
                ensure_local_key(key)


class TestEnsureLocalSupabase(unittest.TestCase):
    def test_needs_both_url_and_key_local(self) -> None:
        ensure_local_supabase("http://127.0.0.1:54321", LOCAL_SERVICE_KEY)
        with self.assertRaises(NotLocalDatabaseError):
            ensure_local_supabase("http://127.0.0.1:54321", HOSTED_SERVICE_KEY)
        with self.assertRaises(NotLocalDatabaseError):
            ensure_local_supabase("https://abc.supabase.co", LOCAL_SERVICE_KEY)


class TestAbortUnlessLocal(unittest.TestCase):
    def test_returns_when_local(self) -> None:
        with patch("tests.db_integration.local_guard.os._exit") as exit_process:
            abort_unless_local("http://127.0.0.1:54321", LOCAL_SERVICE_KEY)
            abort_unless_local(
                "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
            )
        exit_process.assert_not_called()

    def test_ends_the_process_for_a_redirected_postgres_url(self) -> None:
        with (
            patch("tests.db_integration.local_guard.os._exit") as exit_process,
            patch("sys.stderr"),
        ):
            abort_unless_local_postgres(
                "postgresql://postgres:postgres@127.0.0.1:54322/postgres?host=db.x.supabase.co"
            )
        exit_process.assert_called_once_with(NOT_LOCAL_EXIT_STATUS)

    def test_ends_the_process_for_a_hosted_url_or_key(self) -> None:
        for url, key in (
            ("https://abc.supabase.co", None),
            ("http://127.0.0.1:54321", HOSTED_SERVICE_KEY),
        ):
            with (
                self.subTest(url=url),
                patch("tests.db_integration.local_guard.os._exit") as exit_process,
                patch("sys.stderr"),
            ):
                abort_unless_local(url, key)
                exit_process.assert_called_once_with(NOT_LOCAL_EXIT_STATUS)


if __name__ == "__main__":
    unittest.main()
