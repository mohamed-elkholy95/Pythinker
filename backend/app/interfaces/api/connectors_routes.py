"""API routes for connector management."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.application.services.connector_service import get_connector_service
from app.domain.models.connector import (
    Connector,
    ConnectorAuthType,
    ConnectorType,
    CustomApiConfig,
    CustomMcpConfig,
    UserConnector,
)
from app.domain.models.user import User
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.connector import (
    ConnectorListResponse,
    ConnectorResponse,
    CreateCustomApiRequest,
    CreateCustomMcpRequest,
    CustomApiConfigResponse,
    CustomMcpConfigResponse,
    TestConnectionResponse,
    UpdateUserConnectorRequest,
    UserConnectorListResponse,
    UserConnectorResponse,
    _mask_api_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connectors", tags=["connectors"])


def _connector_to_response(c: Connector) -> ConnectorResponse:
    return ConnectorResponse(
        id=c.id,
        name=c.name,
        description=c.description,
        connector_type=c.connector_type.value if hasattr(c.connector_type, "value") else str(c.connector_type),
        icon=c.icon,
        brand_color=c.brand_color,
        category=c.category,
        is_official=c.is_official,
    )


def _user_connector_to_response(uc: UserConnector) -> UserConnectorResponse:
    api_config_resp = None
    if uc.api_config:
        api_config_resp = CustomApiConfigResponse(
            base_url=uc.api_config.base_url,
            auth_type=uc.api_config.auth_type.value
            if hasattr(uc.api_config.auth_type, "value")
            else str(uc.api_config.auth_type),
            api_key=_mask_api_key(uc.api_config.api_key),
            headers=uc.api_config.headers,
            description=uc.api_config.description,
        )

    mcp_config_resp = None
    if uc.mcp_config:
        mcp_config_resp = CustomMcpConfigResponse(
            transport=uc.mcp_config.transport,
            command=uc.mcp_config.command,
            args=uc.mcp_config.args,
            url=uc.mcp_config.url,
            headers=uc.mcp_config.headers,
            env=uc.mcp_config.env,
            description=uc.mcp_config.description,
        )

    return UserConnectorResponse(
        id=uc.id,
        connector_id=uc.connector_id,
        connector_type=uc.connector_type.value if hasattr(uc.connector_type, "value") else str(uc.connector_type),
        name=uc.name,
        description=uc.description,
        icon=uc.icon,
        status=uc.status.value if hasattr(uc.status, "value") else str(uc.status),
        enabled=uc.enabled,
        last_connected_at=uc.last_connected_at,
        error_message=uc.error_message,
        api_config=api_config_resp,
        mcp_config=mcp_config_resp,
    )


# --- Catalog endpoints ---


@router.get("/catalog", response_model=APIResponse[ConnectorListResponse])
async def get_catalog(
    type: str | None = None,
    search: str | None = None,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ConnectorListResponse]:
    """Get available connectors from the catalog."""
    service = get_connector_service()
    connector_type = None
    if type:
        try:
            connector_type = ConnectorType(type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid connector type: {type}") from e

    connectors = await service.get_available_connectors(connector_type=connector_type, search=search)
    return APIResponse(
        data=ConnectorListResponse(
            connectors=[_connector_to_response(c) for c in connectors],
            total=len(connectors),
        )
    )


@router.get("/catalog/{connector_id}", response_model=APIResponse[ConnectorResponse])
async def get_catalog_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ConnectorResponse]:
    """Get a specific connector from the catalog."""
    service = get_connector_service()
    connector = await service.get_connector_by_id(connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    return APIResponse(data=_connector_to_response(connector))


# --- User connector endpoints ---


@router.get("/user", response_model=APIResponse[UserConnectorListResponse])
async def get_user_connectors(
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserConnectorListResponse]:
    """Get all connectors for the current user."""
    service = get_connector_service()
    user_connectors = await service.get_user_connectors(current_user.id)
    connected = [uc for uc in user_connectors if uc.status.value == "connected" and uc.enabled]
    return APIResponse(
        data=UserConnectorListResponse(
            connectors=[_user_connector_to_response(uc) for uc in user_connectors],
            total=len(user_connectors),
            connected_count=len(connected),
        )
    )


@router.get("/user/{user_connector_id}", response_model=APIResponse[UserConnectorResponse])
async def get_user_connector(
    user_connector_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserConnectorResponse]:
    """Get a specific user connector."""
    service = get_connector_service()
    uc = await service._user_connector_repo.get_by_id(user_connector_id)
    if not uc or uc.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Connector not found")
    return APIResponse(data=_user_connector_to_response(uc))


@router.post("/user/connect/{connector_id}", response_model=APIResponse[UserConnectorResponse])
async def connect_app(
    connector_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserConnectorResponse]:
    """Connect a pre-built app connector."""
    service = get_connector_service()
    try:
        uc = await service.connect_app(current_user.id, connector_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return APIResponse(data=_user_connector_to_response(uc))


@router.post("/user/custom-api", response_model=APIResponse[UserConnectorResponse])
async def create_custom_api(
    request: CreateCustomApiRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserConnectorResponse]:
    """Create a custom API connector."""
    service = get_connector_service()
    config = CustomApiConfig(
        base_url=request.base_url,
        auth_type=ConnectorAuthType(request.auth_type),
        api_key=request.api_key,
        headers=request.headers,
    )
    uc = await service.create_custom_api(
        user_id=current_user.id,
        name=request.name,
        config=config,
        description=request.description,
    )
    return APIResponse(data=_user_connector_to_response(uc))


@router.post("/user/custom-mcp", response_model=APIResponse[UserConnectorResponse])
async def create_custom_mcp(
    request: CreateCustomMcpRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserConnectorResponse]:
    """Create a custom MCP server connector."""
    service = get_connector_service()
    config = CustomMcpConfig(
        transport=request.transport,
        command=request.command,
        args=request.args,
        url=request.url,
        headers=request.headers,
        env=request.env,
    )
    uc = await service.create_custom_mcp(
        user_id=current_user.id,
        name=request.name,
        config=config,
        description=request.description,
    )
    return APIResponse(data=_user_connector_to_response(uc))


@router.put("/user/{user_connector_id}", response_model=APIResponse[UserConnectorResponse])
async def update_user_connector(
    user_connector_id: str,
    request: UpdateUserConnectorRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[UserConnectorResponse]:
    """Update a user connector."""
    service = get_connector_service()
    api_config = None
    if request.api_config:
        api_config = CustomApiConfig.model_validate(request.api_config)
    mcp_config = None
    if request.mcp_config:
        mcp_config = CustomMcpConfig.model_validate(request.mcp_config)

    uc = await service.update_custom_connector(
        user_id=current_user.id,
        user_connector_id=user_connector_id,
        name=request.name,
        description=request.description,
        enabled=request.enabled,
        api_config=api_config,
        mcp_config=mcp_config,
    )
    if not uc:
        raise HTTPException(status_code=404, detail="Connector not found")
    return APIResponse(data=_user_connector_to_response(uc))


@router.delete("/user/{user_connector_id}", response_model=APIResponse[dict[str, bool]])
async def delete_user_connector(
    user_connector_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[dict[str, bool]]:
    """Delete a user connector."""
    service = get_connector_service()
    deleted = await service.delete_custom_connector(current_user.id, user_connector_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connector not found")
    return APIResponse(data={"deleted": True})


@router.post("/user/{user_connector_id}/test", response_model=APIResponse[TestConnectionResponse])
async def test_connection(
    user_connector_id: str,
    current_user: User = Depends(get_current_user),
) -> APIResponse[TestConnectionResponse]:
    """Test a connector's connection."""
    service = get_connector_service()
    result = await service.test_connection(current_user.id, user_connector_id)
    return APIResponse(
        data=TestConnectionResponse(
            ok=bool(result["ok"]),
            message=str(result["message"]),
            latency_ms=result.get("latency_ms"),  # type: ignore[arg-type]
        )
    )
