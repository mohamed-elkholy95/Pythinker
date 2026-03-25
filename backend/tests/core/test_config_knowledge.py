"""Tests for KnowledgeBaseSettingsMixin (config_knowledge.py).

Covers default values, env-var overrides, and type correctness for every
field declared in the mixin.
"""

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Fields that a local .env file might override; force them back to the
# code-level defaults so the tests are hermetic.
_KNOWLEDGE_ENV_DEFAULTS: dict[str, str] = {
    "KNOWLEDGE_BASE_ENABLED": "false",
    "KNOWLEDGE_BASE_STORAGE_DIR": "data/knowledge_bases",
    "KNOWLEDGE_BASE_PARSER": "mineru",
    "KNOWLEDGE_BASE_PARSE_METHOD": "txt",
    "KNOWLEDGE_BASE_PARSE_DEVICE": "cpu",
    "KNOWLEDGE_BASE_ENABLE_IMAGE_PROCESSING": "true",
    "KNOWLEDGE_BASE_ENABLE_TABLE_PROCESSING": "true",
    "KNOWLEDGE_BASE_ENABLE_EQUATION_PROCESSING": "true",
    "KNOWLEDGE_BASE_MAX_FILE_SIZE_MB": "100",
    "KNOWLEDGE_BASE_QUERY_MODE": "naive",
    "KNOWLEDGE_BASE_VLM_ENHANCED": "false",
}


@pytest.fixture()
def settings(monkeypatch):
    """Return a fresh Settings instance with all knowledge fields at their
    code-level defaults, regardless of what is in the local .env file.

    Pydantic-settings precedence: env vars > .env file > field defaults.
    Setting env vars here ensures the .env cannot interfere.
    """
    for var, default in _KNOWLEDGE_ENV_DEFAULTS.items():
        monkeypatch.setenv(var, default)

    from app.core.config import Settings

    return Settings()


# ---------------------------------------------------------------------------
# Default-value tests
# ---------------------------------------------------------------------------


class TestKnowledgeBaseDefaults:
    """Every field in KnowledgeBaseSettingsMixin has a precise default value."""

    def test_enabled_is_false_by_default(self, settings):
        assert settings.knowledge_base_enabled is False

    def test_storage_dir_default(self, settings):
        assert settings.knowledge_base_storage_dir == "data/knowledge_bases"

    def test_parser_default(self, settings):
        assert settings.knowledge_base_parser == "mineru"

    def test_parse_method_default(self, settings):
        assert settings.knowledge_base_parse_method == "txt"

    def test_parse_device_default(self, settings):
        assert settings.knowledge_base_parse_device == "cpu"

    def test_image_processing_enabled_by_default(self, settings):
        assert settings.knowledge_base_enable_image_processing is True

    def test_table_processing_enabled_by_default(self, settings):
        assert settings.knowledge_base_enable_table_processing is True

    def test_equation_processing_enabled_by_default(self, settings):
        assert settings.knowledge_base_enable_equation_processing is True

    def test_max_file_size_mb_default(self, settings):
        assert settings.knowledge_base_max_file_size_mb == 100

    def test_query_mode_default(self, settings):
        assert settings.knowledge_base_query_mode == "naive"

    def test_vlm_enhanced_disabled_by_default(self, settings):
        assert settings.knowledge_base_vlm_enhanced is False


# ---------------------------------------------------------------------------
# Type-correctness tests
# ---------------------------------------------------------------------------


class TestKnowledgeBaseFieldTypes:
    """Field values must carry the correct Python types."""

    def test_enabled_is_bool(self, settings):
        assert isinstance(settings.knowledge_base_enabled, bool)

    def test_storage_dir_is_str(self, settings):
        assert isinstance(settings.knowledge_base_storage_dir, str)

    def test_parser_is_str(self, settings):
        assert isinstance(settings.knowledge_base_parser, str)

    def test_parse_method_is_str(self, settings):
        assert isinstance(settings.knowledge_base_parse_method, str)

    def test_parse_device_is_str(self, settings):
        assert isinstance(settings.knowledge_base_parse_device, str)

    def test_image_processing_is_bool(self, settings):
        assert isinstance(settings.knowledge_base_enable_image_processing, bool)

    def test_table_processing_is_bool(self, settings):
        assert isinstance(settings.knowledge_base_enable_table_processing, bool)

    def test_equation_processing_is_bool(self, settings):
        assert isinstance(settings.knowledge_base_enable_equation_processing, bool)

    def test_max_file_size_mb_is_int(self, settings):
        assert isinstance(settings.knowledge_base_max_file_size_mb, int)

    def test_query_mode_is_str(self, settings):
        assert isinstance(settings.knowledge_base_query_mode, str)

    def test_vlm_enhanced_is_bool(self, settings):
        assert isinstance(settings.knowledge_base_vlm_enhanced, bool)


# ---------------------------------------------------------------------------
# Env-var override tests
# ---------------------------------------------------------------------------


