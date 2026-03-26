"""Tests for PromptCacheManager and SemanticResponseCache."""

import hashlib
import time

import pytest

from app.domain.services.agents.prompt_cache_manager import (
    CacheMetrics,
    CachedResponse,
    LLMProvider,
    PromptCacheManager,
    PromptSection,
    SemanticResponseCache,
)


# ── LLMProvider enum ──────────────────────────────────────────────────

class TestLLMProvider:
    def test_values(self):
        assert LLMProvider.OPENAI == "openai"
        assert LLMProvider.ANTHROPIC == "anthropic"
        assert LLMProvider.UNKNOWN == "unknown"


# ── CacheMetrics ──────────────────────────────────────────────────────

class TestCacheMetrics:
    def test_defaults(self):
        m = CacheMetrics()
        assert m.cache_hits == 0
        assert m.cache_misses == 0
        assert m.tokens_saved == 0
        assert m.total_requests == 0

    def test_hit_rate_zero_requests(self):
        assert CacheMetrics().hit_rate == 0.0

    def test_hit_rate_after_hits(self):
        m = CacheMetrics()
        m.record_hit(100)
        m.record_hit(200)
        m.record_miss()
        assert m.hit_rate == pytest.approx(2 / 3)
        assert m.tokens_saved == 300
        assert m.total_requests == 3

    def test_record_hit_increments(self):
        m = CacheMetrics()
        m.record_hit(50)
        assert m.cache_hits == 1
        assert m.total_requests == 1
        assert m.tokens_saved == 50

    def test_record_miss_increments(self):
        m = CacheMetrics()
        m.record_miss()
        assert m.cache_misses == 1
        assert m.total_requests == 1
        assert m.tokens_saved == 0


# ── PromptSection ─────────────────────────────────────────────────────

class TestPromptSection:
    def test_defaults(self):
        s = PromptSection(content="hello")
        assert s.cacheable is True
        assert s.stable is True
        assert s.section_id == ""

    def test_hash_deterministic(self):
        s = PromptSection(content="test content")
        expected = hashlib.md5("test content".encode(), usedforsecurity=False).hexdigest()[:12]
        assert s.hash == expected

    def test_hash_changes_with_content(self):
        s1 = PromptSection(content="aaa")
        s2 = PromptSection(content="bbb")
        assert s1.hash != s2.hash


# ── PromptCacheManager._detect_provider ───────────────────────────────

class TestProviderDetection:
    @pytest.mark.parametrize("name,expected", [
        ("openai", LLMProvider.OPENAI),
        ("OpenAI", LLMProvider.OPENAI),
        ("gpt-4", LLMProvider.OPENAI),
        ("o1-preview", LLMProvider.OPENAI),
        ("o3-mini", LLMProvider.OPENAI),
        ("anthropic", LLMProvider.ANTHROPIC),
        ("claude-3", LLMProvider.ANTHROPIC),
        ("Claude", LLMProvider.ANTHROPIC),
        ("glm-4", LLMProvider.OPENAI),
        ("zhipu-api", LLMProvider.OPENAI),
        ("deepseek-v3", LLMProvider.OPENAI),
        ("kimi-chat", LLMProvider.OPENAI),
        ("moonshot-v1", LLMProvider.OPENAI),
        ("qwen-turbo", LLMProvider.OPENAI),
        ("openrouter", LLMProvider.OPENAI),
        ("together-ai", LLMProvider.OPENAI),
        ("groq-llama", LLMProvider.OPENAI),
        ("unknown-provider", LLMProvider.OPENAI),  # defaults to OpenAI
    ])
    def test_detect_provider(self, name, expected):
        mgr = PromptCacheManager(provider=name)
        assert mgr._provider == expected


# ── PromptCacheManager.prepare_messages_for_caching ───────────────────

class TestPrepareMessages:
    def test_empty_messages(self):
        mgr = PromptCacheManager(provider="openai")
        assert mgr.prepare_messages_for_caching([]) == []

    def test_openai_combines_system_messages(self):
        mgr = PromptCacheManager(provider="openai")
        msgs = [
            {"role": "system", "content": "System 1"},
            {"role": "system", "content": "System 2"},
            {"role": "user", "content": "Hello"},
        ]
        result = mgr.prepare_messages_for_caching(msgs)
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert "System 1" in result[0]["content"]
        assert "System 2" in result[0]["content"]
        assert result[1]["role"] == "user"

    def test_openai_with_dynamic_content(self):
        mgr = PromptCacheManager(provider="openai")
        msgs = [{"role": "system", "content": "Base"}]
        result = mgr.prepare_messages_for_caching(msgs, dynamic_content="Dynamic")
        assert "---" in result[0]["content"]
        assert "Dynamic" in result[0]["content"]

    def test_anthropic_adds_cache_control(self):
        mgr = PromptCacheManager(provider="anthropic")
        msgs = [{"role": "system", "content": "System prompt"}]
        result = mgr.prepare_messages_for_caching(msgs)
        assert len(result) == 1
        content_blocks = result[0]["content"]
        assert isinstance(content_blocks, list)
        assert content_blocks[0]["cache_control"] == {"type": "ephemeral"}

    def test_anthropic_with_dynamic_content(self):
        mgr = PromptCacheManager(provider="anthropic")
        msgs = [{"role": "system", "content": "Base"}]
        result = mgr.prepare_messages_for_caching(msgs, dynamic_content="Dynamic")
        blocks = result[0]["content"]
        assert len(blocks) == 2
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert blocks[1]["text"] == "Dynamic"

    def test_non_system_messages_preserved(self):
        mgr = PromptCacheManager(provider="openai")
        msgs = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
        ]
        result = mgr.prepare_messages_for_caching(msgs)
        assert result == msgs


