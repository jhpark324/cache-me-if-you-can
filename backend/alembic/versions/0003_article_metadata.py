"""Keep an article's summary and numbered citations in its immutable revision."""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE capture_revisions ADD COLUMN article JSON")


def downgrade():
    raise RuntimeError("Article summaries and citations are retained; downgrade requires an explicit data migration.")
