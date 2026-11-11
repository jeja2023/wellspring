"""Explicit PostgreSQL privileges for the application role; unknown tables fail closed."""
import re
from sqlalchemy import text

APPEND_ONLY_TABLES = frozenset({
    "audit_events", "intelligence_events",
    "case_relation_events",
    "person_case_candidate_events",
    "wastewater_result_events", "wastewater_samples", "clue_import_batches", "clue_delivery_events", "analysis_asset_events", "person_events", "place_events", "geo_location_events",
})
MUTABLE_TABLES = frozenset({
    "organizations", "users", "cases", "case_information",
    "idempotency_records", "clues", "investigation_tasks", "clue_case_links",
    "person_drafts", "case_relations", "person_case_candidates",
    "case_import_batches", "case_import_rows",

    "wastewater_sites", "wastewater_results",
    "roles", "administration_lock", "ai_services", "ai_runs", "clue_deliveries", "analysis_assets", "person_records", "person_tasks", "person_transfers", "places", "place_inspections", "place_incidents", "geo_locations",
})
RESTRICTED_UPDATE_TABLES = {
    "intake_case_links": ("status", "version", "revoked_by", "revoked_at", "revoke_reason"),
}


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value):
        raise ValueError("Invalid PostgreSQL identifier")
    return '"' + value + '"'


def apply_runtime_permissions(connection, role="wellspring_app", schema="public"):
    """Run as schema owner inside a transaction, after every migration/restore."""
    role_sql, schema_sql = _identifier(role), _identifier(schema)
    connection.execute(text(f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema_sql} FROM {role_sql}"))
    connection.execute(text(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {schema_sql} FROM {role_sql}"))
    connection.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_sql} REVOKE ALL ON TABLES FROM {role_sql}"))
    connection.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_sql} REVOKE ALL ON SEQUENCES FROM {role_sql}"))
    connection.execute(text(f"GRANT USAGE ON SCHEMA {schema_sql} TO {role_sql}"))
    for table in sorted(APPEND_ONLY_TABLES):
        connection.execute(text(f"GRANT SELECT, INSERT ON TABLE {schema_sql}.{_identifier(table)} TO {role_sql}"))
    for table in sorted(MUTABLE_TABLES):
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE ON TABLE {schema_sql}.{_identifier(table)} TO {role_sql}"))
    for table, columns in RESTRICTED_UPDATE_TABLES.items():
        table_sql = f"{schema_sql}.{_identifier(table)}"
        connection.execute(text(f"GRANT SELECT, INSERT ON TABLE {table_sql} TO {role_sql}"))
        column_sql = ', '.join(_identifier(column) for column in columns)
        connection.execute(text(f"GRANT UPDATE ({column_sql}) ON TABLE {table_sql} TO {role_sql}"))
    connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {schema_sql}.\"sessions\" TO {role_sql}"))
    connection.execute(text(f"GRANT SELECT ON TABLE {schema_sql}.\"alembic_version\" TO {role_sql}"))
