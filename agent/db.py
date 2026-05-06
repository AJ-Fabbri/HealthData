import os
import threading
import duckdb

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "healthdata.duckdb")
_DB_PATH = os.path.abspath(_DB_PATH)

# LangGraph runs parallel tool calls in separate threads. DuckDB connections are
# not thread-safe, so each thread gets its own read-only connection.
_thread_local = threading.local()


def get_conn() -> duckdb.DuckDBPyConnection:
    if not hasattr(_thread_local, "conn"):
        _thread_local.conn = duckdb.connect(_DB_PATH, read_only=True)
    return _thread_local.conn
