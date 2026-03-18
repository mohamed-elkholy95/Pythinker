from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.session import Session
from app.domain.models.user import User, UserRole


class TestSessionCancelAuthorization:
    @pytest.fixture
    def owner_user(self):
        return User(id="user-owner", fullname="Owner", email="owner@test.com", role=UserRole.USER, is_active=True)

    @pytest.fixture
    def other_user(self):
        return User(id="user-other", fullname="Other", email="other@test.com", role=UserRole.USER, is_active=True)

    @pytest.fixture
    def session(self, owner_user):
        session = MagicMock(spec=Session)
        session.session_id = "session-123"
        session.user_id = owner_user.id
        return session

    @pytest.mark.asyncio
    async def test_owner_can_cancel(self, owner_user, session):
        from app.interfaces.api.session_routes import cancel_session

        agent_service = AsyncMock()
        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = session
        await cancel_session(
            session_id="session-123", current_user=owner_user, agent_service=agent_service, session_repo=session_repo
        )
        agent_service.request_cancellation.assert_called_once_with("session-123")

    @pytest.mark.asyncio
    async def test_non_owner_cannot_cancel(self, other_user, session):
        from fastapi import HTTPException

        from app.interfaces.api.session_routes import cancel_session

        agent_service = AsyncMock()
        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = session
        with pytest.raises(HTTPException) as exc_info:
            await cancel_session(
                session_id="session-123",
                current_user=other_user,
                agent_service=agent_service,
                session_repo=session_repo,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_nonexistent_session_returns_404(self, owner_user):
        from fastapi import HTTPException

        from app.interfaces.api.session_routes import cancel_session

        agent_service = AsyncMock()
        session_repo = AsyncMock()
        session_repo.get_by_id.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await cancel_session(
                session_id="nonexistent",
                current_user=owner_user,
                agent_service=agent_service,
                session_repo=session_repo,
            )
        assert exc_info.value.status_code == 404
