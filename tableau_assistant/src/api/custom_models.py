"""
自定义模型 API

提供自定义 AI 模型的 CRUD 操作和连接测试功能。
使用 LangGraph SqliteStore 持久化存储。
"""
import logging
import time
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import httpx

from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models/custom", tags=["Custom Models"])

# 命名空间
CUSTOM_MODELS_NAMESPACE = ("custom_models",)


class CustomModelCreate(BaseModel):
    """创建自定义模型请求"""
    name: str = Field(..., description="模型名称", min_length=1, max_length=50)
    apiBase: str = Field(..., description="API 基础地址", min_length=1)
    apiKey: str = Field(..., description="API 密钥", min_length=1)
    modelId: str = Field(..., description="模型标识符", min_length=1)


class CustomModelResponse(BaseModel):
    """自定义模型响应"""
    name: str
    apiBase: str
    modelId: str
    createdAt: float


class CustomModelTestRequest(BaseModel):
    """测试连接请求"""
    apiBase: str = Field(..., description="API 基础地址")
    apiKey: str = Field(..., description="API 密钥")
    modelId: str = Field(..., description="模型标识符")


class CustomModelTestResponse(BaseModel):
    """测试连接响应"""
    success: bool
    message: str
    latency_ms: Optional[float] = None


@router.get("", response_model=List[CustomModelResponse])
async def list_custom_models():
    """获取所有自定义模型列表"""
    try:
        store = get_langgraph_store()
        items = list(store.search(CUSTOM_MODELS_NAMESPACE, limit=100))
        
        models = []
        for item in items:
            models.append(CustomModelResponse(
                name=item.key,
                apiBase=item.value.get("apiBase", ""),
                modelId=item.value.get("modelId", ""),
                createdAt=item.value.get("createdAt", 0)
            ))
        
        models.sort(key=lambda x: x.createdAt, reverse=True)
        return models
        
    except Exception as e:
        logger.error(f"Failed to list custom models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=CustomModelResponse)
async def create_custom_model(model: CustomModelCreate):
    """添加自定义模型"""
    try:
        store = get_langgraph_store()
        
        # 检查是否已存在
        existing = store.get(CUSTOM_MODELS_NAMESPACE, model.name)
        if existing:
            raise HTTPException(status_code=400, detail=f"Model '{model.name}' already exists")
        
        now = time.time()
        data = {
            "apiBase": model.apiBase,
            "apiKey": model.apiKey,
            "modelId": model.modelId,
            "createdAt": now
        }
        
        store.put(CUSTOM_MODELS_NAMESPACE, model.name, data)
        
        return CustomModelResponse(
            name=model.name,
            apiBase=model.apiBase,
            modelId=model.modelId,
            createdAt=now
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create custom model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{name}")
async def delete_custom_model(name: str):
    """删除自定义模型"""
    try:
        store = get_langgraph_store()
        
        existing = store.get(CUSTOM_MODELS_NAMESPACE, name)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
        
        store.delete(CUSTOM_MODELS_NAMESPACE, name)
        return {"success": True, "message": f"Model '{name}' deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete custom model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test", response_model=CustomModelTestResponse)
async def test_custom_model(request: CustomModelTestRequest):
    """测试自定义模型连接"""
    try:
        start_time = time.time()
        
        api_url = request.apiBase.rstrip("/")
        if not api_url.endswith("/chat/completions"):
            if not api_url.endswith("/v1"):
                api_url = f"{api_url}/v1"
            api_url = f"{api_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {request.apiKey}",
            "Content-Type": "application/json"
        }
        
        test_payload = {
            "model": request.modelId,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
            "stream": False
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, headers=headers, json=test_payload)
        
        latency_ms = (time.time() - start_time) * 1000
        
        if response.status_code == 200:
            return CustomModelTestResponse(success=True, message="连接成功", latency_ms=round(latency_ms, 2))
        elif response.status_code == 401:
            return CustomModelTestResponse(success=False, message="API 密钥无效", latency_ms=round(latency_ms, 2))
        elif response.status_code == 404:
            return CustomModelTestResponse(success=False, message=f"模型 '{request.modelId}' 不存在", latency_ms=round(latency_ms, 2))
        else:
            return CustomModelTestResponse(success=False, message=f"请求失败 ({response.status_code})", latency_ms=round(latency_ms, 2))
            
    except httpx.ConnectError:
        return CustomModelTestResponse(success=False, message="无法连接到 API 服务器")
    except httpx.TimeoutException:
        return CustomModelTestResponse(success=False, message="连接超时")
    except Exception as e:
        return CustomModelTestResponse(success=False, message=f"测试失败: {str(e)}")


@router.get("/{name}")
async def get_custom_model(name: str):
    """获取单个自定义模型详情"""
    try:
        store = get_langgraph_store()
        
        item = store.get(CUSTOM_MODELS_NAMESPACE, name)
        if not item:
            raise HTTPException(status_code=404, detail=f"Model '{name}' not found")
        
        return CustomModelResponse(
            name=name,
            apiBase=item.value.get("apiBase", ""),
            modelId=item.value.get("modelId", ""),
            createdAt=item.value.get("createdAt", 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get custom model: {e}")
        raise HTTPException(status_code=500, detail=str(e))
