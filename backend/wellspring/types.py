"""Database types whose public values are identical on SQLite and PostgreSQL."""
from datetime import timezone
from decimal import Decimal, InvalidOperation
import sqlite3

from sqlalchemy import DateTime, Numeric, Text, event
from sqlalchemy.engine import Engine
from sqlalchemy.types import TypeDecorator

WEIGHT_QUANTUM = Decimal("0.000001")
MAX_WEIGHT = Decimal("99999999999999.999999")


def weight_text(value):
    amount = Decimal(str(value))
    if not amount.is_finite() or abs(amount) > MAX_WEIGHT or amount != amount.quantize(WEIGHT_QUANTUM):
        raise ValueError("Weight must fit an exact decimal(20, 6)")
    return format(amount.quantize(WEIGHT_QUANTUM), "f")


def valid_weight(value):
    try:
        weight_text(value)
        return 1
    except (InvalidOperation, ValueError, TypeError):
        return 0


@event.listens_for(Engine, "connect")
def register_sqlite_decimal(connection, _record):
    if not isinstance(connection, sqlite3.Connection):
        return
    connection.create_function("wellspring_decimal_valid", 1, valid_weight, deterministic=True)
    connection.create_function("wellspring_decimal_compare", 2,
        lambda a, b: (Decimal(str(a)) > Decimal(str(b))) - (Decimal(str(a)) < Decimal(str(b))), deterministic=True)
    connection.create_function("wellspring_decimal_subtract", 2,
        lambda a, b: weight_text(Decimal(str(a)) - Decimal(str(b))), deterministic=True)
    connection.create_collation("WELLSPRING_DECIMAL",
        lambda a, b: (Decimal(a) > Decimal(b)) - (Decimal(a) < Decimal(b)))


class ExactDecimal(TypeDecorator):
    """SQLite TEXT avoids its NUMERIC affinity silently converting to binary floats."""
    impl = Numeric(20, 6)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(Text() if dialect.name == "sqlite" else Numeric(20, 6))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        exact = weight_text(value)
        return exact if dialect.name == "sqlite" else Decimal(exact)

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(str(value)).quantize(WEIGHT_QUANTUM)


# Preserve existing weight imports/migrations while sharing exact storage with
# other explicitly labelled physical units. This adapter never converts units.
ExactWeight = ExactDecimal


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
