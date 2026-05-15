import os
import threading
import duckdb

def _get_db_path() -> str:
    """Resolve database path: synthetic if requested, else real."""
    if os.getenv("USE_SYNTHETIC_DATA", "").lower() == "true":
        db_name = "healthdata_synthetic.duckdb"
    else:
        db_name = "healthdata.duckdb"

    path = os.path.join(os.path.dirname(__file__), "..", "data", db_name)
    return os.path.abspath(path)


# LangGraph runs parallel tool calls in separate threads. DuckDB connections are
# not thread-safe, so each thread gets its own read-only connection.
_thread_local = threading.local()


def get_conn() -> duckdb.DuckDBPyConnection:
    """Get a thread-local DuckDB connection.

    Resolves database path dynamically so Streamlit can switch datasets
    via environment variables without restarting the app.
    """
    db_path = _get_db_path()

    # Check if cached connection matches current path
    if not hasattr(_thread_local, "conn") or not hasattr(_thread_local, "path"):
        try:
            _thread_local.conn = duckdb.connect(db_path, read_only=True)
            _thread_local.path = db_path
        except Exception as e:
            raise RuntimeError(f"Failed to connect to database at {db_path}: {e}")
    elif _thread_local.path != db_path:
        # Database path changed; close old connection and open new one
        try:
            _thread_local.conn.close()
        except Exception:
            pass
        try:
            _thread_local.conn = duckdb.connect(db_path, read_only=True)
            _thread_local.path = db_path
        except Exception as e:
            raise RuntimeError(f"Failed to connect to database at {db_path}: {e}")

    return _thread_local.conn


def has_personal_data() -> bool:
    """Check if the personal database file exists."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "healthdata.duckdb")
    return os.path.exists(path)
