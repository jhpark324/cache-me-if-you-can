"""Give published articles their own identity, immutable revisions and receipts."""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Database-generated UUIDs allow the migration to run as standalone SQL as well.
UUID_SQL = """lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' ||
                    substr(hex(randomblob(2)),2) || '-8' || substr(hex(randomblob(2)),2) ||
                    '-' || hex(randomblob(6)))"""


def restore_promoted_records():
    # 0003 permitted an existing ordinary record to be promoted to an article.
    # Keep its Capture ID and every original raw revision/node ID. Move only the
    # article-era versions to an inaccessible owner to free the ordinary history
    # for future edits; both the article and raw record keep their original URL.
    op.execute("PRAGMA defer_foreign_keys = ON")
    op.execute("""CREATE TEMP TABLE promoted_records (
        capture_id VARCHAR PRIMARY KEY, archive_id VARCHAR NOT NULL UNIQUE, raw_revision_id VARCHAR NOT NULL)""")
    op.execute(f"""
        INSERT INTO promoted_records
        SELECT a.id, {UUID_SQL}, (
            SELECT r.id FROM capture_revisions r WHERE r.capture_id = a.id AND r.article IS NULL
            ORDER BY r.revision_no DESC LIMIT 1
        )
        FROM articles a
        WHERE a.deleted_at IS NULL AND EXISTS (
            SELECT 1 FROM capture_revisions r WHERE r.capture_id = a.id AND r.article IS NULL
        )
    """)
    op.execute("""CREATE TEMP TABLE archived_revisions (
        revision_id VARCHAR PRIMARY KEY, archive_id VARCHAR NOT NULL)""")
    op.execute("""
        INSERT INTO archived_revisions
        SELECT r.id, p.archive_id FROM promoted_records p JOIN article_revisions r ON r.article_id = p.capture_id
    """)
    op.execute("""
        INSERT INTO captures (id, brain_id, current_revision_id, visibility, created_at, updated_at,
                              state_version, index_generation, deleted_at)
        SELECT p.archive_id, c.brain_id, c.current_revision_id, c.visibility, c.created_at, c.updated_at,
               c.state_version, c.index_generation, strftime('%Y-%m-%dT%H:%M:%fZ','now')
        FROM promoted_records p JOIN captures c ON c.id = p.capture_id
    """)
    # Foreign keys from old citations/relations point to (revision, capture,
    # brain). Only the capture component pointing at an archived edition changes.
    # Both original immutability guards are reinstalled in this transaction.
    for table in ("capture_revisions", "provenance_links"):
        op.execute(f"DROP TRIGGER immutable_{table}_update")
    for table, revision_column, owner_column in (
        ("capture_revisions", "id", "capture_id"),
        ("provenance_links", "source_revision_id", "source_capture_id"),
        ("relations", "source_revision_id", "source_capture_id"),
        ("relations", "target_revision_id", "target_capture_id"),
        ("relations", "evidence_revision_id", "evidence_capture_id"),
        ("mutation_receipts", "committed_revision_id", "capture_id"),
        ("deletion_confirmations", "expected_revision_id", "capture_id"),
        ("index_jobs", "revision_id", "capture_id"),
        ("concept_enrichment_jobs", "requested_revision_id", "capture_id"),
    ):
        op.execute(f"""UPDATE {table} SET {owner_column} = ar.archive_id
            FROM archived_revisions ar WHERE {table}.{revision_column} = ar.revision_id""")
    # This is a disposable projection: the outbox below replaces it with the
    # last ordinary revision. A private archival owner has no index membership.
    op.execute("DELETE FROM capture_index_states WHERE revision_id IN (SELECT revision_id FROM archived_revisions)")
    for table in ("capture_revisions", "provenance_links"):
        op.execute(f"""CREATE TRIGGER immutable_{table}_update BEFORE UPDATE ON {table}
            BEGIN SELECT RAISE(ABORT, 'immutable revision data'); END""")
    op.execute("""
        UPDATE captures SET current_revision_id = p.raw_revision_id, updated_at = r.created_at,
            state_version = state_version + 1, index_generation = index_generation + 1
        FROM promoted_records p JOIN capture_revisions r ON r.id = p.raw_revision_id
        WHERE captures.id = p.capture_id
    """)
    op.execute("DROP TABLE archived_revisions")
    op.execute("DROP TABLE promoted_records")


