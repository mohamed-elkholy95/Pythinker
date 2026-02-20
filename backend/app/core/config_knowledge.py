"""Knowledge base settings mixin.

Configures RAG-Anything multimodal document processing integration.
Feature-flagged off by default until the dependency is stable.
"""


class KnowledgeBaseSettingsMixin:
    """Settings for knowledge base (RAG-Anything) integration."""

    knowledge_base_enabled: bool = False
    knowledge_base_storage_dir: str = "data/knowledge_bases"
    knowledge_base_parser: str = "mineru"  # "mineru" or "docling"
    knowledge_base_parse_method: str = "txt"  # "txt" (plain text, no MinerU), "auto", "ocr"
    knowledge_base_parse_device: str = "cpu"  # "cpu", "cuda", "mps"
    knowledge_base_enable_image_processing: bool = True
    knowledge_base_enable_table_processing: bool = True
    knowledge_base_enable_equation_processing: bool = True
    knowledge_base_max_file_size_mb: int = 100
    knowledge_base_query_mode: str = (
        "naive"  # "naive" (reliable), "hybrid"/"local"/"global" (requires GPT-4-class LLM for entity extraction)
    )
    knowledge_base_vlm_enhanced: bool = False  # Requires vision-capable model
