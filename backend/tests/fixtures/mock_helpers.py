"""Helper functions for creating mocked external services."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import Mock


def create_mock_supabase(return_data: Optional[List[Dict[str, Any]]] = None):
    """
    Create a mocked Supabase client with chainable query builder.

    Args:
        return_data: Data to return from execute() call

    Returns:
        Mock Supabase client with chainable methods
    """
    mock = Mock()

    # Make all query builder methods return the mock itself (chainable)
    mock.table.return_value = mock
    mock.select.return_value = mock
    mock.eq.return_value = mock
    mock.in_.return_value = mock
    mock.not_.return_value = mock
    mock.is_.return_value = mock
    mock.order.return_value = mock
    mock.limit.return_value = mock
    mock.single.return_value = mock
    mock.insert.return_value = mock
    mock.update.return_value = mock
    mock.ilike.return_value = mock
    mock.filter.return_value = mock

    # execute() returns mock response with data
    mock_response = Mock()
    mock_response.data = return_data if return_data is not None else []
    mock.execute.return_value = mock_response

    return mock


def create_mock_ollama_client(response_content: str = '{"topics": []}'):
    """
    Create a mocked Ollama client.

    Args:
        response_content: JSON string to return from chat()

    Returns:
        Mock Ollama client
    """
    mock_client = Mock()
    mock_response = Mock()
    mock_response.message.content = response_content
    mock_client.chat.return_value = mock_response
    return mock_client


def create_mock_mail_message(
    uid: str = "test_123",
    from_: str = "alderman@ward1.org",
    subject: str = "Test Newsletter",
    date=None,
    html: str = "<html><body>Test content</body></html>",
    text: str = "Test content",
    to: Optional[List[str]] = None,
):
    """Create a mocked imap_tools MailMessage object."""
    msg = Mock()
    msg.uid = uid
    msg.from_ = from_
    msg.subject = subject
    msg.date = date or datetime.now()
    msg.html = html
    msg.text = text
    msg.to = to or ["recipient@example.com"]
    return msg


def create_mock_requests_response(
    status_code: int = 200,
    text: str = "<html>Content</html>",
    raise_error: Optional[Exception] = None,
):
    """Create a mocked requests Response object."""
    mock_response = Mock()
    mock_response.status_code = status_code
    mock_response.text = text

    if raise_error:
        mock_response.raise_for_status.side_effect = raise_error
    else:
        mock_response.raise_for_status.return_value = None

    return mock_response
