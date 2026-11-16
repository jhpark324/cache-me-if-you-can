"""Database lifecycle and serialized short write transactions."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import runpy
import sqlite3
from uuid import uuid4

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base, EmbeddingProfile, IndexBuild, LocalBrain


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid4())


def migrate_database(path: str | Path) -> None:
    """Upgrade a file DB; adopt an unversioned DB only if baseline DDL matches.

    Older development databases are never stamped merely because a table exists.
    A mismatched schema stops startup and leaves its data intact for an explicit
    migration. The lock serializes upgrades across processes.
    """
    from alembic import command
    from alembic.config import Config
    from filelock import FileLock

    path = Path(path).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    source_migrations = Path(__file__).resolve().parents[2] / "alembic"
    migrations = source_migrations if source_migrations.is_dir() else Path(__file__).resolve().parent / "migrations"
    if not (migrations / "env.py").is_file():
        raise RuntimeError("Packaged database migrations are missing.")

    def schema(connection):
        rows = connection.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY type, name")
        return {(kind, name): re.sub(r"\s+", " ", statement.strip()) for kind, name, statement in rows}

    with FileLock(str(path) + ".migration.lock", timeout=30):
        config = Config()
        config.set_main_option("script_location", str(migrations).replace("%", "%%"))
        config.set_main_option("sqlalchemy.url", ("sqlite+pysqlite:///" + str(path)).replace("%", "%%"))
        with sqlite3.connect(path) as actual:
            versioned = actual.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone()
            actual_schema = schema(actual)
            if actual_schema and not versioned:
                baseline = runpy.run_path(str(migrations / "versions" / "0001_canonical_records.py"))
                with sqlite3.connect(":memory:") as reference:
                    for statement in baseline["STATEMENTS"]:
                        reference.execute(statement)
                    if actual_schema != schema(reference):
                        raise RuntimeError("Unversioned database schema differs from migration 0001; explicit migration is required. Existing data was retained.")
                if actual.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise RuntimeError("Existing database has invalid foreign keys; migration was not applied.")
                command.stamp(config, "0001")
        command.upgrade(config, "head")


def install_guards(connection):
    # Canonical history cannot accidentally be updated by a later service method.
    for table in ("capture_revisions", "revision_kinds", "knowledge_nodes", "revision_concepts", "node_concepts", "provenance_links"):
        for action in ("UPDATE", "DELETE"):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable revision data'); END")
    connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS no_capture_restore BEFORE UPDATE OF deleted_at ON captures WHEN OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NOT OLD.deleted_at BEGIN SELECT RAISE(ABORT, 'deleted captures cannot be restored'); END")
    connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS node_span_bounds BEFORE INSERT ON knowledge_nodes WHEN NEW.body_end > (SELECT length(body_markdown) FROM capture_revisions WHERE id = NEW.revision_id) BEGIN SELECT RAISE(ABORT, 'node span exceeds body'); END")


class Database:
    def __init__(self, path: str | Path, *, brain_id: str | None = None, initialize: bool = True):
        path = str(path)
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        options = {"poolclass": StaticPool} if path == ":memory:" else {}
        self.engine = create_engine("sqlite+pysqlite://" if path == ":memory:" else "sqlite+pysqlite:///" + path, connect_args={"check_same_thread": False, "timeout": 15}, **options)

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=15000")
            if path != ":memory:":
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        if initialize:
            Base.metadata.create_all(self.engine)
            with self.engine.begin() as connection:
                install_guards(connection)
        with self.write() as session:
            brain = session.get(LocalBrain, brain_id) if brain_id else session.scalar(select(LocalBrain).order_by(LocalBrain.created_at).limit(1))
            if brain is None:
                now = utcnow()
                brain = LocalBrain(id=brain_id or new_id(), created_at=now)
                session.add(brain)
                session.flush()
                profile = EmbeddingProfile(id=new_id(), brain_id=brain.id, model_id="nlpai-lab/KURE-v2", model_revision="unconfigured", configuration={"representation": "multi_vector", "token_dimension": 128, "dtype": "float32", "metric": "cosine", "scoring": "maxsim", "query_tokens": 64, "document_tokens": 512, "chunk_rules_version": "markdown-v1"}, created_at=now)
                session.add(profile)
                session.flush()
                build_id = new_id()
                build = IndexBuild(id=build_id, brain_id=brain.id, profile_id=profile.id, table_name="knowledge_" + build_id.replace("-", ""), status="building", created_at=now)
                session.add(build)
                session.flush()
                brain.active_index_build_id = build.id
            self.brain_id = brain.id

    @contextmanager
    def read(self):
        with self.session_factory() as session:
            yield session

    @contextmanager
    def write(self):
        with self.session_factory() as session:
            try:
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def close(self):
        self.engine.dispose()
