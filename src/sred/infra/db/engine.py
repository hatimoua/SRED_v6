"""Re-export the singleton engine from sred.db and register WAL pragmas."""
from sqlalchemy import event
from sred.db import engine          # singleton; created once at sred.db import
import sred.models  # noqa: F401   # registers all 17 ORM table mappers


def _set_wal_mode(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


event.listen(engine, "connect", _set_wal_mode)

__all__ = ["engine"]
