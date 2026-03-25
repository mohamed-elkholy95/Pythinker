"""Tests for DatasourceService stub."""

import pytest

from app.domain.services.datasource import DatasourceService


@pytest.fixture()
def service() -> DatasourceService:
    return DatasourceService()


class TestDatasourceService:
    @pytest.mark.asyncio()
    async def test_get_relevant_apis_empty(self, service: DatasourceService) -> None:
        apis = await service.get_relevant_apis("weather data for New York")
        assert apis == []

    @pytest.mark.asyncio()
    async def test_register_api(self, service: DatasourceService) -> None:
        event = await service.register_api("WeatherBank/get_weather", "Get weather data")
        assert event.api_name == "WeatherBank/get_weather"
        assert event.documentation == "Get weather data"
        assert event.type == "datasource"

    @pytest.mark.asyncio()
    async def test_get_api_documentation_none(self, service: DatasourceService) -> None:
        result = await service.get_api_documentation("NonExistent/api")
        assert result is None
