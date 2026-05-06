#!/usr/bin/env python3
"""
Print all columns in fact and intermediate tables.

Usage:
    python scripts/list_schema.py
    python scripts/list_schema.py --schemas main_marts main_intermediate
    python scripts/list_schema.py --format compact   # one line per table
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.db import get_conn

DEFAULT_SCHEMAS = ["main_marts", "main_intermediate"]


def list_schema(schemas: list[str], fmt: str) -> None:
    con = get_conn()

    placeholders = ", ".join("?" * len(schemas))
    rows = con.execute(
        f"""
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema IN ({placeholders})
        ORDER BY table_schema, table_name, ordinal_position
        """,
        schemas,
    ).fetchall()

    if not rows:
        print("No tables found in schemas:", schemas)
        return

    current_table = None
    col_buf: list[str] = []

    def flush(table: str, cols: list[str]) -> None:
        if fmt == "compact":
            print(f"{table} ({len(cols)}): {', '.join(cols)}")
        else:
            print(f"\n{'─' * 60}")
            print(f"  {table}  ({len(cols)} columns)")
            print(f"{'─' * 60}")
            for c in cols:
                print(f"  {c}")

    for schema, table, col, dtype in rows:
        full = f"{schema}.{table}"
        col_entry = f"{col}: {dtype}" if fmt != "compact" else col
        if full != current_table:
            if current_table:
                flush(current_table, col_buf)
            current_table = full
            col_buf = []
        col_buf.append(col_entry)

    if current_table:
        flush(current_table, col_buf)

    total = len(rows)
    tables = len({f"{r[0]}.{r[1]}" for r in rows})
    print(f"\nTotal: {total} columns across {tables} tables")


def main() -> None:
    parser = argparse.ArgumentParser(description="List columns in fact/intermediate tables")
    parser.add_argument(
        "--schemas", nargs="+", default=DEFAULT_SCHEMAS,
        help="DuckDB schemas to inspect (default: main_marts main_intermediate)",
    )
    parser.add_argument(
        "--format", choices=["full", "compact"], default="full",
        help="full = one column per line with type; compact = one line per table",
    )
    args = parser.parse_args()
    list_schema(args.schemas, args.format)


if __name__ == "__main__":
    main()
