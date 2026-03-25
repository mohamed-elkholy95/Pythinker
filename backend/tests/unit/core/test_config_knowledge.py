"""Tests for knowledge base settings mixin."""

import pytest

from app.core.config_knowledge import KnowledgeBaseSettingsMixin


@pytest.mark.unit
class TestKnowledgeBaseSettingsMixin:
    """Tests for KnowledgeBaseSettingsMixin defaults."""

    def test_defaults(self) -> None:
        mixin = KnowledgeBaseSettingsMixin()
        assert mixin.knowledge_base_enabled is False
        assert mixin.knowledge_base_storage_dir == "data/knowledge_bases"
        assert mixin.knowledge_base_parser == "mineru"
        assert mixin.knowledge_base_parse_method == "txt"
        assert mixin.knowledge_base_parse_device == "cpu"
        assert mixin.knowledge_base_enable_image_processing is True
        assert mixin.knowledge_base_enable_table_processing is True
        assert mixin.knowledge_base_enable_equation_processing is True
        assert mixin.knowledge_base_max_file_size_mb == 100
        assert mixin.knowledge_base_query_mode == "naive"
        assert mixin.knowledge_base_vlm_enhanced is False

    def test_can_override_enabled(self) -> None:
        mixin = KnowledgeBaseSettingsMixin()
        mixin.knowledge_base_enabled = True
        assert mixin.knowledge_base_enabled is True

    def test_can_override_parser(self) -> None:
        mixin = KnowledgeBaseSettingsMixin()
        mixin.knowledge_base_parser = "docling"
        assert mixin.knowledge_base_parser == "docling"

    def test_can_override_parse_device(self) -> None:
        mixin = KnowledgeBaseSettingsMixin()
        mixin.knowledge_base_parse_device = "cuda"
        assert mixin.knowledge_base_parse_device == "cuda"
