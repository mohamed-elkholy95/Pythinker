import logging

from bson import ObjectId
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure

from app.domain.exceptions.base import DuplicateResourceException, IntegrationException, UserNotFoundException
from app.domain.models.user import User
from app.domain.repositories.user_repository import UserRepository
from app.infrastructure.models.documents import UserDocument

logger = logging.getLogger(__name__)


class MongoUserRepository(UserRepository):
    """MongoDB implementation of UserRepository"""

    async def create_user(self, user: User) -> User:
        """Create a new user"""
        logger.info(f"Creating user: {user.fullname}")
        try:
            user_doc = UserDocument.from_domain(user)
            await user_doc.create()
        except DuplicateKeyError as e:
            logger.warning("Duplicate user: %s — %s", user.fullname, e)
            raise DuplicateResourceException(f"User already exists: {user.fullname}") from e
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error creating user %s: %s", user.fullname, e)
            raise IntegrationException(f"Failed to create user: {e}", service="mongodb") from e

        result = user_doc.to_domain()
        logger.info(f"User created successfully: {result.id}")
        return result

    async def get_user_by_id(self, user_id: str) -> User | None:
        """Get user by ID"""
        logger.debug(f"Getting user by ID: {user_id}")
        try:
            user_doc = await UserDocument.find_one(UserDocument.user_id == user_id)
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error getting user %s: %s", user_id, e)
            return None

        if not user_doc:
            logger.debug(f"User not found: {user_id}")
            return None
        return user_doc.to_domain()

    async def get_user_by_fullname(self, fullname: str) -> User | None:
        """Get user by fullname"""
        logger.debug(f"Getting user by fullname: {fullname}")
        try:
            user_doc = await UserDocument.find_one(UserDocument.fullname == fullname)
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error getting user by fullname %s: %s", fullname, e)
            return None

        if not user_doc:
            logger.debug(f"User not found: {fullname}")
            return None
        return user_doc.to_domain()

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email"""
        logger.debug(f"Getting user by email: {email}")
        try:
            user_doc = await UserDocument.find_one(UserDocument.email == email.lower())
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error getting user by email %s: %s", email, e)
            return None

        if not user_doc:
            logger.debug(f"User not found: {email}")
            return None
        return user_doc.to_domain()

    async def update_user(self, user: User) -> User:
        """Update user information"""
        logger.info(f"Updating user: {user.id}")
        try:
            user_doc = await UserDocument.find_one(UserDocument.user_id == user.id)
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error finding user %s for update: %s", user.id, e)
            raise IntegrationException(f"Failed to find user for update: {e}", service="mongodb") from e

        if not user_doc:
            raise UserNotFoundException(user.id)

        user_doc.update_from_domain(user)
        try:
            await user_doc.save()
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error saving user %s: %s", user.id, e)
            raise IntegrationException(f"Failed to update user: {e}", service="mongodb") from e

        result = user_doc.to_domain()
        logger.info(f"User updated successfully: {result.id}")
        return result

    async def delete_user(self, user_id: str) -> bool:
        """Delete user by ID"""
        logger.info(f"Deleting user: {user_id}")
        try:
            user_doc = await UserDocument.find_one(UserDocument.user_id == user_id)
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error finding user %s for deletion: %s", user_id, e)
            return False

        if not user_doc:
            logger.warning(f"User not found for deletion: {user_id}")
            return False

        try:
            await user_doc.delete()
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error deleting user %s: %s", user_id, e)
            return False

        logger.info(f"User deleted successfully: {user_id}")
        return True

    async def list_users(self, limit: int = 100, offset: int = 0, cursor: str | None = None) -> list[User]:
        """List users with cursor-based or offset-based pagination.

        When ``cursor`` is provided it takes precedence over ``offset``.
        The cursor value is the string representation of a MongoDB ``_id``.
        """
        logger.debug(f"Listing users: limit={limit}, offset={offset}, cursor={cursor}")
        try:
            if cursor is not None:
                query = UserDocument.find({"_id": {"$gt": ObjectId(cursor)}})
                query = query.sort("+_id").limit(limit)
            else:
                query = UserDocument.find().sort("+_id").skip(offset).limit(limit)

            user_docs = await query.to_list()
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error listing users: %s", e)
            return []

        users = [doc.to_domain() for doc in user_docs]
        logger.debug(f"Found {len(users)} users")
        return users

    async def fullname_exists(self, fullname: str) -> bool:
        """Check if fullname exists"""
        logger.debug(f"Checking if fullname exists: {fullname}")
        try:
            user_doc = await UserDocument.find_one(UserDocument.fullname == fullname)
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error checking fullname %s: %s", fullname, e)
            return False

        exists = user_doc is not None
        logger.debug(f"Fullname exists: {exists}")
        return exists

    async def email_exists(self, email: str) -> bool:
        """Check if email exists"""
        logger.debug(f"Checking if email exists: {email}")
        try:
            user_doc = await UserDocument.find_one(UserDocument.email == email.lower())
        except (ConnectionFailure, OperationFailure) as e:
            logger.error("MongoDB error checking email %s: %s", email, e)
            return False

        exists = user_doc is not None
        logger.debug(f"Email exists: {exists}")
        return exists