def upgrade():
    # sqlite3's legacy transaction control starts transactions for DML, not DDL.
    # Acquire the write transaction before creating tables so a failed copy can retry.
    op.execute("UPDATE alembic_version SET version_num = version_num WHERE 0")
    op.execute("""
        CREATE TABLE articles (
            id VARCHAR PRIMARY KEY NOT NULL,
            brain_id VARCHAR NOT NULL REFERENCES local_brain(id),
            current_revision_id VARCHAR NOT NULL,
            created_at VARCHAR NOT NULL,
            updated_at VARCHAR NOT NULL,
            deleted_at VARCHAR,
            FOREIGN KEY (current_revision_id, id) REFERENCES article_revisions(id, article_id)
                DEFERRABLE INITIALLY DEFERRED
        )
    """)
    op.execute("CREATE INDEX ix_articles_brain_id ON articles(brain_id)")
    op.execute("""
        CREATE TABLE article_revisions (
            id VARCHAR PRIMARY KEY NOT NULL,
            article_id VARCHAR NOT NULL REFERENCES articles(id),
            revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
            title VARCHAR NOT NULL,
            summary VARCHAR NOT NULL,
            body_markdown TEXT NOT NULL,
            citations JSON NOT NULL,
            topics JSON NOT NULL,
            created_at VARCHAR NOT NULL,
            UNIQUE (id, article_id),
            UNIQUE (article_id, revision_no)
        )
    """)
    op.execute("""
        CREATE TABLE article_receipts (
            principal_scope VARCHAR NOT NULL,
            request_id VARCHAR NOT NULL,
            operation VARCHAR NOT NULL,
            request_fingerprint VARCHAR NOT NULL,
            article_id VARCHAR NOT NULL REFERENCES articles(id),
            committed_revision_id VARCHAR NOT NULL,
            PRIMARY KEY (principal_scope, request_id),
            FOREIGN KEY (committed_revision_id, article_id) REFERENCES article_revisions(id, article_id)
        )
    """)
    op.execute("""
        INSERT INTO articles (id, brain_id, current_revision_id, created_at, updated_at, deleted_at)
        SELECT c.id, c.brain_id, c.current_revision_id, c.created_at, c.updated_at, c.deleted_at
        FROM captures c JOIN capture_revisions r ON r.id = c.current_revision_id
        WHERE r.article IS NOT NULL
    """)
    op.execute("""
        INSERT INTO article_revisions
            (id, article_id, revision_no, title, summary, body_markdown, citations, topics, created_at)
        SELECT r.id, a.id, r.revision_no, r.title, json_extract(r.article, '$.summary'),
               r.body_markdown, json_extract(r.article, '$.citations'),
               (SELECT json_group_array(name) FROM (
                   SELECT t.name FROM revision_concepts rc JOIN concepts t ON t.id = rc.concept_id
                   WHERE rc.revision_id = r.id ORDER BY t.id
               )), r.created_at
        FROM articles a JOIN capture_revisions r ON r.capture_id = a.id
        WHERE r.article IS NOT NULL
    """)
    for action in ("UPDATE", "DELETE"):
        op.execute(f"""CREATE TRIGGER immutable_article_revisions_{action.lower()}
            BEFORE {action} ON article_revisions
            BEGIN SELECT RAISE(ABORT, 'immutable revision data'); END""")

    op.execute("""
        UPDATE concept_enrichment_jobs
        SET status = 'superseded', completed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
            lease_token = NULL, lease_until = NULL
        WHERE capture_id IN (SELECT id FROM articles) AND status IN ('pending','running')
    """)
    op.execute("""
        UPDATE index_jobs SET status = 'superseded', lease_token = NULL, lease_until = NULL
        WHERE capture_id IN (SELECT id FROM articles) AND operation = 'upsert'
          AND status IN ('pending','running')
    """)
    restore_promoted_records()
    # Pure article Captures still own an article-era current revision. Tombstone
    # those only; previously deleted documents keep their original deletion state.
    op.execute("""
        UPDATE captures
        SET deleted_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
            state_version = state_version + 1, index_generation = index_generation + 1
        WHERE deleted_at IS NULL AND EXISTS (
            SELECT 1 FROM articles a WHERE a.id = captures.id AND a.current_revision_id = captures.current_revision_id
        )
    """)
    # Publish a new index generation for ordinary records restored by the split.
    # The normal upsert replaces their stale article chunks. Pure article records
    # get the normal remove outbox. Already deleted records retain their jobs.
    op.execute(f"""
        INSERT INTO index_jobs (id, capture_id, revision_id, profile_id, build_id, index_generation,
                                operation, status, attempt_count, available_at)
        SELECT {UUID_SQL}, c.id, c.current_revision_id, b.profile_id, b.id, c.index_generation,
               CASE WHEN c.deleted_at IS NULL THEN 'upsert' ELSE 'remove' END, 'pending', 0,
               strftime('%Y-%m-%dT%H:%M:%fZ','now')
        FROM articles a JOIN captures c ON c.id = a.id JOIN index_builds b ON b.brain_id = a.brain_id
        WHERE a.deleted_at IS NULL AND b.status IN ('building','active')
    """)
    op.execute("""
        INSERT INTO capture_index_states (capture_id, build_id, revision_id, index_generation, status, updated_at)
        SELECT j.capture_id, j.build_id, j.revision_id, j.index_generation,
               CASE WHEN j.operation = 'upsert' THEN 'pending' ELSE 'excluded' END, j.available_at
        FROM index_jobs j JOIN articles a ON a.id = j.capture_id JOIN captures c ON c.id = a.id
        WHERE a.deleted_at IS NULL AND j.index_generation = c.index_generation
        ON CONFLICT (capture_id, build_id) DO UPDATE SET revision_id = excluded.revision_id,
            index_generation = excluded.index_generation, status = excluded.status,
            error_code = NULL, updated_at = excluded.updated_at
    """)


def downgrade():
    raise RuntimeError("Independent article revisions are retained; restore a pre-upgrade backup to downgrade.")
