"""Durable incremental topic linking; existing topics are not queued."""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# Frozen SQL: do not import runtime ORM definitions into a migration.
STATEMENTS = (
    "CREATE TABLE topic_backfill_jobs (\n\tid VARCHAR NOT NULL, \n\tbrain_id VARCHAR NOT NULL, \n\tconcept_id VARCHAR NOT NULL, \n\tdefinition_hash VARCHAR NOT NULL, \n\tpolicy_version VARCHAR NOT NULL, \n\tstatus VARCHAR NOT NULL, \n\tcandidate_ids JSON NOT NULL, \n\tattempt_count INTEGER NOT NULL, \n\tcall_count INTEGER NOT NULL, \n\tavailable_at VARCHAR NOT NULL, \n\tlease_token VARCHAR, \n\tlease_until VARCHAR, \n\terror_code VARCHAR, \n\tcreated_at VARCHAR NOT NULL, \n\tcompleted_at VARCHAR, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(concept_id, brain_id) REFERENCES concepts (id, brain_id), \n\tUNIQUE (concept_id, definition_hash, policy_version), \n\tCHECK (status IN ('pending','running','completed','partial','failed','superseded')), \n\tCHECK (attempt_count >= 0 AND attempt_count <= 3 AND call_count >= 0 AND call_count <= 4)\n)",
    'CREATE INDEX ix_topic_backfill_jobs_status ON topic_backfill_jobs (status)',
    "CREATE TABLE topic_backfill_decisions (\n\tconcept_id VARCHAR NOT NULL, \n\tdefinition_hash VARCHAR NOT NULL, \n\tcapture_id VARCHAR NOT NULL, \n\tcontent_hash VARCHAR NOT NULL, \n\tpolicy_version VARCHAR NOT NULL, \n\tbrain_id VARCHAR NOT NULL, \n\toutcome VARCHAR NOT NULL, \n\tcreated_at VARCHAR NOT NULL, \n\tPRIMARY KEY (concept_id, definition_hash, capture_id, content_hash, policy_version), \n\tFOREIGN KEY(concept_id, brain_id) REFERENCES concepts (id, brain_id), \n\tFOREIGN KEY(capture_id, brain_id) REFERENCES captures (id, brain_id), \n\tCHECK (outcome IN ('attach','reject'))\n)",
)


def upgrade():
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade():
    raise RuntimeError("Topic decisions are retained; downgrade requires an explicit data migration.")
