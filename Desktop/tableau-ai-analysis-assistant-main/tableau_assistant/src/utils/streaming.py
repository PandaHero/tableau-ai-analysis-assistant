# -*- coding: utf-8 -*-
"""
流式输出辅助函数

提供统一的 LLM 流式输出调用接口，支持：
1. Token 级别的实时流式输出
2. 手动 JSON 解析为结构化输出
3. 可选的 token 显示控制
"""
import json
import logging
from typing import Dict, Any, Type, TypeVar

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


async def invoke_with_streaming(
    prompt: ChatPromptTemplate,
    llm: BaseChatModel,
    input_data: Dict[str, Any],
    output_model: Type[T],
    show_tokens: bool = True
) -> T:
    """
    统一使用流式输出调用 LLM，手动解析 JSON
    
    注意：不使用 with_structured_output，因为它不支持 token 级别的流式输出。
    相反，我们：
    1. 自动从 Pydantic 模型生成 JSON Schema
    2. 将 Schema 注入到 prompt 中
    3. 使用 astream_events 捕获 token 流
    4. 手动解析并验证输出
    
    Args:
        prompt: prompt 模板
        llm: 语言模型
        input_data: prompt 的输入变量
        output_model: Pydantic 输出模型（用于生成 Schema 和验证）
        show_tokens: 是否实时打印 token (默认 True，显示流式输出)
    
    Returns:
        解析后的输出模型实例
    
    Raises:
        ValueError: 当 LLM 输出无法解析为有效 JSON 时
        Exception: 其他流式输出相关错误
    
    Example:
        >>> from tableau_assistant.prompts.understanding import UNDERSTANDING_PROMPT
        >>> from tableau_assistant.src.models.question import QuestionUnderstanding
        >>> 
        >>> result = await invoke_with_streaming(
        ...     prompt=UNDERSTANDING_PROMPT,
        ...     llm=llm,
        ...     input_data={"question": "哪个门店的收入最高？"},
        ...     output_model=QuestionUnderstanding,
        ...     show_tokens=True
        ... )
    """
    try:
        # 生成 JSON Schema 并注入到 input_data 中
        json_schema = output_model.model_json_schema()
        input_data_with_schema = {
            **input_data,
            "json_schema": json.dumps(json_schema, indent=2, ensure_ascii=False)
        }
        
        # 创建 chain（不使用 with_structured_output）
        chain = prompt | llm
        
        # 使用 astream_events 捕获 token 流
        collected_content = []
        token_count = 0
        
        if show_tokens:
            print("  🔄 [开始流式输出] ", end="", flush=True)
        
        async for event in chain.astream_events(input_data_with_schema, version="v2"):
            event_type = event.get("event")
            
            # 捕获 token 流式输出
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content"):
                    token = chunk.content
                    if token:
                        if show_tokens:
                            print(token, end="", flush=True)
                        collected_content.append(token)
                        token_count += 1
        
        if show_tokens:
            if token_count > 0:
                print(f" [结束流式输出] ✓ ({token_count} tokens)", flush=True)
            else:
                print(" [结束] ✓ (无token流)", flush=True)
            print()  # 换行
        
        # 手动解析 JSON
        full_content = "".join(collected_content)
        
        if not full_content.strip():
            raise ValueError("LLM 返回空内容")
        
        try:
            result = output_model.model_validate_json(full_content)
            return result
        except json.JSONDecodeError as e:
            # JSON 解析失败 - 记录错误并抛出
            logger.error(f"JSON 解析失败: {e}")
            logger.error(f"LLM 输出内容: {full_content[:500]}...")
            raise ValueError(f"LLM 输出无法解析为有效 JSON: {e}")
        except Exception as e:
            # Pydantic 验证失败
            logger.error(f"Pydantic 模型验证失败: {e}")
            logger.error(f"LLM 输出内容: {full_content[:500]}...")
            raise ValueError(f"LLM 输出不符合模型规范: {e}")
        
    except ValueError:
        # 重新抛出 ValueError（JSON 解析或验证错误）
        raise
    except Exception as e:
        # 其他错误 - 记录并抛出
        logger.error(f"流式输出调用失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise


# ============= 导出 =============

__all__ = [
    "invoke_with_streaming",
]
