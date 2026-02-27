# -*- coding: utf-8 -*-
"""
FeatureExtractor - 特征提取器

使用快速 LLM 验证和修正 RulePrefilter 的结果：
- 验证时间提示
- 验证计算种子匹配
- 提取 required_measures 和 required_dimensions

配置来源：
- analytics_assistant/config/app.yaml -> semantic_parser.optimization.feature_extractor

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

import asyncio
import json
import logging
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.agents.base.node import get_llm

from ..schemas.prefilter import (
    FeatureExtractionOutput,
    PrefilterResult,
)
from ..prompts.feature_extractor_prompt import (
    build_feature_extractor_prompt,
    FEATURE_EXTRACTOR_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def get_feature_extractor_config() -> dict[str, Any]:
    """获取 FeatureExtractor 配置。"""
    try:
        config = get_config()
        return config.get_semantic_parser_optimization_config().get(
            "feature_extractor", {}
        )
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}

# ═══════════════════════════════════════════════════════════════════════════
# FeatureExtractor 组件
# ═══════════════════════════════════════════════════════════════════════════

class FeatureExtractor:
    """特征提取器
    
    使用快速 LLM 验证 RulePrefilter 的结果，提取字段需求。
    
    设计原则：
    - 使用项目模型管理系统获取 LLM
    - 精简 Prompt（~200 tokens）
    - 超时后降级到规则结果
    
    Examples:
        >>> extractor = FeatureExtractor()
        >>> result = await extractor.extract(
        ...     question="上个月各地区的利润率",
        ...     prefilter_result=prefilter_result,
        ... )
    """
    
    def __init__(self):
        """初始化 FeatureExtractor。
        
        配置从 app.yaml 加载，LLM 通过项目模型管理系统获取。
        """
        config = get_feature_extractor_config()
        
        # 从配置加载超时时间（毫秒）
        self.timeout_ms = config.get("timeout_ms", 500)
        
        # 使用项目模型管理系统获取 LLM
        # agent_name 用于自动选择 temperature
        self._llm = get_llm(
            agent_name="semantic_parser",
            enable_json_mode=True,
        )
    
    async def extract(
        self,
        question: str,
        prefilter_result: PrefilterResult,
    ) -> FeatureExtractionOutput:
        """提取特征
        
        Args:
            question: 用户问题
            prefilter_result: 规则预处理结果
            
        Returns:
            FeatureExtractionOutput 特征提取输出
        """
        try:
            # 如果配置了超时且大于 0，则使用超时
            if self.timeout_ms > 0:
                timeout_seconds = self.timeout_ms / 1000.0
                result = await asyncio.wait_for(
                    self._extract_with_llm(question, prefilter_result),
                    timeout=timeout_seconds,
                )
            else:
                # 不设置超时
                result = await self._extract_with_llm(question, prefilter_result)
            return result
            
        except asyncio.TimeoutError:
            logger.warning(
                f"FeatureExtractor 超时 ({self.timeout_ms}ms)，使用降级模式"
            )
            return self._create_degraded_output(prefilter_result)
            
        except Exception as e:
            logger.error(f"FeatureExtractor 失败: {e}")
            return self._create_degraded_output(prefilter_result)
    
    async def _extract_with_llm(
        self,
        question: str,
        prefilter_result: PrefilterResult,
    ) -> FeatureExtractionOutput:
        """使用 LLM 提取特征。"""
        # 构建 Prompt
        user_prompt = build_feature_extractor_prompt(question, prefilter_result)
        
        # 调用 LLM
        messages = [
            {"role": "system", "content": FEATURE_EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        
        response = await self._llm.ainvoke(messages)
        
        # 解析响应
        return self._parse_response(response.content, prefilter_result)
    
    def _parse_response(
        self,
        content: str,
        prefilter_result: PrefilterResult,
    ) -> FeatureExtractionOutput:
        """解析 LLM 响应。"""
        try:
            # 尝试解析 JSON
            # 查找 JSON 块
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                data = json.loads(json_str)
                
                return FeatureExtractionOutput(
                    required_measures=data.get("required_measures", []),
                    required_dimensions=data.get("required_dimensions", []),
                    confirmed_time_hints=data.get("confirmed_time_hints", []),
                    confirmed_computations=data.get("confirmed_computations", []),
                    confirmation_confidence=data.get("confirmation_confidence", 0.8),
                    is_degraded=False,
                )
            
            # 解析失败，使用降级
            logger.warning("FeatureExtractor 响应解析失败，使用降级模式")
            return self._create_degraded_output(prefilter_result)
            
        except json.JSONDecodeError as e:
            logger.warning(f"FeatureExtractor JSON 解析失败: {e}")
            return self._create_degraded_output(prefilter_result)
    
    def _create_degraded_output(
        self,
        prefilter_result: PrefilterResult,
    ) -> FeatureExtractionOutput:
        """创建降级输出。
        
        使用 RulePrefilter 的结果作为降级方案。
        """
        # 从时间提示中提取
        confirmed_time_hints = [
            hint.original_expression for hint in prefilter_result.time_hints
        ]
        
        # 从计算种子中提取
        confirmed_computations = [
            comp.seed_name for comp in prefilter_result.matched_computations
        ]
        
        return FeatureExtractionOutput(
            required_measures=[],  # 降级模式下为空，由 FieldRetriever 使用全量检索
            required_dimensions=[],
            confirmed_time_hints=confirmed_time_hints,
            confirmed_computations=confirmed_computations,
            confirmation_confidence=prefilter_result.match_confidence,
            is_degraded=True,
        )

__all__ = ["FeatureExtractor", "get_feature_extractor_config"]
