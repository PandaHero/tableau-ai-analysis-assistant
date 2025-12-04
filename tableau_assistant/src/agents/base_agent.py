"""
Base agent class for VizQL agents (v2 architecture)

Provides a clean, unified architecture for agent implementation with:
- Automatic prompt integration
- Streaming output support
- Template method pattern for customization
- Dynamic model selection (supports frontend model configuration)
- Per-agent temperature configuration
"""
from typing import Dict, Any, Optional
from langgraph.runtime import Runtime

from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.prompts.base import BasePrompt


# ============= Agent Temperature 配置 =============
# 不同 Agent 有不同的最佳 temperature 设置
# - 低 temperature (0.0-0.2): 需要精确、确定性输出的任务
# - 中 temperature (0.3-0.5): 需要一定创造性但仍需结构化的任务
# - 高 temperature (0.6-0.8): 需要创造性和多样性的任务

AGENT_TEMPERATURE_CONFIG = {
    # Understanding: 需要精确理解用户意图，低 temperature
    "UnderstandingAgent": 0.1,
    
    # TaskPlanner: 需要精确的字段映射和查询规划，低 temperature
    "TaskPlannerAgent": 0.1,
    
    # QuestionBoost: 需要一定创造性来优化问题，中 temperature
    "QuestionBoostAgent": 0.3,
    
    # Insight: 需要创造性来发现洞察，中高 temperature
    "InsightAgent": 0.4,
    
    # Replanner: 需要判断是否重规划，中 temperature
    "ReplannerAgent": 0.2,
    
    # DimensionHierarchy: 需要精确推断层级关系，低 temperature
    "DimensionHierarchyAgent": 0.1,
    
    # 默认值
    "default": 0.2
}


def get_agent_temperature(agent_name: str) -> float:
    """
    获取指定 Agent 的默认 temperature
    
    Args:
        agent_name: Agent 类名
    
    Returns:
        temperature 值 (0.0-1.0)
    """
    return AGENT_TEMPERATURE_CONFIG.get(agent_name, AGENT_TEMPERATURE_CONFIG["default"])


