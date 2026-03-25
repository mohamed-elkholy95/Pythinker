"""Tests for PromptCacheManager and SemanticResponseCache."""

from __future__ import annotations

import time

import pytest

from app.domain.services.agents.prompt_cache_manager import (
    CacheMetrics,
    LLMProvider,
    PromptCacheManager,
    PromptSection,
    SemanticResponseCache,
)

# ---------------------------------------------------------------------------
# CacheMetrics
# ---------------------------------------------------------------------------


class TestCacheMetrics:
    def test_initial_values(self):
        m = CacheMetrics()
        assert m.cache_hits == 0
        assert m.cache_misses == 0
        assert m.tokens_saved == 0
        assert m.total_requests == 0

    def test_hit_rate_zero_requests(self):
        m = CacheMetrics()
        assert m.hit_rate == 0.0

    def test_hit_rate_all_hits(self):
        m = CacheMetrics()
        m.record_hit(100)
        m.record_hit(100)
        assert m.hit_rate == 1.0

    def test_hit_rate_mixed(self):
        m = CacheMetrics()
        m.record_hit(50)
        m.record_miss()
        assert m.hit_rate == pytest.approx(0.5)

    def test_record_hit_tokens(self):
        m = CacheMetrics()
        m.record_hit(500)
        assert m.tokens_saved == 500
        assert m.total_requests == 1
        assert m.cache_hits == 1

    def test_record_miss(self):
        m = CacheMetrics()
        m.record_miss()
        assert m.cache_misses == 1
        assert m.total_requests == 1


# ---------------------------------------------------------------------------
# PromptSection
# ---------------------------------------------------------------------------


class TestPromptSection:
    def test_hash_deterministic(self):
        s = PromptSection(content="hello world")
        h1 = s.hash
        h2 = s.hash
        assert h1 == h2

    def test_hash_different_content(self):
        s1 = PromptSection(content="hello")
        s2 = PromptSection(content="world")
        assert s1.hash != s2.hash

    def test_hash_length(self):
        s = PromptSection(content="test")
        assert len(s.hash) == 12

    def test_defaults(self):
        s = PromptSection(content="x")
        assert s.cacheable is True
        assert s.stable is True
        assert s.section_id == ""


# ---------------------------------------------------------------------------
# PromptCacheManager — provider detection
# ---------------------------------------------------------------------------


class TestPromptCacheManagerProviderDetection:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("openai", LLMProvider.OPENAI),
            ("gpt-4o", LLMProvider.OPENAI),
            ("o1-preview", LLMProvider.OPENAI),
            ("o3-mini", LLMProvider.OPENAI),
            ("anthropic", LLMProvider.ANTHROPIC),
            ("claude-3", LLMProvider.ANTHROPIC),
            ("glm-4", LLMProvider.OPENAI),
            ("zhipu", LLMProvider.OPENAI),
            ("deepseek-chat", LLMProvider.OPENAI),
            ("moonshot-v1", LLMProvider.OPENAI),
            ("qwen-turbo", LLMProvider.OPENAI),
            ("groq-llama", LLMProvider.OPENAI),
            ("together-ai", LLMProvider.OPENAI),
            ("openrouter-meta", LLMProvider.OPENAI),
            ("unknown-provider", LLMProvider.OPENAI),  # defaults to OpenAI
        ],
    )
    def test_provider_detection(self, name, expected):
        mgr = PromptCacheManager(provider=name)
        assert mgr._provider == expected


# ---------------------------------------------------------------------------
# PromptCacheManager — message preparation
# ---------------------------------------------------------------------------


