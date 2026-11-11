"""Database types whose public values are identical on SQLite and PostgreSQL."""
from datetime import timezone
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, Text
from sqlalchemy.types import TypeDecorator

DECIMAL_QUANTUM = Decimal("0.000001")
MAX_DECIMAL = Decimal("99999999999999.999999")


def decimal_text(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or abs(amount) > MAX_DECIMAL or amount != amount.quantize(DECIMAL_QUANTUM):
        raise ValueError("Value must fit an exact decimal(20, 6)")
    return format(amount.quantize(DECIMAL_QUANTUM), "f")


class ExactDecimal(TypeDecorator):
    """SQLite TEXT avoids its NUMERIC affinity silently converting to binary floats."""
    impl = Numeric(20, 6)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(Text() if dialect.name == "sqlite" else Numeric(20, 6))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        exact = decimal_text(value)
        return exact if dialect.name == "sqlite" else Decimal(exact)

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(str(value)).quantize(DECIMAL_QUANTUM)


class UTCDateTime(TypeDecorator):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Datetime values must include a timezone")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
