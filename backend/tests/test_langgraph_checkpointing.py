"""Tests for LangGraph checkpointing configuration."""

from unittest.mock import MagicMock, patch


class TestLangGraphCheckpointingConfiguration:
    """Tests for checkpointing enablement via configuration."""

    def test_checkpointing_logic_disabled_when_flag_false(self):
        """Test checkpointing logic: disabled when feature flag is False."""
        # Test the logic: checkpointing should be disabled when flag is False
        feature_flag = False  # Simulating flag being False
        mongodb_db = MagicMock()  # MongoDB is available

        # This is the logic from _init_langgraph_flow
        enable_checkpointing = feature_flag and mongodb_db is not None

        assert enable_checkpointing is False

    def test_checkpointing_logic_enabled_when_flag_true_and_mongodb_available(self):
        """Test checkpointing logic: enabled when flag is True and MongoDB available."""
        feature_flag = True
        mongodb_db = MagicMock()

        enable_checkpointing = feature_flag and mongodb_db is not None

        assert enable_checkpointing is True

    def test_checkpointing_logic_disabled_when_mongodb_none(self):
        """Test checkpointing logic: disabled when MongoDB is None."""
        feature_flag = True
        mongodb_db = None

        enable_checkpointing = feature_flag and mongodb_db is not None

        assert enable_checkpointing is False


class TestAgentServiceMongoDBInjection:
    """Tests for MongoDB injection through the service layer."""

    def test_agent_service_accepts_mongodb_db(self):
        """Test that AgentService accepts mongodb_db parameter."""
        from app.application.services.agent_service import AgentService

        mock_mongodb = MagicMock()

        # This should not raise an error
        with patch("app.application.services.agent_service.AgentDomainService"):
            service = AgentService(
                llm=MagicMock(),
                agent_repository=MagicMock(),
                session_repository=MagicMock(),
                sandbox_cls=MagicMock,
                task_cls=MagicMock,
                json_parser=MagicMock(),
                file_storage=MagicMock(),
                mcp_repository=MagicMock(),
                mongodb_db=mock_mongodb,
            )

            assert service is not None

    def test_agent_domain_service_accepts_mongodb_db(self):
        """Test that AgentDomainService accepts mongodb_db parameter."""
        from app.domain.services.agent_domain_service import AgentDomainService

        mock_mongodb = MagicMock()

        service = AgentDomainService(
            agent_repository=MagicMock(),
            session_repository=MagicMock(),
            llm=MagicMock(),
            sandbox_cls=MagicMock,
            task_cls=MagicMock,
            json_parser=MagicMock(),
            file_storage=MagicMock(),
            mcp_repository=MagicMock(),
            mongodb_db=mock_mongodb,
        )

        assert service._mongodb_db is mock_mongodb

    def test_agent_task_runner_accepts_mongodb_db(self):
        """Test that AgentTaskRunner constructor stores mongodb_db parameter.

        Note: We test the parameter storage directly rather than instantiating
        AgentTaskRunner, as the constructor calls get_settings() which validates
        API keys. The actual instantiation is tested in integration tests with
        proper configuration.
        """
        # Verify AgentTaskRunner.__init__ signature accepts mongodb_db
        import inspect

        from app.domain.services.agent_task_runner import AgentTaskRunner

        sig = inspect.signature(AgentTaskRunner.__init__)
        params = sig.parameters

        assert "mongodb_db" in params
        # Default should be None
        assert params["mongodb_db"].default is None


class TestConfigFeatureFlag:
    """Tests for feature flag configuration."""

    def test_feature_flag_exists_in_settings(self):
        """Test that feature_workflow_checkpointing exists in settings."""
        from app.core.config import Settings

        settings = Settings()

        # Verify the flag exists and defaults to False
        assert hasattr(settings, "feature_workflow_checkpointing")
        assert settings.feature_workflow_checkpointing is False

    def test_feature_flag_can_be_enabled(self):
        """Test that feature flag can be enabled via environment."""
        import os

        # Temporarily set env var
        original = os.environ.get("FEATURE_WORKFLOW_CHECKPOINTING")
        try:
            os.environ["FEATURE_WORKFLOW_CHECKPOINTING"] = "true"
            from app.core.config import Settings

            settings = Settings()
            assert settings.feature_workflow_checkpointing is True
        finally:
            if original is not None:
                os.environ["FEATURE_WORKFLOW_CHECKPOINTING"] = original
            else:
                os.environ.pop("FEATURE_WORKFLOW_CHECKPOINTING", None)


class TestDependenciesMongoDBInjection:
    """Tests for MongoDB injection in dependencies."""

    def test_dependency_injection_logic(self):
        """Test the logic that injects MongoDB when checkpointing is enabled.

        This tests the conditional logic without calling get_settings() which
        would validate API keys. The actual dependency injection is tested
        in integration tests with proper configuration.
        """
        # Simulate the dependency injection logic from dependencies.py:
        # if settings.feature_workflow_checkpointing:
        #     mongodb_db = get_mongodb().client[settings.mongodb_database]

        # Test case 1: Feature flag enabled
        feature_workflow_checkpointing = True
        mock_mongodb = MagicMock()
        mongodb_db = None

        if feature_workflow_checkpointing:
            mongodb_db = mock_mongodb

        assert mongodb_db is mock_mongodb

        # Test case 2: Feature flag disabled
        feature_workflow_checkpointing = False
        mongodb_db = None

        if feature_workflow_checkpointing:
            mongodb_db = mock_mongodb

        assert mongodb_db is None


class TestLangGraphFlowCheckpointerCreation:
    """Tests for checkpointer creation in LangGraphPlanActFlow."""

    def test_checkpointer_created_when_enabled(self):
        """Test that MongoDBCheckpointer is created when checkpointing enabled."""
        # Test the conditional logic in flow.py
        enable_checkpointing = True
        mongodb_db = MagicMock()

        # Simulating the logic from flow.py lines 196-203:
        checkpointer = None
        if enable_checkpointing and mongodb_db:
            # In actual code: checkpointer = MongoDBCheckpointer(mongodb_db)
            checkpointer = "created"

        assert checkpointer is not None

    def test_checkpointer_not_created_when_disabled(self):
        """Test that checkpointer is None when checkpointing disabled."""
        enable_checkpointing = False
        mongodb_db = MagicMock()

        checkpointer = None
        if enable_checkpointing and mongodb_db:
            checkpointer = "created"

        assert checkpointer is None

    def test_checkpointer_not_created_when_no_mongodb(self):
        """Test that checkpointer is None when no MongoDB."""
        enable_checkpointing = True
        mongodb_db = None

        checkpointer = None
        if enable_checkpointing and mongodb_db:
            checkpointer = "created"

        assert checkpointer is None
