# -*- coding: utf-8 -*-
"""
WorkflowContext 单元测试

测试 WorkflowContext 的创建、验证和辅助函数。
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# 导入辅助函数（不需要完整的 WorkflowContext）
from tableau_assistant.src.workflow.context import (
    MetadataLoadStatus,
    create_workflow_config,
    get_context,
    get_context_or_raise,
)


# ═══════════════════════════════════════════════════════════════════════════
# MetadataLoadStatus 测试
# ═══════════════════════════════════════════════════════════════════════════

class TestMetadataLoadStatus:
    """MetadataLoadStatus 测试"""
    
    def test_create_status(self):
        """测试创建加载状态"""
        status = MetadataLoadStatus(
            source="cache",
            is_preloading=False,
            waited_seconds=0,
            hierarchy_inferred=False,
            message="从缓存加载"
        )
        
        assert status.source == "cache"
        assert status.is_preloading is False
        assert status.waited_seconds == 0
        assert status.hierarchy_inferred is False
        assert status.message == "从缓存加载"
    
    def test_to_dict(self):
        """测试转换为字典"""
        status = MetadataLoadStatus(
            source="preload",
            is_preloading=True,
            waited_seconds=5.5,
            hierarchy_inferred=True,
            message="等待预热完成"
        )
        
        result = status.to_dict()
        
        assert result["source"] == "preload"
        assert result["is_preloading"] is True
        assert result["waited_seconds"] == 5.5
        assert result["hierarchy_inferred"] is True
        assert result["message"] == "等待预热完成"


# ═══════════════════════════════════════════════════════════════════════════
# Config 辅助函数测试
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigHelpers:
    """Config 辅助函数测试"""
    
    def test_get_context_none_config(self):
        """测试 config 为 None 时返回 None"""
        ctx = get_context(None)
        assert ctx is None
    
    def test_get_context_no_workflow_context(self):
        """测试 config 中没有 workflow_context 时返回 None"""
        config = {"configurable": {"thread_id": "thread_123"}}
        ctx = get_context(config)
        assert ctx is None
    
    def test_get_context_with_workflow_context(self):
        """测试 config 中有 workflow_context 时返回它"""
        mock_ctx = MagicMock()
        config = {"configurable": {"thread_id": "thread_123", "workflow_context": mock_ctx}}
        ctx = get_context(config)
        assert ctx == mock_ctx
    
    def test_get_context_or_raise_none_config(self):
        """测试 config 为 None 时抛出异常"""
        with pytest.raises(ValueError, match="config is None"):
            get_context_or_raise(None)
    
    def test_get_context_or_raise_no_workflow_context(self):
        """测试 config 中没有 workflow_context 时抛出异常"""
        config = {"configurable": {"thread_id": "thread_123"}}
        with pytest.raises(ValueError, match="WorkflowContext not found"):
            get_context_or_raise(config)
    
    def test_get_context_or_raise_success(self):
        """测试成功获取上下文"""
        mock_ctx = MagicMock()
        config = {"configurable": {"thread_id": "thread_123", "workflow_context": mock_ctx}}
        ctx = get_context_or_raise(config)
        assert ctx == mock_ctx
    
    def test_create_workflow_config(self):
        """测试创建工作流配置"""
        mock_ctx = MagicMock()
        mock_ctx.auth.model_dump.return_value = {"api_key": "test"}
        
        config = create_workflow_config("thread_123", mock_ctx)
        
        assert "configurable" in config
        assert config["configurable"]["thread_id"] == "thread_123"
        assert config["configurable"]["workflow_context"] == mock_ctx
        assert "tableau_auth" in config["configurable"]
    
    def test_create_workflow_config_with_extra(self):
        """测试创建带额外配置的工作流配置"""
        mock_ctx = MagicMock()
        mock_ctx.auth.model_dump.return_value = {"api_key": "test"}
        
        config = create_workflow_config(
            "thread_123",
            mock_ctx,
            custom_key="custom_value"
        )
        
        assert config["configurable"]["custom_key"] == "custom_value"