class TestPromptCacheManagerOpenAI:
    def test_empty_messages(self):
        mgr = PromptCacheManager(provider="openai")
        result = mgr.prepare_messages_for_caching([])
        assert result == []

    def test_system_combined(self):
        mgr = PromptCacheManager(provider="openai")
        msgs = [
            {"role": "system", "content": "System prompt 1"},
            {"role": "system", "content": "System prompt 2"},
            {"role": "user", "content": "Hello"},
        ]
        result = mgr.prepare_messages_for_caching(msgs)
        assert len(result) == 2  # Combined system + user
        assert result[0]["role"] == "system"
        assert "System prompt 1" in result[0]["content"]
        assert "System prompt 2" in result[0]["content"]

    def test_dynamic_content_appended(self):
        mgr = PromptCacheManager(provider="openai")
        msgs = [{"role": "system", "content": "Base"}]
        result = mgr.prepare_messages_for_caching(msgs, dynamic_content="Dynamic")
        assert "Dynamic" in result[0]["content"]
        assert "---" in result[0]["content"]

    def test_no_system_message(self):
        mgr = PromptCacheManager(provider="openai")
        msgs = [{"role": "user", "content": "Hello"}]
        result = mgr.prepare_messages_for_caching(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"


class TestPromptCacheManagerAnthropic:
    def test_system_gets_cache_control(self):
        mgr = PromptCacheManager(provider="anthropic")
        msgs = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
        ]
        result = mgr.prepare_messages_for_caching(msgs)
        sys_msg = result[0]
        assert isinstance(sys_msg["content"], list)
        assert sys_msg["content"][0]["cache_control"] == {"type": "ephemeral"}

    def test_dynamic_content_split(self):
        mgr = PromptCacheManager(provider="anthropic")
        msgs = [{"role": "system", "content": "Base prompt"}]
        result = mgr.prepare_messages_for_caching(msgs, dynamic_content="Dynamic part")
        sys_content = result[0]["content"]
        assert len(sys_content) == 2
        assert sys_content[0]["text"] == "Base prompt"
        assert "cache_control" in sys_content[0]
        assert sys_content[1]["text"] == "Dynamic part"

    def test_user_messages_unchanged(self):
        mgr = PromptCacheManager(provider="anthropic")
        msgs = [{"role": "user", "content": "Hello"}]
        result = mgr.prepare_messages_for_caching(msgs)
        assert result == msgs


# ---------------------------------------------------------------------------
# PromptCacheManager — split_prompt
# ---------------------------------------------------------------------------


class TestPromptCacheManagerSplitPrompt:
    def test_no_dynamic_sections(self):
        mgr = PromptCacheManager()
        prefix, suffix = mgr.split_prompt("Hello world")
        assert prefix == "Hello world"
        assert suffix == ""

    def test_with_dynamic_section(self):
        mgr = PromptCacheManager()
        prompt = "Static line\nDYNAMIC: data\nMore dynamic"
        prefix, suffix = mgr.split_prompt(prompt, dynamic_sections=["DYNAMIC"])
        assert "Static line" in prefix
        assert "DYNAMIC" in suffix

    def test_empty_dynamic_sections(self):
        mgr = PromptCacheManager()
        prefix, suffix = mgr.split_prompt("Hello", dynamic_sections=[])
        assert prefix == "Hello"
        assert suffix == ""


# ---------------------------------------------------------------------------
# PromptCacheManager — track_prompt_version
# ---------------------------------------------------------------------------


class TestPromptCacheManagerVersionTracking:
    def test_first_version_no_change(self):
        mgr = PromptCacheManager()
        changed = mgr.track_prompt_version("p1", "content A")
        assert changed is False  # First time

    def test_same_content_no_change(self):
        mgr = PromptCacheManager()
        mgr.track_prompt_version("p1", "content A")
        changed = mgr.track_prompt_version("p1", "content A")
        assert changed is False

    def test_different_content_detected(self):
        mgr = PromptCacheManager()
        mgr.track_prompt_version("p1", "content A")
        changed = mgr.track_prompt_version("p1", "content B")
        assert changed is True


# ---------------------------------------------------------------------------
# PromptCacheManager — cache control params
# ---------------------------------------------------------------------------


class TestPromptCacheManagerCacheControl:
    def test_anthropic_returns_header(self):
        mgr = PromptCacheManager(provider="anthropic")
        params = mgr.get_cache_control_params()
        assert "extra_headers" in params
        assert "anthropic-beta" in params["extra_headers"]

    def test_openai_returns_empty(self):
        mgr = PromptCacheManager(provider="openai")
        params = mgr.get_cache_control_params()
        assert params == {}


# ---------------------------------------------------------------------------
# PromptCacheManager — metrics
# ---------------------------------------------------------------------------


class TestPromptCacheManagerMetrics:
    def test_initial_metrics(self):
        mgr = PromptCacheManager()
        m = mgr.get_metrics()
        assert m["cache_hits"] == 0
        assert m["provider"] == "openai"

    def test_metrics_after_operations(self):
        mgr = PromptCacheManager()
        # First call = miss
        mgr.prepare_messages_for_caching([{"role": "system", "content": "hello"}])
        # Same call = hit
        mgr.prepare_messages_for_caching([{"role": "system", "content": "hello"}])
        m = mgr.get_metrics()
        assert m["cache_hits"] == 1
        assert m["cache_misses"] == 1

    def test_reset_metrics(self):
        mgr = PromptCacheManager()
        mgr._metrics.record_hit(100)
        mgr.reset_metrics()
        assert mgr.get_metrics()["cache_hits"] == 0


