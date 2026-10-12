"""Dialect helpers for the intelligence store.

The store targets MySQL in production, but upserts are built per dialect so
the same store runs on SQLite in unit tests (and on Postgres if
``INTELLIGENCE_STORE_TYPE`` grows one) without forking the query code.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, inspect, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

if TYPE_CHECKING:
    from collections.abc import Callable
    from logging import Logger

    from sqlalchemy import Connection, MetaData, Table
    from sqlalchemy.sql import ColumnElement
    from sqlalchemy.sql.dml import Insert


def upsert(
    dialect: str,
    table: "Table",
    values: dict[str, Any] | list[dict[str, Any]],
    *,
    conflict_cols: list[str],
    update: Callable[[Any], dict[str, Any]],
) -> "Insert":
    """INSERT … ON DUPLICATE KEY / ON CONFLICT DO UPDATE.

    ``update`` receives the "incoming row" accessor (``inserted`` on MySQL,
    ``excluded`` elsewhere) and returns the SET clause. ``conflict_cols`` must
    name a unique constraint; MySQL ignores it and uses whichever key fired.
    """
    if dialect == "mysql":
        stmt = mysql_insert(table).values(values)
        return stmt.on_duplicate_key_update(**update(stmt.inserted))
    builder = sqlite_insert if dialect == "sqlite" else pg_insert
    stmt = builder(table).values(values)
    return stmt.on_conflict_do_update(index_elements=conflict_cols, set_=update(stmt.excluded))


def utcnow() -> datetime:
    """Naive UTC: every DateTime column in this store holds UTC without tzinfo."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def greatest(dialect: str, a: "ColumnElement", b: "ColumnElement") -> "ColumnElement":
    return func.max(a, b) if dialect == "sqlite" else func.greatest(a, b)


def ensure_schema(sync_conn: "Connection", metadata: "MetaData", logger: Logger) -> list[str]:
    """Create missing tables, then add missing nullable columns and indexes.

    ``create_all`` never alters an existing table, so without this every new
    column would need a hand-run migration on each deployment. Only additive,
    nullable changes are applied; anything destructive must be an explicit
    migration. Safe to run concurrently from several processes: a lost race
    surfaces as "duplicate column/key" and is ignored.
    """
    metadata.create_all(sync_conn)
    applied: list[str] = []
    inspector = inspect(sync_conn)
    preparer = sync_conn.dialect.identifier_preparer
    for table in metadata.sorted_tables:
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_cols:
                continue
            if not column.nullable:
                logger.warning(
                    "Intelligence schema: %s.%s is NOT NULL and missing; add it with a migration",
                    table.name, column.name,
                )
                continue
            ddl = (
                f"ALTER TABLE {preparer.format_table(table)} ADD COLUMN "
                f"{preparer.format_column(column)} {column.type.compile(dialect=sync_conn.dialect)}"
            )
            if _execute_ignoring_duplicates(sync_conn, ddl):
                applied.append(f"{table.name}.{column.name}")
        existing_indexes = {i["name"] for i in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name in existing_indexes:
                continue
            try:
                index.create(sync_conn)
                applied.append(f"index {index.name}")
            except Exception as exc:  # concurrent starters race on DDL
                logger.debug("Intelligence schema: index %s not created: %s", index.name, exc)
    if applied:
        logger.info("Intelligence schema migrated: %s", ", ".join(applied))
    return applied


def _execute_ignoring_duplicates(sync_conn: "Connection", ddl: str) -> bool:
    try:
        sync_conn.execute(text(ddl))
        return True
    except Exception as exc:  # concurrent starters race on DDL
        if "duplicate" in str(exc).lower():
            return False
        raise
