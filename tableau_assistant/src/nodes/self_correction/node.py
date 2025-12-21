# -*- coding: utf-8 -*-
"""
Self-Correction Node

当 Execute 节点执行失败时，分析错误并尝试修复查询。

工作流程：
1. 检查 query_result 是否有错误
2. 分析错误类型
3. 尝试自动修复（字段名纠正等）
4. 如果无法自动修复，调用 LLM 生成修复建议
5. 返回修复后的查询或放弃

Requirements:
- 基于 MODULE_ARCHITECTURE_DEEP_ANALYSIS.md 中的 Self-Correction 改进建议
"""

import logging
from typing import Any, Dict, Optional

from langgraph.types import RunnableConfig

from tableau_assistant.src.orchestration.workflow.state import VizQLState
from .corrector import QueryCorrector, CorrectionResult, ErrorCategory

logger = logging.getLogger(__name__)


class SelfCorrectionNode:
    """
    Self-Correction Node 实现
    
    分析执行错误，尝试修复查询。
    """
    
    def __init__(
        self,
        max_attempts: int = 2,
        use_llm_fallback: bool = True,
    ):
        """
        初始化 Self-Correction Node
        
        Args:
            max_attempts: 最大纠错尝试次数
            use_llm_fallback: 是否使用 LLM 作为后备纠错方案
        """
        self.max_attempts = max_attempts
        self.use_llm_fallback = use_llm_fallback
    
    async def execute(
        self,
        state: VizQLState,
        config: Optional[RunnableConfig] = None,
    ) -> Dict[str, Any]:
        """
        执行自我纠错
        
        Args:
            state: 当前工作流状态
            config: LangGraph 配置
            
        Returns:
            更新后的状态
        """
        # 获取当前纠错次数
        correction_count = state.get("correction_count", 0)
        
        # 检查是否超过最大尝试次数
        if correction_count >= self.max_attempts:
            logger.warning(f"已达到最大纠错次数 ({self.max_attempts})，放弃纠错")
            return {
                "correction_count": correction_count,
                "correction_exhausted": True,
            }
        
        # 获取错误信息
        query_result = state.get("query_result")
        if not query_result:
            logger.warning("没有 query_result，跳过纠错")
            return {"correction_exhausted": True}
        
        # 检查是否有错误
        error_message = None
        if hasattr(query_result, 'error'):
            error_message = query_result.error
        elif isinstance(query_result, dict):
            error_message = query_result.get('error')
        
        if not error_message:
            logger.info("query_result 没有错误，跳过纠错")
            return {"correction_exhausted": True}
        
        logger.info(f"开始自我纠错 (attempt {correction_count + 1}/{self.max_attempts})")
        logger.info(f"错误信息: {error_message}")
        
        # 获取原始查询
        vizql_query = state.get("vizql_query")
        if not vizql_query:
            logger.warning("没有 vizql_query，无法纠错")
            return {"correction_exhausted": True}
        
        # 转换为 dict
        if hasattr(vizql_query, 'model_dump'):
            query_dict = vizql_query.model_dump(exclude_none=True)
        elif hasattr(vizql_query, 'to_dict'):
            query_dict = vizql_query.to_dict()
        elif isinstance(vizql_query, dict):
            query_dict = vizql_query.copy()
        else:
            logger.warning(f"无法处理的 vizql_query 类型: {type(vizql_query)}")
            return {"correction_exhausted": True}
        
        # 获取数据模型用于字段验证
        data_model = state.get("data_model")
        
        # 创建纠错器
        corrector = QueryCorrector(data_model=data_model)
        
        # 尝试纠错
        result = corrector.correct(query_dict, error_message)
        
        if result.can_correct and result.corrected_query:
            logger.info(f"自动纠错成功: {result.reason}")
            for suggestion in result.suggestions:
                logger.info(f"  - {suggestion.reason}")
            
            # 记录纠错历史
            correction_history = state.get("correction_history", [])
            correction_history.append({
                "attempt": correction_count + 1,
                "error_category": result.error_category.value,
                "suggestions": [s.model_dump() for s in result.suggestions],
                "reason": result.reason,
            })
            
            return {
                "vizql_query": result.corrected_query,
                "correction_count": correction_count + 1,
                "correction_history": correction_history,
                "correction_exhausted": False,
                # 清除之前的错误，准备重新执行
                "query_result": None,
            }
        
        # 自动纠错失败，尝试 LLM 后备方案
        if self.use_llm_fallback and result.error_category not in [
            ErrorCategory.PERMISSION_DENIED,
            ErrorCategory.TIMEOUT,
        ]:
            logger.info("自动纠错失败，尝试 LLM 后备方案")
            llm_result = await self._llm_correction(
                state, query_dict, error_message, config
            )
            if llm_result:
                correction_history = state.get("correction_history", [])
                correction_history.append({
                    "attempt": correction_count + 1,
                    "error_category": result.error_category.value,
                    "method": "llm",
                    "reason": "LLM 生成修复建议",
                })
                return {
                    "vizql_query": llm_result,
                    "correction_count": correction_count + 1,
                    "correction_history": correction_history,
                    "correction_exhausted": False,
                    "query_result": None,
                }
        
        # 无法纠错
        logger.warning(f"无法纠错: {result.reason}")
        return {
            "correction_count": correction_count + 1,
            "correction_exhausted": True,
        }
    
    async def _llm_correction(
        self,
        state: VizQLState,
        query: Dict[str, Any],
        error_message: str,
        config: Optional[RunnableConfig] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        使用 LLM 生成修复建议
        
        Args:
            state: 当前状态
            query: 原始查询
            error_message: 错误信息
            config: LangGraph 配置
            
        Returns:
            修复后的查询，如果无法修复返回 None
        """
        try:
            from tableau_assistant.src.agents.base import (
                get_llm,
                call_llm_with_tools,
                parse_json_response,
            )
            
            # 获取数据模型信息
            data_model = state.get("data_model")
            available_fields = []
            if data_model:
                fields = getattr(data_model, 'fields', [])
                if isinstance(data_model, dict):
                    fields = data_model.get('fields', [])
                for f in fields[:50]:  # 限制字段数量
                    if hasattr(f, 'name'):
                        available_fields.append(f"{f.name} ({getattr(f, 'fieldCaption', f.name)})")
                    elif isinstance(f, dict):
                        available_fields.append(f"{f.get('name')} ({f.get('fieldCaption', f.get('name'))})")
            
            # 构建提示
            import json
            prompt = f"""你是一个 VizQL 查询修复专家。请分析以下查询执行错误，并生成修复后的查询。

## 原始查询
```json
{json.dumps(query, indent=2, ensure_ascii=False)}
```

## 错误信息
{error_message}

## 可用字段
{chr(10).join(available_fields[:30]) if available_fields else '(无字段信息)'}

## 要求
1. 分析错误原因
2. 生成修复后的查询
3. 只返回 JSON 格式的修复后查询，不要其他内容

## 输出格式
```json
{{
  "can_fix": true/false,
  "reason": "修复原因说明",
  "fixed_query": {{ ... }}  // 修复后的查询，如果无法修复则为 null
}}
```
"""
            
            from langchain_core.messages import HumanMessage
            messages = [HumanMessage(content=prompt)]
            
            # 获取 middleware
            middleware = None
            if config and "configurable" in config:
                middleware = config["configurable"].get("middleware")
            
            # 调用 LLM
            llm = get_llm(agent_name="self_correction")
            response = await call_llm_with_tools(
                llm=llm,
                messages=messages,
                tools=[],
                streaming=False,
                middleware=middleware,
                state=dict(state) if state else {},
                config=config,
            )
            
            # 解析响应
            import re
            content = response.content if hasattr(response, 'content') else str(response)
            
            # 提取 JSON
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                result = json.loads(content)
            
            if result.get("can_fix") and result.get("fixed_query"):
                logger.info(f"LLM 修复成功: {result.get('reason')}")
                return result["fixed_query"]
            else:
                logger.info(f"LLM 无法修复: {result.get('reason')}")
                return None
                
        except Exception as e:
            logger.warning(f"LLM 纠错失败: {e}")
            return None


async def self_correction_node(
    state: VizQLState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """
    Self-Correction 节点入口
    
    Args:
        state: VizQLState
        config: RunnableConfig
        
    Returns:
        更新后的状态
    """
    logger.info("Self-Correction node started")
    
    # 从配置获取参数
    max_attempts = 2
    use_llm_fallback = True
    
    if config and "configurable" in config:
        workflow_config = config["configurable"].get("workflow_config", {})
        max_attempts = workflow_config.get("max_correction_attempts", 2)
        use_llm_fallback = workflow_config.get("use_llm_correction", True)
    
    node = SelfCorrectionNode(
        max_attempts=max_attempts,
        use_llm_fallback=use_llm_fallback,
    )
    
    result = await node.execute(state, config)
    
    logger.info(f"Self-Correction node completed: exhausted={result.get('correction_exhausted', True)}")
    return result
