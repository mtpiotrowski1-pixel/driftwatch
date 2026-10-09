from __future__ import annotations

from sqlalchemy import func, select

from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import User
from driftwatch.seed import seed_admin


def _bootstrap_settings(settings: Settings, *, email: str) -> Settings:
    return settings.model_copy(
        update={
            "initial_admin_email": email,
            "initial_admin_password": "bootstrap-password-123",
        }
    )


async def test_seed_admin_bootstraps_only_an_empty_database(
    database: Database, settings: Settings
) -> None:
    configured = _bootstrap_settings(settings, email="operator@example.com")

    await seed_admin(database, configured)

    async with database.session() as session:
        user = (await session.execute(select(User))).scalar_one()
        assert user.email == "operator@example.com"
        assert user.is_superadmin is True
        assert user.is_admin is True


async def test_seed_admin_does_not_recreate_renamed_operator(
    database: Database, settings: Settings
) -> None:
    configured = _bootstrap_settings(settings, email="operator@example.com")
    await seed_admin(database, configured)
    async with database.session() as session:
        user = (await session.execute(select(User))).scalar_one()
        user.email = "renamed@example.com"
        await session.commit()

    await seed_admin(database, configured)

    async with database.session() as session:
        users = (await session.execute(select(User))).scalars().all()
        assert [user.email for user in users] == ["renamed@example.com"]


async def test_seed_admin_never_elevates_or_adds_to_nonempty_database(
    database: Database, settings: Settings
) -> None:
    async with database.session() as session:
        session.add(
            User(
                email="member@example.com",
                password_hash="not-used",
                is_admin=False,
                is_superadmin=False,
            )
        )
        await session.commit()

    await seed_admin(
        database,
        _bootstrap_settings(settings, email="member@example.com"),
    )

    async with database.session() as session:
        count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        member = (await session.execute(select(User))).scalar_one()
        assert count == 1
        assert member.is_superadmin is False
        assert member.is_admin is False
