"""Tests for OpenAILLM multi-key support (FAILOVER strategy)

Tests automatic key rotation on HTTP 429 (rate limit) and 401 (authentication) errors.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import RateLimitError

from app.domain.exceptions.base import ConfigurationException
from app.infrastructure.external.llm.openai_llm import OpenAILLM


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing without real Redis."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def openai_llm_multikey(mock_redis):
    """Create OpenAILLM instance with 3 keys."""
    return OpenAILLM(
        api_key="primary-key",
        fallback_api_keys=["fallback-key-1", "fallback-key-2"],
        redis_client=mock_redis,
        model_name="gpt-4o-mini",
        temperature=0.7,
        max_tokens=1000,
        api_base="https://api.openai.com/v1",
    )


class TestOpenAILLMMultiKeyInit:
    """Test initialization with multiple API keys."""

    def test_init_with_single_key(self, mock_redis):
        """Single key should work (backward compatibility)."""
        llm = OpenAILLM(
            api_key="test-key",
            redis_client=mock_redis,
        )
        assert llm._max_retries == 1
        assert len(llm._key_pool.keys) == 1

    def test_init_with_multiple_keys(self, openai_llm_multikey):
        """Should initialize with 3 keys (primary + 2 fallbacks)."""
        assert openai_llm_multikey._max_retries == 3
        assert len(openai_llm_multikey._key_pool.keys) == 3
        # Keys should have priorities 0, 1, 2 (FAILOVER strategy)
        priorities = sorted([k.priority for k in openai_llm_multikey._key_pool.keys])
        assert priorities == [0, 1, 2]

    def test_init_requires_api_key(self, mock_redis):
        """Should raise error if no primary key provided."""
        with pytest.raises(ConfigurationException, match="API key is required"):
            OpenAILLM(
                api_key=None,
                redis_client=mock_redis,
            )


class TestOpenAILLMRateLimitRotation:
    """Test automatic key rotation on HTTP 429 rate limits."""

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_rotation(self, openai_llm_multikey, mock_redis):
        """Rate limit (429) should rotate to next key."""
        messages = [{"role": "user", "content": "test"}]

        # Mock _get_client to return different mocked clients for each key
        clients = []
        for _ in range(3):
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock()
            mock_client.chat.completions = AsyncMock()
            clients.append(mock_client)

        # First client: raise RateLimitError
        mock_response = MagicMock()
        mock_response.headers = {"x-ratelimit-reset-requests": str(int(time.time()) + 60)}
        rate_limit_error = RateLimitError("Rate limit exceeded", response=mock_response, body=None)
        clients[0].chat.completions.create = AsyncMock(side_effect=rate_limit_error)

        # Second client: return success
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message = MagicMock()
        mock_completion.choices[0].message.model_dump = MagicMock(
            return_value={"role": "assistant", "content": "success"}
        )
        mock_completion.choices[0].finish_reason = "stop"
        mock_completion.usage = None
        clients[1].chat.completions.create = AsyncMock(return_value=mock_completion)

        call_count = 0

        async def mock_get_client(**kwargs):
            nonlocal call_count
            result = clients[call_count]
            call_count += 1
            return result

        with patch.object(openai_llm_multikey, "_get_client", side_effect=mock_get_client):
            result = await openai_llm_multikey.ask(messages)

        assert result["content"] == "success"
        assert call_count == 2  # Should have rotated to second key

    @pytest.mark.asyncio
    async def test_all_keys_exhausted_rate_limit(self, openai_llm_multikey, mock_redis):
        """Should raise error if all keys hit rate limit."""
        messages = [{"role": "user", "content": "test"}]

        # Mock all clients to raise RateLimitError
        mock_response = MagicMock()
        mock_response.headers = {"x-ratelimit-reset-requests": str(int(time.time()) + 60)}
        rate_limit_error = RateLimitError("Rate limit exceeded", response=mock_response, body=None)

        clients = []
        for _ in range(3):
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock()
            mock_client.chat.completions = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=rate_limit_error)
            clients.append(mock_client)

        call_count = 0

        async def mock_get_client(**kwargs):
            nonlocal call_count
            if call_count < len(clients):
                result = clients[call_count]
                call_count += 1
                return result
            raise RuntimeError("All 3 OpenAI/OpenRouter API keys exhausted")

        with (
            patch.object(openai_llm_multikey, "_get_client", side_effect=mock_get_client),
            pytest.raises(RuntimeError, match="All 3 OpenAI/OpenRouter API keys exhausted"),
        ):
            await openai_llm_multikey.ask(messages)

    @pytest.mark.asyncio
    async def test_parse_rate_limit_ttl_from_header(self, openai_llm_multikey):
        """Should parse x-ratelimit-reset-requests header for TTL."""
        mock_response = MagicMock()
        reset_time = int(time.time()) + 120  # 2 minutes from now
        mock_response.headers = {"x-ratelimit-reset-requests": str(reset_time)}

        error = RateLimitError("Rate limit", response=mock_response, body=None)
        ttl = openai_llm_multikey._parse_openai_rate_limit(error)

        # Should be close to 120 seconds (allow 2s tolerance for test execution time)
        assert 118 <= ttl <= 122

    @pytest.mark.asyncio
    async def test_parse_rate_limit_ttl_fallback(self, openai_llm_multikey):
        """Should use default TTL if header missing."""
        mock_response = MagicMock()
        mock_response.headers = {}

        error = RateLimitError("Rate limit", response=mock_response, body=None)
        ttl = openai_llm_multikey._parse_openai_rate_limit(error)

        assert ttl == 60  # Default 1 minute


class TestOpenAILLMAuthenticationRotation:
    """Test automatic key rotation on HTTP 401 authentication errors."""

    @pytest.mark.asyncio
    async def test_auth_error_triggers_rotation(self, openai_llm_multikey, mock_redis):
        """Authentication error (401) should rotate to next key."""
        messages = [{"role": "user", "content": "test"}]

        # Mock clients
        clients = []
        for _ in range(3):
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock()
            mock_client.chat.completions = AsyncMock()
            clients.append(mock_client)

        # First client: raise AuthenticationError (simulated)
        auth_error = Exception("401 Unauthorized: Invalid API key")
        clients[0].chat.completions.create = AsyncMock(side_effect=auth_error)

        # Second client: return success
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message = MagicMock()
        mock_completion.choices[0].message.model_dump = MagicMock(
            return_value={"role": "assistant", "content": "success"}
        )
        mock_completion.choices[0].finish_reason = "stop"
        mock_completion.usage = None
        clients[1].chat.completions.create = AsyncMock(return_value=mock_completion)

        call_count = 0

        async def mock_get_client(**kwargs):
            nonlocal call_count
            result = clients[call_count]
            call_count += 1
            return result

        with patch.object(openai_llm_multikey, "_get_client", side_effect=mock_get_client):
            result = await openai_llm_multikey.ask(messages)

        assert result["content"] == "success"
        assert call_count == 2  # Should have rotated to second key

    @pytest.mark.asyncio
    async def test_all_keys_invalid_auth(self, openai_llm_multikey, mock_redis):
        """Should raise error if all keys are invalid."""
        messages = [{"role": "user", "content": "test"}]

        auth_error = Exception("401 Unauthorized: Invalid API key")

        clients = []
        for _ in range(3):
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock()
            mock_client.chat.completions = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=auth_error)
            clients.append(mock_client)

        call_count = 0

        async def mock_get_client(**kwargs):
            nonlocal call_count
            if call_count < len(clients):
                result = clients[call_count]
                call_count += 1
                return result
            raise RuntimeError("All 3 OpenAI/OpenRouter API keys exhausted")

        with (
            patch.object(openai_llm_multikey, "_get_client", side_effect=mock_get_client),
            pytest.raises(RuntimeError, match="All 3 OpenAI/OpenRouter API keys exhausted"),
        ):
            await openai_llm_multikey.ask(messages)


class TestOpenAILLMFallbackProviderIsolation:
    """Fallback-provider calls must not poison the primary key pool."""

    @pytest.mark.asyncio
    async def test_fallback_auth_error_does_not_exhaust_primary_pool_key(self, mock_redis):
        messages = [{"role": "user", "content": "test"}]
        primary_timeout = TimeoutError()
        fallback_auth_error = Exception("401 Unauthorized: Invalid fallback API key")

        primary_client = AsyncMock()
        primary_client.chat = AsyncMock()
        primary_client.chat.completions = AsyncMock()
        primary_client.chat.completions.create = AsyncMock(side_effect=primary_timeout)

        fallback_client = AsyncMock()
        fallback_client.chat = AsyncMock()
        fallback_client.chat.completions = AsyncMock()
        fallback_client.chat.completions.create = AsyncMock(side_effect=fallback_auth_error)

        constructed_clients: list[tuple[str, str]] = []

        def _client_factory(*, api_key, base_url, **kwargs):
            constructed_clients.append((api_key, base_url))
            if api_key == "fallback-key":
                return fallback_client
            return primary_client

        llm = OpenAILLM(
            api_key="primary-key",
            redis_client=mock_redis,
            model_name="gpt-4o-mini",
            temperature=0.7,
            max_tokens=1000,
            api_base="https://primary.example/v1",
            fallback_provider={
                "api_base": "https://fallback.example/v1",
                "model_name": "MiniMax-M2.7",
                "api_key": "fallback-key",
            },
        )
        llm.get_api_key = AsyncMock(return_value="primary-key")
        llm._key_pool.mark_exhausted = AsyncMock()

        with (
            patch("app.infrastructure.external.llm.openai_llm.AsyncOpenAI", side_effect=_client_factory),
            pytest.raises(
                Exception,
                match=r"LLM request timed out after 300.0s \(model=gpt-4o-mini, tools=no\)",
            ),
        ):
            await llm.ask(messages)

        assert llm.get_api_key.await_count == 1
        llm._key_pool.mark_exhausted.assert_not_called()
        assert constructed_clients == [
            ("primary-key", "https://primary.example/v1"),
            ("fallback-key", "https://fallback.example/v1"),
        ]


class TestOpenAILLMStreamRotation:
    """Test automatic key rotation in streaming mode."""

    @pytest.mark.asyncio
    async def test_stream_rate_limit_rotation(self, openai_llm_multikey, mock_redis):
        """Stream rate limit should rotate to next key."""
        messages = [{"role": "user", "content": "test"}]

        # Mock clients
        clients = []
        for _ in range(3):
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock()
            mock_client.chat.completions = AsyncMock()
            clients.append(mock_client)

        # First client: raise RateLimitError
        mock_response = MagicMock()
        mock_response.headers = {"x-ratelimit-reset-requests": str(int(time.time()) + 60)}
        rate_limit_error = RateLimitError("Rate limit exceeded", response=mock_response, body=None)
        clients[0].chat.completions.create = AsyncMock(side_effect=rate_limit_error)

        # Second client: return successful stream
        async def mock_stream():
            chunks = [
                MagicMock(choices=[MagicMock(delta=MagicMock(content="hello"), finish_reason=None)], usage=None),
                MagicMock(choices=[MagicMock(delta=MagicMock(content=" world"), finish_reason="stop")], usage=None),
            ]
            for chunk in chunks:
                yield chunk

        clients[1].chat.completions.create = AsyncMock(return_value=mock_stream())

        call_count = 0

        async def mock_get_client(**kwargs):
            nonlocal call_count
            result = clients[call_count]
            call_count += 1
            return result

        with patch.object(openai_llm_multikey, "_get_client", side_effect=mock_get_client):
            result_parts = [chunk async for chunk in openai_llm_multikey.ask_stream(messages)]

        assert "".join(result_parts) == "hello world"
        assert call_count == 2  # Should have rotated to second key

    @pytest.mark.asyncio
    async def test_stream_auth_error_rotation(self, openai_llm_multikey, mock_redis):
        """Stream auth error should rotate to next key."""
        messages = [{"role": "user", "content": "test"}]

        clients = []
        for _ in range(3):
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock()
            mock_client.chat.completions = AsyncMock()
            clients.append(mock_client)

        # First client: raise auth error
        auth_error = Exception("401 Unauthorized: Invalid API key")
        clients[0].chat.completions.create = AsyncMock(side_effect=auth_error)

        # Second client: return successful stream
        async def mock_stream():
            chunks = [
                MagicMock(choices=[MagicMock(delta=MagicMock(content="success"), finish_reason="stop")], usage=None),
            ]
            for chunk in chunks:
                yield chunk

        clients[1].chat.completions.create = AsyncMock(return_value=mock_stream())

        call_count = 0

        async def mock_get_client(**kwargs):
            nonlocal call_count
            result = clients[call_count]
            call_count += 1
            return result

        with patch.object(openai_llm_multikey, "_get_client", side_effect=mock_get_client):
            result_parts = [chunk async for chunk in openai_llm_multikey.ask_stream(messages)]

        assert "".join(result_parts) == "success"
        assert call_count == 2


class TestOpenAILLMRedisGracefulDegradation:
    """Test graceful degradation when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_works_without_redis(self):
        """Should work with in-memory state if Redis unavailable."""
        llm = OpenAILLM(
            api_key="test-key",
            fallback_api_keys=["fallback-1"],
            redis_client=None,  # No Redis
            model_name="gpt-4o-mini",
        )
        assert llm._max_retries == 2
        assert len(llm._key_pool.keys) == 2

        # Should be able to get active key
        key = await llm.get_api_key()
        assert key == "test-key"
