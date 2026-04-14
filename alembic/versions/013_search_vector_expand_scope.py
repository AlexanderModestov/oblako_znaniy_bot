"""Expand search_vector scope: title (A), section+topic (B), description-tail (C).

The description typically starts with boilerplate ("Практическая работа
содержит..."). Real content sits after the marker "Тематические элементы
работы:". We index only that tail to avoid drowning real matches in
template text. When the marker is absent, description contributes nothing
(we prefer precision over recall here).

Revision ID: 013
Revises: 012
Create Date: 2026-04-14
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


TRIGGER_FN = r"""
CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('russian', coalesce(NEW.title, '')), 'A') ||
        setweight(
            to_tsvector('russian',
                coalesce(NEW.section, '') || ' ' || coalesce(NEW.topic, '')
            ), 'B') ||
        setweight(
            to_tsvector('russian',
                coalesce(
                    substring(NEW.description FROM 'Тематические элементы работы:(.*)$'),
                    ''
                )
            ), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

RECOMPUTE_SQL = r"""
UPDATE lessons SET search_vector =
    setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
    setweight(
        to_tsvector('russian',
            coalesce(section, '') || ' ' || coalesce(topic, '')
        ), 'B') ||
    setweight(
        to_tsvector('russian',
            coalesce(
                substring(description FROM 'Тематические элементы работы:(.*)$'),
                ''
            )
        ), 'C');
"""

# Previous state from migration 011: title-only.
DOWNGRADE_FN = r"""
CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('russian', coalesce(NEW.title, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

DOWNGRADE_RECOMPUTE = r"""
UPDATE lessons SET search_vector =
    to_tsvector('russian', coalesce(title, ''));
"""


def upgrade() -> None:
    op.execute(TRIGGER_FN)
    op.execute(RECOMPUTE_SQL)


def downgrade() -> None:
    op.execute(DOWNGRADE_FN)
    op.execute(DOWNGRADE_RECOMPUTE)
