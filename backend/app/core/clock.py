from datetime import UTC, datetime


def utcnow() -> datetime:
    """Server UTC, stored naive so SQLite and Postgres round-trip identically."""
    return datetime.now(UTC).replace(tzinfo=None)
