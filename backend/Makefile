unit-test:
	uv run python -m notifications.test_matcher --queue
	uv run python -m notifications.test_matcher --queue
	uv run python -m notifications.process_notification_queue --daily-digest --dry-run
	uv run python -m notifications.process_notification_queue --daily-digest
	uv run python -m notifications.process_notification_queue --daily-digest --batch-id 2026-01-21