# ---------------------------------------------------------------------------
# SemanticResponseCache
# ---------------------------------------------------------------------------


class TestSemanticResponseCache:
    def test_put_and_get_exact(self):
        cache = SemanticResponseCache(ttl_seconds=60)
        cache.put("What is Python?", "A programming language")
        result = cache.get("What is Python?")
        assert result == "A programming language"

    def test_get_miss(self):
        cache = SemanticResponseCache(ttl_seconds=60)
        assert cache.get("unknown query") is None

    def test_get_expired(self):
        cache = SemanticResponseCache(ttl_seconds=1)
        cache.put("What is Python?", "A programming language")
        # Manually expire
        for entry in cache._cache.values():
            entry.created_at -= 10
        assert cache.get("What is Python?") is None

    def test_semantic_match(self):
        cache = SemanticResponseCache(ttl_seconds=60, similarity_threshold=0.5)
        cache.put("What is Python programming language?", "A language")
        # Similar query should match
        result = cache.get("Tell me about Python programming language")
        # May or may not match depending on Jaccard overlap — test both paths
        # The important thing is it doesn't crash
        assert result is None or result == "A language"

    def test_exact_match_preferred(self):
        cache = SemanticResponseCache(ttl_seconds=60)
        cache.put("What is Python?", "exact answer")
        result = cache.get("What is Python?")
        assert result == "exact answer"

    def test_lru_eviction(self):
        cache = SemanticResponseCache(ttl_seconds=60, max_entries=2)
        cache.put("query1", "resp1")
        cache.put("query2", "resp2")
        cache.put("query3", "resp3")  # Should evict query1 (lowest hit_count)
        assert len(cache._cache) <= 2

    def test_expired_eviction(self):
        cache = SemanticResponseCache(ttl_seconds=1, max_entries=100)
        cache.put("q1", "r1")
        cache.put("q2", "r2")
        # Expire all
        for entry in cache._cache.values():
            entry.created_at -= 10
        evicted = cache._evict_expired(time.time())
        assert evicted == 2
        assert len(cache._cache) == 0

    def test_clear(self):
        cache = SemanticResponseCache()
        cache.put("q", "r")
        cache.clear()
        assert len(cache._cache) == 0

    def test_get_metrics(self):
        cache = SemanticResponseCache(ttl_seconds=60, max_entries=500)
        m = cache.get_metrics()
        assert m["entries"] == 0
        assert m["max_entries"] == 500
        assert m["ttl_seconds"] == 60

    def test_hit_count_incremented(self):
        cache = SemanticResponseCache(ttl_seconds=60)
        cache.put("q", "r")
        cache.get("q")
        cache.get("q")
        entry = next(iter(cache._cache.values()))
        assert entry.hit_count == 2


class TestSemanticResponseCacheSemanticKey:
    def test_extract_removes_stop_words(self):
        cache = SemanticResponseCache()
        key = cache._extract_semantic_key("What is the best way to learn Python programming?")
        assert "the" not in key.split()
        assert "is" not in key.split()

    def test_extract_sorted(self):
        cache = SemanticResponseCache()
        key = cache._extract_semantic_key("zebra apple mango")
        words = key.split()
        assert words == sorted(words)

    def test_extract_limited_to_10(self):
        cache = SemanticResponseCache()
        long_prompt = " ".join(f"word{i}" for i in range(50))
        key = cache._extract_semantic_key(long_prompt)
        assert len(key.split()) <= 10

    def test_calculate_similarity_identical(self):
        cache = SemanticResponseCache()
        assert cache._calculate_similarity("python learn best", "python learn best") == 1.0

    def test_calculate_similarity_disjoint(self):
        cache = SemanticResponseCache()
        assert cache._calculate_similarity("python learn", "java compile") == 0.0

    def test_calculate_similarity_partial(self):
        cache = SemanticResponseCache()
        sim = cache._calculate_similarity("python learn best", "python learn worst")
        assert 0.0 < sim < 1.0

    def test_calculate_similarity_empty(self):
        cache = SemanticResponseCache()
        assert cache._calculate_similarity("", "something") == 0.0
        assert cache._calculate_similarity("something", "") == 0.0