class TestKnowledgeBaseEnvOverrides:
    """Settings can be changed via environment variables."""

    def test_enabled_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ENABLED", "true")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_enabled is True

    def test_storage_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_STORAGE_DIR", "/mnt/kb")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_storage_dir == "/mnt/kb"

    def test_parser_docling_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_PARSER", "docling")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_parser == "docling"

    def test_parse_method_auto_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_PARSE_METHOD", "auto")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_parse_method == "auto"

    def test_parse_method_ocr_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_PARSE_METHOD", "ocr")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_parse_method == "ocr"

    def test_parse_device_cuda_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_PARSE_DEVICE", "cuda")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_parse_device == "cuda"

    def test_parse_device_mps_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_PARSE_DEVICE", "mps")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_parse_device == "mps"

    def test_image_processing_disabled_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ENABLE_IMAGE_PROCESSING", "false")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_enable_image_processing is False

    def test_table_processing_disabled_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ENABLE_TABLE_PROCESSING", "false")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_enable_table_processing is False

    def test_equation_processing_disabled_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_ENABLE_EQUATION_PROCESSING", "false")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_enable_equation_processing is False

    def test_max_file_size_mb_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_MAX_FILE_SIZE_MB", "500")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_max_file_size_mb == 500

    def test_query_mode_hybrid_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_QUERY_MODE", "hybrid")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_query_mode == "hybrid"

    def test_query_mode_local_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_QUERY_MODE", "local")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_query_mode == "local"

    def test_query_mode_global_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_QUERY_MODE", "global")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_query_mode == "global"

    def test_vlm_enhanced_enabled_from_env(self, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_BASE_VLM_ENHANCED", "true")
        from app.core.config import Settings

        s = Settings()
        assert s.knowledge_base_vlm_enhanced is True


# ---------------------------------------------------------------------------
# Mixin isolation test
# ---------------------------------------------------------------------------


class TestKnowledgeBaseSettingsMixinDirect:
    """KnowledgeBaseSettingsMixin can be imported and introspected independently."""

    def test_mixin_importable(self):
        from app.core.config_knowledge import KnowledgeBaseSettingsMixin

        assert KnowledgeBaseSettingsMixin is not None

    def test_mixin_has_all_expected_fields(self):
        from app.core.config_knowledge import KnowledgeBaseSettingsMixin

        expected_fields = {
            "knowledge_base_enabled",
            "knowledge_base_storage_dir",
            "knowledge_base_parser",
            "knowledge_base_parse_method",
            "knowledge_base_parse_device",
            "knowledge_base_enable_image_processing",
            "knowledge_base_enable_table_processing",
            "knowledge_base_enable_equation_processing",
            "knowledge_base_max_file_size_mb",
            "knowledge_base_query_mode",
            "knowledge_base_vlm_enhanced",
        }
        # Inspect class annotations (plain mixin — no Pydantic model_fields)
        annotations = {}
        for klass in KnowledgeBaseSettingsMixin.__mro__:
            annotations.update(getattr(klass, "__annotations__", {}))

        for field in expected_fields:
            assert field in annotations, f"Missing annotation: {field}"

    def test_mixin_default_values_match_class_attributes(self):
        from app.core.config_knowledge import KnowledgeBaseSettingsMixin

        assert KnowledgeBaseSettingsMixin.knowledge_base_enabled is False
        assert KnowledgeBaseSettingsMixin.knowledge_base_storage_dir == "data/knowledge_bases"
        assert KnowledgeBaseSettingsMixin.knowledge_base_parser == "mineru"
        assert KnowledgeBaseSettingsMixin.knowledge_base_parse_method == "txt"
        assert KnowledgeBaseSettingsMixin.knowledge_base_parse_device == "cpu"
        assert KnowledgeBaseSettingsMixin.knowledge_base_enable_image_processing is True
        assert KnowledgeBaseSettingsMixin.knowledge_base_enable_table_processing is True
        assert KnowledgeBaseSettingsMixin.knowledge_base_enable_equation_processing is True
        assert KnowledgeBaseSettingsMixin.knowledge_base_max_file_size_mb == 100
        assert KnowledgeBaseSettingsMixin.knowledge_base_query_mode == "naive"
        assert KnowledgeBaseSettingsMixin.knowledge_base_vlm_enhanced is False

    def test_mixin_field_count(self):
        from app.core.config_knowledge import KnowledgeBaseSettingsMixin

        annotations = {}
        for klass in KnowledgeBaseSettingsMixin.__mro__:
            annotations.update(getattr(klass, "__annotations__", {}))

        kb_fields = [k for k in annotations if k.startswith("knowledge_base_")]
        assert len(kb_fields) == 11


# ---------------------------------------------------------------------------
# Integration test: mixin is composed into Settings
# ---------------------------------------------------------------------------


class TestKnowledgeBaseIntegration:
    """KnowledgeBaseSettingsMixin fields are accessible via the top-level Settings."""

    def test_settings_inherits_mixin(self):
        from app.core.config import Settings
        from app.core.config_knowledge import KnowledgeBaseSettingsMixin

        assert issubclass(Settings, KnowledgeBaseSettingsMixin)

    def test_all_fields_accessible_on_settings(self, settings):
        """Every declared field is reachable on the composed Settings object."""
        fields = [
            "knowledge_base_enabled",
            "knowledge_base_storage_dir",
            "knowledge_base_parser",
            "knowledge_base_parse_method",
            "knowledge_base_parse_device",
            "knowledge_base_enable_image_processing",
            "knowledge_base_enable_table_processing",
            "knowledge_base_enable_equation_processing",
            "knowledge_base_max_file_size_mb",
            "knowledge_base_query_mode",
            "knowledge_base_vlm_enhanced",
        ]
        for field in fields:
            assert hasattr(settings, field), f"Settings missing attribute: {field}"
