from alembic import context
from sqlalchemy import engine_from_config, pool

from src.core.database import Base
from src.core.models import (  # noqa: F401
    Region, Municipality, School, Subject, Course, Section, Topic,
    Lesson, LessonLink, User,
)
from src.config import get_settings

config = context.config
target_metadata = Base.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    settings = get_settings()
    context.configure(
        url=settings.sync_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    settings = get_settings()
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.sync_database_url
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