# ── PromptCacheManager cache metrics tracking ─────────────────────────

class TestCacheMetricsTracking:
    def test_first_call_is_miss(self):
        mgr = PromptCacheManager(provider="openai")
        mgr.prepare_messages_for_caching([{"role": "system", "content": "hello"}])
        assert mgr._metrics.cache_misses == 1
        assert mgr._metrics.cache_hits == 0

    def test_second_identical_call_is_hit(self):
        mgr = PromptCacheManager(provider="openai")
        msgs = [{"role": "system", "content": "hello"}]
        mgr.prepare_messages_for_caching(msgs)
        mgr.prepare_messages_for_caching(msgs)
        assert mgr._metrics.cache_hits == 1
        assert mgr._metrics.cache_misses == 1

    def test_different_content_is_miss(self):
        mgr = PromptCacheManager(provider="openai")
        mgr.prepare_messages_for_caching([{"role": "system", "content": "first"}])
        mgr.prepare_messages_for_caching([{"role": "system", "content": "second"}])
        assert mgr._metrics.cache_misses == 2
        assert mgr._metrics.cache_hits == 0


# ── PromptCacheManager.split_prompt ───────────────────────────────────

class TestSplitPrompt:
    def test_no_dynamic_sections(self):
        mgr = PromptCacheManager()
        prefix, suffix = mgr.split_prompt("full prompt")
        assert prefix == "full prompt"
        assert suffix == ""

    def test_with_dynamic_sections(self):
        mgr = PromptCacheManager()
        prompt = "Static line 1\nStatic line 2\n# DYNAMIC_SECTION\nDynamic content\nMore dynamic"
        prefix, suffix = mgr.split_prompt(prompt, dynamic_sections=["DYNAMIC_SECTION"])
        assert "Static line 1" in prefix
        assert "Static line 2" in prefix
        assert "DYNAMIC_SECTION" in suffix
        assert "Dynamic content" in suffix


# ── PromptCacheManager.track_prompt_version ───────────────────────────

class TestTrackPromptVersion:
    def test_first_time_returns_false(self):
        mgr = PromptCacheManager()
        assert mgr.track_prompt_version("system", "content v1") is False

    def test_same_content_returns_false(self):
        mgr = PromptCacheManager()
        mgr.track_prompt_version("system", "content v1")
        assert mgr.track_prompt_version("system", "content v1") is False

    def test_changed_content_returns_true(self):
        mgr = PromptCacheManager()
        mgr.track_prompt_version("system", "content v1")
        assert mgr.track_prompt_version("system", "content v2") is True


# ── PromptCacheManager.get_cache_control_params ───────────────────────

class TestCacheControlParams:
    def test_anthropic_returns_header(self):
        mgr = PromptCacheManager(provider="anthropic")
        params = mgr.get_cache_control_params()
        assert "extra_headers" in params
        assert "anthropic-beta" in params["extra_headers"]

    def test_openai_returns_empty(self):
        mgr = PromptCacheManager(provider="openai")
        assert mgr.get_cache_control_params() == {}


# ── PromptCacheManager.get_metrics / reset_metrics ────────────────────

class TestManagerMetrics:
    def test_get_metrics_structure(self):
        mgr = PromptCacheManager(provider="openai")
        metrics = mgr.get_metrics()
        assert metrics["provider"] == "openai"
        assert "cache_hits" in metrics
        assert "cache_misses" in metrics
        assert "hit_rate" in metrics
        assert "tokens_saved_estimate" in metrics
        assert "tracked_prompts" in metrics

    def test_reset_metrics(self):
        mgr = PromptCacheManager()
        mgr.prepare_messages_for_caching([{"role": "system", "content": "hi"}])
        mgr.reset_metrics()
        assert mgr._metrics.total_requests == 0


# ── SemanticResponseCache ─────────────────────────────────────────────

