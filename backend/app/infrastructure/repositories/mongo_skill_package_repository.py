"""MongoDB implementation of SkillPackageRepository."""

import logging
from typing import Any

from app.core.config import get_settings
from app.infrastructure.storage.mongodb import get_mongodb

logger = logging.getLogger(__name__)


class MongoSkillPackageRepository:
    """Inserts skill package documents into the ``skill_packages`` collection."""

    async def save_package(self, package_doc: dict[str, Any]) -> None:
        """Insert *package_doc* into the ``skill_packages`` MongoDB collection.

        Raises:
            Exception: Re-raises any storage error after logging so the caller
                can decide whether to surface or swallow it.
        """
        try:
            settings = get_settings()
            mongodb = get_mongodb()
            db = mongodb.client[settings.mongodb_database]
            collection = db.get_collection("skill_packages")
            await collection.insert_one(package_doc)
            logger.info("Saved skill package %s to database", package_doc.get("id"))
        except Exception as exc:
            logger.error(
                "Failed to save skill package %s: %s",
                package_doc.get("id"),
                exc,
            )
            raise
