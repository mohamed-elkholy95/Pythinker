"""Image generation service using fal.ai FLUX models."""

import logging
from typing import Any

from app.core.config import get_settings
from app.core.retry import http_retry
from app.domain.exceptions.base import ConfigurationException, ImageGenerationException
from app.infrastructure.external.http_pool import HTTPClientPool, ManagedHTTPClient

logger = logging.getLogger(__name__)

FAL_QUEUE_URL = "https://queue.fal.run"
FAL_RESULT_URL = "https://queue.fal.run"


class ImageGenerationService:
    """Service for AI image generation via fal.ai.

    Supports:
    - Text-to-image: FLUX 2 Pro
    - NL image editing: FLUX Kontext
    - Background removal: BiRefNet
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or get_settings().fal_api_key
        self._client: ManagedHTTPClient | None = None

    async def _get_client(self) -> ManagedHTTPClient:
        """Get or create the pool-managed HTTP client for fal.ai."""
        if self._client is None or self._client.is_closed:
            self._client = await HTTPClientPool.get_client(
                name="fal-image-generation",
                timeout=120.0,
                headers={"Authorization": f"Key {self._api_key}"},
            )
        return self._client

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def close(self) -> None:
        await HTTPClientPool.close_client("fal-image-generation")
        self._client = None

    @http_retry
    async def _submit_and_poll(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Submit a job to fal.ai queue and poll for result."""
        if not self._api_key:
            raise ConfigurationException("fal.ai API key not configured (FAL_API_KEY)")

        client = await self._get_client()

        # Submit to queue
        submit_url = f"{FAL_QUEUE_URL}/{model_id}"
        resp = await client.post(submit_url, json=payload)
        resp.raise_for_status()
        submit_data = resp.json()

        request_id = submit_data.get("request_id")
        if not request_id:
            raise ImageGenerationException("No request_id in fal.ai response")

        # Poll for status
        status_url = f"{FAL_RESULT_URL}/{model_id}/requests/{request_id}/status"
        for _ in range(120):  # max ~2 min polling
            import asyncio

            await asyncio.sleep(1)

            status_resp = await client.get(status_url)
            status_resp.raise_for_status()
            status_data = status_resp.json()
            status = status_data.get("status")

            if status == "COMPLETED":
                result_url = f"{FAL_RESULT_URL}/{model_id}/requests/{request_id}"
                result_resp = await client.get(result_url)
                result_resp.raise_for_status()
                return result_resp.json()
            if status in ("FAILED", "CANCELLED"):
                error = status_data.get("error", "Unknown error")
                raise RuntimeError(f"fal.ai job failed: {error}")

        raise TimeoutError("fal.ai job timed out after 120s")

    async def generate_image(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        num_images: int = 1,
    ) -> list[str]:
        """Generate image(s) from text prompt using FLUX 2 Pro.

        Returns list of image URLs.
        """
        settings = get_settings()
        max_size = settings.image_generation_max_size
        width = min(width, max_size)
        height = min(height, max_size)

        payload = {
            "prompt": prompt,
            "image_size": {"width": width, "height": height},
            "num_images": min(num_images, 4),
            "safety_tolerance": "2",
        }

        logger.info(f"Generating image: prompt='{prompt[:80]}...', size={width}x{height}")
        result = await self._submit_and_poll("fal-ai/flux-pro/v1.1", payload)

        images = result.get("images", [])
        urls = [img.get("url", "") for img in images if img.get("url")]
        logger.info(f"Generated {len(urls)} image(s)")
        return urls

    async def edit_image(
        self,
        image_url: str,
        prompt: str,
    ) -> list[str]:
        """Edit an image using natural language with FLUX Kontext.

        Returns list of edited image URLs.
        """
        payload = {
            "prompt": prompt,
            "image_url": image_url,
        }

        logger.info(f"Editing image: prompt='{prompt[:80]}...'")
        result = await self._submit_and_poll("fal-ai/flux-pro/kontext", payload)

        images = result.get("images", [])
        urls = [img.get("url", "") for img in images if img.get("url")]
        logger.info(f"Edited image, got {len(urls)} result(s)")
        return urls

    async def remove_background(self, image_url: str) -> list[str]:
        """Remove background from image using BiRefNet.

        Returns list of processed image URLs.
        """
        payload = {
            "image_url": image_url,
        }

        logger.info("Removing background from image")
        result = await self._submit_and_poll("fal-ai/birefnet/v2", payload)

        images = result.get("images", [])
        urls = [img.get("url", "") for img in images if img.get("url")]
        logger.info(f"Background removed, got {len(urls)} result(s)")
        return urls


# Global singleton
_image_generation_service: ImageGenerationService | None = None


def get_image_generation_service() -> ImageGenerationService:
    global _image_generation_service
    if _image_generation_service is None:
        _image_generation_service = ImageGenerationService()
    return _image_generation_service
