"""drop_old_columns

Revision ID: 50a4fec6594a
Revises: 6297b0d20b50
Create Date: 2026-07-08 15:15:10.604362

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50a4fec6594a'
down_revision: Union[str, Sequence[str], None] = '6297b0d20b50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('feedback', recreate='always') as batch_op:
        batch_op.drop_column('experience')
        batch_op.drop_column('feedback_type')
        batch_op.drop_column('product_id')
        batch_op.drop_column('description')


def downgrade() -> None:
    """Downgrade schema."""
    pass
