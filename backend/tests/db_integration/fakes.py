"""Fakes for the services around the database: IMAP, the LLM and Resend.

The database tests run app code for real against the local stack; only these
boundaries are replaced.
"""

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, Mock

from tests.fixtures.mock_helpers import create_mock_mail_message


def mail_message(uid: str, sender: str, **fields: Any) -> Mock:
    """An imap_tools message from ``sender``, received at a fixed UTC time."""
    fields.setdefault("date", datetime(2026, 10, 1, 14, 0, tzinfo=UTC))
    fields.setdefault("subject", f"Newsletter {uid}")
    return create_mock_mail_message(uid=uid, from_=sender, **fields)


class FakeMailbox:
    """A logged-in imap_tools mailbox holding ``messages``; records flag changes."""

    def __init__(self, messages: Iterable[Mock] = ()) -> None:
        self.messages = list(messages)
        self.flags: list[tuple[Any, Any, bool]] = []
        self.folder = Mock()

    def fetch(self, *_criteria: Any, **_options: Any) -> list[Mock]:
        return list(self.messages)

    def flag(self, uids: Any, flag: Any, value: bool) -> None:
        self.flags.append((uids, flag, value))

    def mailbox_class(self) -> MagicMock:
        """A stand-in for ``imap_tools.MailBox`` whose login yields this mailbox."""
        mailbox_class = MagicMock()
        mailbox_class.return_value.login.return_value.__enter__.return_value = self
        return mailbox_class


class FakeLlm:
    """Stands in for ``call_llm``: answers each prompt by its response schema."""

    def __init__(
        self,
        topics: Iterable[str] = (),
        summary: str = "A short summary.",
        developments: Iterable[str] = ("A council vote on the plan.",),
        weekly_summary: str = "The week in review.",
    ) -> None:
        self.answers = {
            "TopicsExtraction": {"topics": list(topics)},
            "Summary": {"summary": summary},
            "FactExtraction": {"developments": list(developments)},
            "WeeklySynthesis": {"summary": weekly_summary},
        }
        self.prompts: list[str] = []

    def __call__(self, _model: str, prompt: str, schema: dict[str, Any]) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.answers[schema["title"]])


class FakeResend:
    """Stands in for ``resend.Emails.send``; records each email it is given."""

    def __init__(self, fail_for: Iterable[str] = ()) -> None:
        self.fail_for = set(fail_for)
        self.sent: list[dict[str, Any]] = []

    def __call__(self, params: dict[str, Any]) -> dict[str, str]:
        if params["to"] in self.fail_for:
            raise RuntimeError(f"Resend rejected {params['to']}")
        self.sent.append(params)
        return {"id": f"email-{len(self.sent)}"}

    def recipients(self) -> list[str]:
        return [str(params["to"]) for params in self.sent]