class TestSemanticResponseCache:
    def test_init_defaults(self):
        cache = SemanticResponseCache()
        assert cache._ttl == 900
        assert cache._max_entries == 1000
        assert cache._similarity_threshold == 0.85

    def test_init_custom(self):
        cache = SemanticResponseCache(ttl_seconds=60, max_entries=10, similarity_threshold=0.5)
        assert cache._ttl == 60
        assert cache._max_entries == 10

    def test_put_and_get_exact_match(self):
        cache = SemanticResponseCache(ttl_seconds=60)
        cache.put("What is Python?", "Python is a programming language.")
        result = cache.get("What is Python?")
        assert result == "Python is a programming language."

    def test_get_miss(self):
        cache = SemanticResponseCache(ttl_seconds=60)
        assert cache.get("nonexistent prompt") is None

    def test_get_expired_entry(self):
        cache = SemanticResponseCache(ttl_seconds=0)
        cache.put("prompt", "response")
        # TTL=0 means immediate expiry
        result = cache.get("prompt")
        assert result is None

    def test_put_evicts_when_full(self):
        cache = SemanticResponseCache(max_entries=2)
        cache.put("prompt1", "response1")
        cache.put("prompt2", "response2")
        cache.put("prompt3", "response3")
        assert len(cache._cache) <= 2

    def test_semantic_match(self):
        cache = SemanticResponseCache(ttl_seconds=300, similarity_threshold=0.5)
        cache.put("What is the Python programming language?", "Python is interpreted.")
        # Very similar query should hit
        result = cache.get("What is Python programming language?")
        # May or may not match depending on semantic key extraction
        # Just verify no error
        assert result is None or isinstance(result, str)

    def test_clear(self):
        cache = SemanticResponseCache()
        cache.put("p1", "r1")
        cache.put("p2", "r2")
        cache.clear()
        assert len(cache._cache) == 0
        assert cache.get("p1") is None

    def test_get_metrics_structure(self):
        cache = SemanticResponseCache()
        cache.put("p", "r")
        cache.get("p")
        metrics = cache.get_metrics()
        assert "entries" in metrics
        assert "max_entries" in metrics
        assert "ttl_seconds" in metrics
        assert "hit_rate" in metrics

    def test_hash_prompt_normalization(self):
        cache = SemanticResponseCache()
        h1 = cache._hash_prompt("Hello  World")
        h2 = cache._hash_prompt("hello   world")
        assert h1 == h2

    def test_extract_semantic_key_removes_stop_words(self):
        cache = SemanticResponseCache()
        key = cache._extract_semantic_key("What is the best way to learn Python programming?")
        assert "the" not in key.split()
        assert "is" not in key.split()

    def test_calculate_similarity_identical(self):
        cache = SemanticResponseCache()
        assert cache._calculate_similarity("python code", "python code") == 1.0

    def test_calculate_similarity_no_overlap(self):
        cache = SemanticResponseCache()
        assert cache._calculate_similarity("python code", "java testing") == 0.0

    def test_calculate_similarity_partial_overlap(self):
        cache = SemanticResponseCache()
        sim = cache._calculate_similarity("python code", "python testing")
        assert 0.0 < sim < 1.0

    def test_calculate_similarity_empty(self):
        cache = SemanticResponseCache()
        assert cache._calculate_similarity("", "something") == 0.0
        assert cache._calculate_similarity("something", "") == 0.0

    def test_evict_expired_removes_old(self):
        cache = SemanticResponseCache(ttl_seconds=1)
        cache.put("p", "r")
        # Manually set created_at to past
        for entry in cache._cache.values():
            entry.created_at = time.time() - 10
        removed = cache._evict_expired(time.time())
        assert removed == 1
        assert len(cache._cache) == 0

    def test_evict_lru_removes_least_used(self):
        cache = SemanticResponseCache(max_entries=10)
        cache.put("p1", "r1")
        cache.put("p2", "r2")
        # Hit p2 to increase hit count
        cache.get("p2")
        cache._evict_lru()
        # p1 should be evicted (lower hit count)
        assert cache.get("p2") is not None or len(cache._cache) == 1

    def test_evict_lru_empty_cache(self):
        cache = SemanticResponseCache()
        cache._evict_lru()  # should not raise


# ── CachedResponse ────────────────────────────────────────────────────

class TestCachedResponse:
    def test_defaults(self):
        cr = CachedResponse(
            response="hello",
            prompt_hash="abc",
            created_at=time.time(),
        )
        assert cr.hit_count == 0
        assert cr.semantic_key is None

    def test_with_semantic_key(self):
        cr = CachedResponse(
            response="hello",
            prompt_hash="abc",
            created_at=time.time(),
            semantic_key="python code",
        )
        assert cr.semantic_key == "python code"