class BaseVizQLAgent:
    """
    Base class for VizQL agents with clean prompt integration
    
    This class provides a unified execution flow:
    1. Prepare input data (_prepare_input_data)
    2. Execute with streaming (_execute_with_prompt)
    3. Process result (_process_result)
    
    Subclasses only need to implement:
    - _prepare_input_data(): Format state data for the prompt
    - _process_result(): Wrap the result for state update
    
    Features:
    - Per-agent temperature configuration (see AGENT_TEMPERATURE_CONFIG)
    - Dynamic model selection from frontend
    - Streaming output support
    
    Example:
        class MyAgent(BaseVizQLAgent):
            def __init__(self):
                super().__init__(MyPrompt())
            
            def _prepare_input_data(self, state, **kwargs):
                return {
                    "question": state['question'],
                    "metadata": state['metadata']
                }
            
            def _process_result(self, result, state):
                return {"my_result": result}
    """
    
    def __init__(self, prompt: BasePrompt, temperature: Optional[float] = None):
        """
        Initialize agent with a prompt
        
        Args:
            prompt: BasePrompt instance that defines the agent's behavior
            temperature: Optional custom temperature (if None, uses AGENT_TEMPERATURE_CONFIG)
        """
        self.prompt = prompt
        # 使用自定义 temperature 或从配置获取
        self._custom_temperature = temperature
    
    async def execute(
        self,
        state: VizQLState,
        runtime: Runtime[VizQLContext],
        model_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute agent with streaming output
        
        This is the main entry point for agent execution. It:
        1. Prepares input data from state
        2. Executes the prompt with streaming
        3. Processes and returns the result
        
        Args:
            state: Current VizQL state
            runtime: Runtime context
            model_config: Optional model configuration from frontend
                - provider: "local", "azure", or "openai"
                - model_name: Model name (e.g., "gpt-4o-mini", "qwen3")
                - temperature: Temperature setting (0.0-1.0)
            **kwargs: Additional arguments passed to _prepare_input_data
        
        Returns:
            Dict with processed result (ready for state update)
        
        Example:
            # Use default model from settings
            result = await agent.execute(state, runtime)
            
            # Use specific model from frontend
            result = await agent.execute(state, runtime,
                model_config={
                    "provider": "openai",
                    "model_name": "gpt-4o",
                    "temperature": 0.3
                })
        """
        # Prepare input data for the prompt
        input_data = self._prepare_input_data(state, **kwargs)
        
        # Execute with streaming (pass model_config)
        result = await self._execute_with_prompt(input_data, runtime, model_config)
        
        # Process and return result
        return self._process_result(result, state)
    
    async def _execute_with_prompt(
        self,
        input_data: Dict[str, Any],
        runtime: Runtime[VizQLContext],
        model_config: Optional[Dict[str, Any]] = None
    ):
        """
        Execute prompt with streaming output
        
        This method handles the actual LLM invocation with streaming.
        It uses the new BasePrompt.format_messages() method.
        
        Args:
            input_data: Prepared input data for the prompt
            runtime: Runtime context
            model_config: Optional model configuration from frontend
                - provider: "local", "azure", or "openai"
                - model_name: Model name
                - temperature: Temperature setting
        
        Returns:
            Parsed and validated output model instance
        """
        # Get LLM using select_model (supports frontend model selection)
        from tableau_assistant.src.model_manager import select_model
        from tableau_assistant.src.config.settings import settings
        from tableau_assistant.src.capabilities.storage.llm_cache import LLMCache
        from tableau_assistant.src.monitoring.callbacks import SQLiteTrackingCallback
        from tableau_assistant.src.utils.retry import retry_async_call
        from langchain_core.runnables import RunnableConfig
        
        # 获取当前 Agent 的默认 temperature
        agent_name = self.__class__.__name__
        default_temp = self._custom_temperature if self._custom_temperature is not None else get_agent_temperature(agent_name)
        
        # Use model_config from frontend if provided, otherwise use settings
        if model_config:
            provider = model_config.get('provider', settings.llm_model_provider)
            model_name = model_config.get('model_name', settings.tooling_llm_model)
            # 前端可以覆盖 temperature，否则使用 agent 默认值
            temperature = model_config.get('temperature', default_temp)
        else:
            # Default: use settings configuration with agent-specific temperature
            provider = settings.llm_model_provider
            model_name = settings.tooling_llm_model
            temperature = default_temp
        
        llm = select_model(
            provider=provider,
            model_name=model_name,
            temperature=temperature
        )
        
        # Format messages using the prompt
        messages = self.prompt.format_messages(**input_data)
        
        # Get output model for validation
        output_model = self.prompt.get_output_model()
        
        # 1. 初始化 LLM 缓存
        llm_cache = LLMCache(store=runtime.store, ttl=3600)  # 1小时缓存
        
        # 2. 检查缓存
        cached_content = llm_cache.get(messages, model_name, temperature)
        if cached_content:
            print(f"  ✓ [使用缓存响应] ({len(cached_content)} 字符)")
            # 直接解析缓存的内容
            cleaned_content = self._clean_json_output(cached_content)
            result = output_model.model_validate_json(cleaned_content)
            return result
        
        # 3. 创建 Callback（监控）
        callback = SQLiteTrackingCallback(
            store=runtime.store,
            user_id=runtime.context.user_id,
            session_id=runtime.context.session_id,
            agent_name=self.__class__.__name__
        )
        
        # 4. 创建 RunnableConfig（传递 Callback）
        config = RunnableConfig(
            tags=[
                f"user_{runtime.context.user_id}",
                f"session_{runtime.context.session_id}",
                self.__class__.__name__
            ],
            metadata={
                "user_id": runtime.context.user_id,
                "session_id": runtime.context.session_id,
                "agent_name": self.__class__.__name__,
                "model": model_name,
                "temperature": temperature
            },
            callbacks=[callback]
        )
        
        # 5. 使用重试机制执行 LLM 调用
        async def _execute_llm_with_streaming():
            """带流式输出的 LLM 调用（内部函数，用于重试）"""
            collected_content = []
            token_count = 0
            
            print("  🔄 [开始流式输出] ", end="", flush=True)
            
            # Stream tokens from LLM（传递 config）
            async for event in llm.astream_events(messages, config=config, version="v2"):
                event_type = event.get("event")
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        token = chunk.content
                        if token:
                            print(token, end="", flush=True)
                            collected_content.append(token)
                            token_count += 1
            
            print(f" [结束流式输出] ✓ ({token_count} tokens)", flush=True)
            print()  # 换行
            
            # Parse and validate output
            full_content = "".join(collected_content)
            if not full_content.strip():
                raise ValueError("LLM 返回空内容")
            
            return full_content
        
        # 执行 LLM 调用（带重试）
        try:
            full_content = await retry_async_call(
                _execute_llm_with_streaming,
                max_attempts=3  # 最多重试3次
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"LLM 调用失败（已重试3次）: {e}")
            raise
        
        # Clean JSON content
        cleaned_content = self._clean_json_output(full_content)
        
        try:
            result = output_model.model_validate_json(cleaned_content)
            # 6. 保存到缓存
            llm_cache.set(messages, model_name, temperature, full_content)
            return result
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"输出验证失败: {e}")
            logger.error(f"LLM 输出内容: {cleaned_content[:500]}...")
            raise ValueError(f"LLM 输出不符合模型规范: {e}")

    
    def _clean_json_output(self, content: str) -> str:
        """
        Clean JSON output from LLM using professional JSON repair library
        
        Handles common issues:
        - Markdown code blocks
        - Extra whitespace
        - Malformed array syntax
        - Trailing commas
        - Unescaped quotes in strings
        - Missing quotes around keys
        - Incomplete JSON structures
        """
        import re
        import json
        import logging
        logger = logging.getLogger(__name__)
        
        # Step 1: Remove markdown code blocks
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        
        # Step 2: Extract JSON if there's extra text
        # Look for the first { and last }
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            content = content[start:end+1]
        
        # Step 3: Try to parse as-is first
        try:
            json.loads(content)
            return content.strip()
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}, 尝试使用json-repair修复")
        
        # Step 4: Try using json-repair library
        try:
            from json_repair import repair_json
            repaired = repair_json(content)
            # Validate the repaired JSON
            json.loads(repaired)
            logger.info("JSON修复成功")
            return repaired
        except ImportError:
            logger.warning("json-repair库未安装,使用基础修复方法")
            # Fallback to basic fixes
            return self._basic_json_fix(content)
        except Exception as e:
            logger.error(f"json-repair修复失败: {e}, 使用基础修复方法")
            return self._basic_json_fix(content)
    
    def _basic_json_fix(self, content: str) -> str:
        """
        Basic JSON fixes without external libraries
        
        Args:
            content: Potentially malformed JSON string
        
        Returns:
            Fixed JSON string (best effort)
        """
        import re
        
        # Fix critical issue: "subtasks": [[...]], [[...]] -> "subtasks": [[...], [...]]
        content = re.sub(r'(\]\s*\])\s*,\s*(\[\s*\[)', r'],\2', content)
        
        # Fix nested array issue: "subtasks": [[{...}], [{...}]] -> "subtasks": [{...}, {...}]
        content = re.sub(r'(\[)\s*\[\s*(\{)', r'\1\2', content)
        content = re.sub(r'(\})\s*\]\s*,\s*\[\s*(\{)', r'\1,\2', content)
        content = re.sub(r'(\})\s*\]\s*(\])', r'\1\2', content)
        
        # Fix malformed array syntax: ], [ -> ,
        content = re.sub(r'\]\s*,\s*\[', ',', content)
        
        # Remove trailing commas before closing brackets/braces
        content = re.sub(r',(\s*[}\]])', r'\1', content)
        
        # Fix common quote issues (basic)
        content = content.replace('"', '"').replace('"', '"')
        content = content.replace(''', "'").replace(''', "'")
        
        return content.strip()
    
    def _prepare_input_data(
        self,
        state: VizQLState,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Prepare input data for the prompt (override in subclasses)
        
        This method should extract relevant data from the state
        and format it for the prompt template.
        
        Args:
            state: Current VizQL state
            **kwargs: Additional arguments from execute()
        
        Returns:
            Dict with data for prompt template variables
        
        Example:
            def _prepare_input_data(self, state, **kwargs):
                return {
                    "question": state['boosted_question'],
                    "metadata": state['metadata']
                }
        """
        return kwargs
    
    def _process_result(
        self,
        result: Any,
        state: VizQLState
    ) -> Dict[str, Any]:
        """
        Process the result (override in subclasses)
        
        This method should wrap the result in a format suitable
        for updating the state.
        
        Args:
            result: Parsed output model instance
            state: Current VizQL state
        
        Returns:
            Dict ready for state.update()
        
        Example:
            def _process_result(self, result, state):
                return {
                    "understanding": result,
                    "sub_questions": result.sub_questions
                }
        """
        return {"result": result}


# ============= 导出 =============

__all__ = [
    "BaseVizQLAgent",
    "AGENT_TEMPERATURE_CONFIG",
    "get_agent_temperature",
]
