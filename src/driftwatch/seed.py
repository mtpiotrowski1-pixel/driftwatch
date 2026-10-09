"""Seed the one-time bootstrap administrator from configuration.

Environment credentials are deliberately not a reconciliation source. They
may create the first user in an empty database, but they must never recreate or
re-elevate an account after an operator changes production state.
"""

from __future__ import annotations

import logging

from driftwatch.bootstrap import claim_initial_admin, close_existing_instance_bootstrap
from driftwatch.config import Settings
from driftwatch.db import Database
from driftwatch.models import User
from driftwatch.security.passwords import hash_password
from driftwatch.services import ensure_default_organization

logger = logging.getLogger(__name__)


async def seed_admin(db: Database, settings: Settings) -> None:
    async with db.session() as session:
        await close_existing_instance_bootstrap(session)
        # Persist the guard even when no seed credentials are configured.
        await session.commit()
        if not settings.initial_admin_email or not settings.initial_admin_password:
            return
        email = settings.initial_admin_email.lower()
        if not await claim_initial_admin(session):
            return
        org = await ensure_default_organization(session, settings.default_org_name)
        # The seeded account is the instance operator (superadmin): it manages all
        # organizations, with the default org as its home for creating data.
        session.add(
            User(
                email=email,
                name="Administrator",
                password_hash=hash_password(settings.initial_admin_password),
                organization_id=org.id,
                is_superadmin=True,
                is_admin=True,
            )
        )
        await session.commit()
        logger.info("seeded initial superadmin")
