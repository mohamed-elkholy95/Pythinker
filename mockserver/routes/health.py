from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "code": 0,
        "msg": "success",
        "data": {"status": "healthy", "version": "1.0.0-demo"},
    }


@router.get("/health/ready")
async def readiness():
    return {"code": 0, "msg": "success", "data": {"ready": True}}
