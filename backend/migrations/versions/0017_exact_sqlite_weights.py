"""Preserve SQLite's existing six-place values and use exact decimal text thereafter.

Historical binary floating-point precision cannot be reconstructed. Values outside
the public decimal range, negative balances and invalid values stop this migration
before any schema changes so an operator can investigate the original database.
"""
from decimal import Decimal
from alembic import op
import sqlalchemy as sa
from wellspring.types import weight_text

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

TABLES = {
    "evidence": ("balance",),
    "weight_events": ("delta",),
    "evidence_inventory_observations": ("book_weight", "observed_weight", "difference"),
}
CHECKS = {
    "evidence": ("ck_evidence_exact_balance", "wellspring_decimal_valid(balance) = 1 AND wellspring_decimal_compare(balance, '0') >= 0"),
    "weight_events": ("ck_weight_event_exact_delta", "wellspring_decimal_valid(delta) = 1"),
    "evidence_inventory_observations": ("ck_inventory_exact_weights", "wellspring_decimal_valid(book_weight) = 1 AND wellspring_decimal_valid(observed_weight) = 1 AND wellspring_decimal_valid(difference) = 1 AND wellspring_decimal_compare(book_weight, '0') >= 0 AND wellspring_decimal_compare(observed_weight, '0') >= 0"),
}


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        return
    snapshots = {}
    for table, columns in TABLES.items():
        snapshots[table] = []
        for row in connection.execute(sa.text(f"SELECT id, {', '.join(columns)} FROM {table}")).mappings():
            values = {"id": row["id"]}
            for column in columns:
                # Match the previous Numeric(20, 6) API conversion, not a fresh
                # interpretation of the originally entered (unrecoverable) value.
                value = row[column]
                try:
                    exact = weight_text(format(value, ".6f") if isinstance(value, float) else value)
                    if column in ("balance", "book_weight", "observed_weight") and Decimal(exact) < 0:
                        raise ValueError("negative weight")
                except (ValueError, ArithmeticError, TypeError) as exc:
                    raise RuntimeError(f"Cannot migrate {table}.{column} row {row['id']}: investigate the original weight before retrying") from exc
                values[column] = exact
            snapshots[table].append(values)
    for table, columns in TABLES.items():
        for column in columns:
            op.add_column(table, sa.Column(column + "__exact", sa.Text(), nullable=True))
        for row in snapshots[table]:
            assignments = ", ".join(f"{column}__exact = :{column}" for column in columns)
            connection.execute(sa.text(f"UPDATE {table} SET {assignments} WHERE id = :id"), row)
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.drop_column(column)
                batch.alter_column(column + "__exact", new_column_name=column, existing_type=sa.Text(), nullable=False)
            name, condition = CHECKS[table]
            batch.create_check_constraint(name, condition)


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        raise RuntimeError("Downgrading exact SQLite weights would lose decimal precision; restore a reviewed backup instead")
