import glob
import os
import re
import aiosqlite

try:
    import asyncpg
except ImportError:  # pragma: no cover
    asyncpg = None

try:
    from backend.config import settings
except ImportError:
    from config import settings

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), settings.DB_PATH))
DATABASE_URL = settings.DATABASE_URL
SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "database_files", "schema.sql"))
SCHEMA_PATH_PG = os.path.abspath(os.path.join(os.path.dirname(__file__), "database_files", "schema_postgres.sql"))
MIGRATIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "database_files", "migrations"))


def _is_postgres() -> bool:
    return bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))


def _ensure_database_path() -> None:
    if not _is_postgres():
        directory = os.path.dirname(DB_PATH)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)


def _replace_question_placeholders(sql: str) -> str:
    result = []
    in_single_quote = False
    in_double_quote = False
    escape = False
    param_index = 1

    for ch in sql:
        if escape:
            result.append(ch)
            escape = False
            continue

        if ch == "\\":
            result.append(ch)
            escape = True
            continue

        if in_single_quote:
            result.append(ch)
            if ch == "'":
                in_single_quote = False
            continue

        if in_double_quote:
            result.append(ch)
            if ch == '"':
                in_double_quote = False
            continue

        if ch == "'":
            in_single_quote = True
            result.append(ch)
            continue

        if ch == '"':
            in_double_quote = True
            result.append(ch)
            continue

        if ch == "?":
            result.append(f"${param_index}")
            param_index += 1
        else:
            result.append(ch)

    return "".join(result)


SERIAL_PK_TABLES = {
    "users",
    "questions",
    "question_options",
    "exams",
    "exam_questions",
    "exam_attempts",
    "leaderboard",
    "comments",
    "notifications",
    "badges",
    "pending_approvals",
}


def _extract_insert_table(sql: str) -> str | None:
    match = re.match(r"^\s*INSERT\s+INTO\s+\"?([A-Za-z_][A-Za-z0-9_]*)\"?", sql, flags=re.I)
    return match.group(1).lower() if match else None


def _translate_postgres_sql(sql: str) -> str:
    if not _is_postgres():
        return sql

    original_sql = sql
    sql = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", sql, flags=re.I)
    if re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", original_sql, flags=re.I):
        sql = sql.rstrip().rstrip(";")
        if "ON CONFLICT" not in sql.upper():
            sql += " ON CONFLICT DO NOTHING"

    sql = re.sub(r"datetime\(\s*'now'\s*\)", "CURRENT_TIMESTAMP::text", sql, flags=re.I)
    sql = re.sub(r"AUTOINCREMENT", "", sql, flags=re.I)
    return _replace_question_placeholders(sql)


class PostgresCursor:
    def __init__(self, records, lastrowid=None):
        self._records = list(records)
        self._index = 0
        self.lastrowid = lastrowid

    async def fetchone(self):
        if self._index >= len(self._records):
            return None
        row = self._records[self._index]
        self._index += 1
        return row

    async def fetchall(self):
        return list(self._records)


class PostgresDatabase:
    backend = "postgres"

    def __init__(self, conn):
        self._conn = conn

    async def execute(self, sql: str, params=None):
        params = params or ()
        sql = _translate_postgres_sql(sql)
        if re.match(r"^\s*(SELECT|WITH|VALUES)\b", sql, flags=re.I):
            records = await self._conn.fetch(sql, *params)
            return PostgresCursor(records)

        await self._conn.execute(sql, *params)
        lastrowid = None
        insert_table = _extract_insert_table(sql)
        if insert_table in SERIAL_PK_TABLES:
            try:
                lastrowid = await self._conn.fetchval("SELECT LASTVAL()")
            except Exception:
                lastrowid = None
        return PostgresCursor([], lastrowid=lastrowid)

    async def executemany(self, sql: str, seq_of_params):
        sql = _translate_postgres_sql(sql)
        for params in seq_of_params:
            await self._conn.execute(sql, *params)
        return PostgresCursor([])

    async def executescript(self, script: str):
        statements = [stmt.strip() for stmt in script.split(";") if stmt.strip()]
        for statement in statements:
            await self.execute(statement)

    async def commit(self):
        return None

    async def close(self):
        await self._conn.close()


async def connect_db():
    if _is_postgres():
        if asyncpg is None:
            raise ImportError("asyncpg is required for PostgreSQL support. Install asyncpg in your environment.")
        pg_conn = await asyncpg.connect(DATABASE_URL)
        return PostgresDatabase(pg_conn)

    _ensure_database_path()
    return await aiosqlite.connect(DB_PATH)


async def _execute_schema(db) -> None:
    if _is_postgres():
        cursor = await db.execute(
            "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' LIMIT 1"
        )
    else:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
        )

    row = await cursor.fetchone()
    if row is not None:
        return

    schema_path = SCHEMA_PATH_PG if _is_postgres() else SCHEMA_PATH
    if _is_postgres() and not os.path.exists(schema_path):
        schema_path = SCHEMA_PATH

    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as schema_file:
        schema_sql = schema_file.read()

    await db.executescript(schema_sql)
    if not _is_postgres():
        await db.commit()


async def _ensure_migrations_table(db) -> None:
    if _is_postgres():
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    else:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        await db.commit()


async def _get_applied_migrations(db) -> set[str]:
    cursor = await db.execute("SELECT name FROM _migrations")
    rows = await cursor.fetchall()
    return {row[0] for row in rows}


async def _apply_migration(db, name: str, path: str) -> None:
    with open(path, "r", encoding="utf-8") as migration_file:
        migration_sql = migration_file.read()

    statements = [stmt.strip() for stmt in migration_sql.split(";") if stmt.strip()]
    for statement in statements:
        try:
            await db.execute(statement)
        except Exception as exc:
            message = str(exc).lower()
            if "duplicate column name" in message or "already exists" in message:
                continue
            raise

    await db.execute(
        "INSERT INTO _migrations (name) VALUES (?)",
        (name,),
    )
    if not _is_postgres():
        await db.commit()


async def _run_migrations(db) -> None:
    await _ensure_migrations_table(db)
    applied = await _get_applied_migrations(db)
    migration_files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
    for migration_path in migration_files:
        migration_name = os.path.basename(migration_path)
        if migration_name in applied:
            continue
        await _apply_migration(db, migration_name, migration_path)


async def init_db(app) -> None:
    app.state.db = await connect_db()
    if not _is_postgres():
        await app.state.db.execute("PRAGMA foreign_keys=ON;")
        await app.state.db.execute("PRAGMA journal_mode=WAL;")
        await app.state.db.commit()

    await _execute_schema(app.state.db)
    await _run_migrations(app.state.db)


async def close_db(app) -> None:
    db = getattr(app.state, "db", None)
    if db is not None:
        await db.close()
