"""Give published articles their own identity, immutable revisions and receipts."""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


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

    # Preserve referenced immutable history. All ordinary reads and SourceRefs
    # already enforce the parent Capture's tombstone, including stale search hits.
    op.execute("""
        UPDATE captures
        SET deleted_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
            updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
            state_version = state_version + 1, index_generation = index_generation + 1
        WHERE id IN (SELECT id FROM articles) AND deleted_at IS NULL
    """)
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
    # Mirror the normal deletion outbox. An already deleted Capture retains its
    # existing removal job and generation. A building index is drained as well.
    op.execute("""
        INSERT INTO index_jobs (id, capture_id, revision_id, profile_id, build_id, index_generation,
                                operation, status, attempt_count, available_at)
        SELECT lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' ||
                     substr(hex(randomblob(2)),2) || '-8' || substr(hex(randomblob(2)),2) ||
                     '-' || hex(randomblob(6))),
               c.id, c.current_revision_id, b.profile_id, b.id, c.index_generation,
               'remove', 'pending', 0, c.deleted_at
        FROM articles a JOIN captures c ON c.id = a.id JOIN index_builds b ON b.brain_id = a.brain_id
        WHERE a.deleted_at IS NULL AND b.status IN ('building','active')
    """)
    op.execute("""
        INSERT INTO capture_index_states (capture_id, build_id, revision_id, index_generation, status, updated_at)
        SELECT j.capture_id, j.build_id, j.revision_id, j.index_generation, 'excluded', j.available_at
        FROM index_jobs j JOIN articles a ON a.id = j.capture_id
        WHERE a.deleted_at IS NULL AND j.operation = 'remove'
        ON CONFLICT (capture_id, build_id) DO UPDATE SET revision_id = excluded.revision_id,
            index_generation = excluded.index_generation, status = excluded.status,
            error_code = NULL, updated_at = excluded.updated_at
    """)


def downgrade():
    raise RuntimeError("Independent article revisions are retained; restore a pre-upgrade backup to downgrade.")
