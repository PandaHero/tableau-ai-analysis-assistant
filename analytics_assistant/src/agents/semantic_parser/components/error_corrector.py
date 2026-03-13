# -*- coding: utf-8 -*-
"""
Error Corrector - 错误修正器

基于执行错误反馈，让 LLM 修正语义理解输出。

核心功能：
1. 错误分类：区分可重试和不可重试的错误
2. 重复检测：相同错误出现 N 次则终止
3. 重试限制：最多 M 次重试
4. LLM 修正：基于错误信息让 LLM 修正输出

防止无限循环机制：
- 相同错误检测：如果相同错误出现 max_same_error_count 次，立即终止
- 最大重试次数：硬性限制 max_retries 次
- 总错误历史检查：防止交替错误（A→B→A→B）绕过检测
- 错误分类：某些错误类型不适合重试

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.error_corrector
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.agents.base import stream_llm_structured

from ..schemas.output import SemanticOutput
from ..schemas.error_correction import ErrorCorrectionHistory, CorrectionResult
from ..prompts.error_correction_prompt import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)

class ErrorCorrector:
    """错误修正器
    
    基于执行错误反馈，让 LLM 修正语义理解输出。
    
    防止无限循环:
    - 相同错误检测：如果相同错误出现 max_same_error_count 次，立即终止
    - 最大重试次数：硬性限制 max_retries 次
    - 总错误历史检查：防止交替错误（A→B→A→B）绕过检测
    - 错误分类：某些错误类型不适合重试
    
    配置项（从 app.yaml 读取）：
    - max_retries: 最大重试次数（默认 3）
    - max_same_error_count: 相同错误最大出现次数（默认 2）
    - non_retryable_errors: 不可重试的错误类型列表
    
    使用方式：
        corrector = ErrorCorrector(llm=llm)
        result = await corrector.correct(
            question=question,
            previous_output=output,
            error_info=error_message,
            error_type="field_not_found",
        )
        if result.should_continue:
            # 使用 result.corrected_output 重新执行
        else:
            # 返回错误给用户
    """
    
    # 默认配置（作为 fallback）
    _DEFAULT_MAX_RETRIES = 3
    _DEFAULT_MAX_SAME_ERROR_COUNT = 2
    _DEFAULT_NON_RETRYABLE_ERRORS = {
        "timeout",
        "service_unavailable",
        "authentication_error",
        "rate_limit_exceeded",
        "permission_denied",
        "quota_exceeded",
    }
    
    def __init__(self, llm: Any = None):
        """初始化错误修正器
        
        Args:
            llm: LLM 模型实例，用于生成修正
        """
        self._llm = llm
        self._error_history: list[ErrorCorrectionHistory] = []
        
        # 从配置加载参数
        self._load_config()
    
    def _load_config(self) -> None:
        """从 YAML 配置加载参数"""
        try:
            config = get_config()
            error_config = config.get_error_corrector_config()
            
            self.max_retries: int = error_config.get(
                "max_retries", 
                self._DEFAULT_MAX_RETRIES
            )
            self.max_same_error_count: int = error_config.get(
                "max_same_error_count",
                self._DEFAULT_MAX_SAME_ERROR_COUNT
            )
            
            # 不可重试错误类型（从配置读取列表，转为 set）
            non_retryable_list = error_config.get(
                "non_retryable_errors",
                list(self._DEFAULT_NON_RETRYABLE_ERRORS)
            )
            self.non_retryable_errors: set[str] = set(non_retryable_list)
            
            logger.debug(
                f"ErrorCorrector 配置加载成功: "
                f"max_retries={self.max_retries}, "
                f"max_same_error_count={self.max_same_error_count}, "
                f"non_retryable_errors={self.non_retryable_errors}"
            )
            
        except Exception as e:
            logger.warning(f"加载配置失败，使用默认值: {e}")
            self.max_retries = self._DEFAULT_MAX_RETRIES
            self.max_same_error_count = self._DEFAULT_MAX_SAME_ERROR_COUNT
            self.non_retryable_errors = self._DEFAULT_NON_RETRYABLE_ERRORS.copy()
    
    # ═══════════════════════════════════════════════════════════════════════
    # 错误 Hash 计算
    # ═══════════════════════════════════════════════════════════════════════
    
    def _compute_error_hash(self, error_info: str) -> str:
        """计算错误信息的 hash，用于重复检测
        
        Args:
            error_info: 错误信息
            
        Returns:
            错误信息的 hash（16 字符）
        """
        normalized = self._normalize_error_message(error_info)
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def _normalize_error_message(self, error_info: str) -> str:
        """标准化错误信息，去除变化部分
        
        去除时间戳、具体数值等可能变化的内容，
        保留错误的核心特征用于重复检测。
        
        Args:
            error_info: 原始错误信息
            
        Returns:
            标准化后的错误信息
        """
        # 去除时间戳 (ISO 格式和常见格式)
        normalized = re.sub(
            r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?',
            '[TIMESTAMP]',
            error_info
        )
        # 去除可变数值（行号/位置/数量等独立数字），让同模板错误稳定归并。
        normalized = re.sub(r'\b\d+\b', 'N', normalized)
        # 去除 UUID
        normalized = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '[UUID]',
            normalized,
            flags=re.IGNORECASE
        )
        # 去除多余空白
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized.strip()
    
    # ═══════════════════════════════════════════════════════════════════════
    # 重试判断
    # ═══════════════════════════════════════════════════════════════════════
    
    def should_retry(
        self,
        error_info: str,
        error_type: str,
    ) -> tuple[bool, Optional[str]]:
        """判断是否应该重试
        
        防止交替错误绕过检测：
        - 除了检查单个错误的重复次数，还检查错误历史总长度
        - 即使 A→B→A→B 模式，总历史长度也会达到上限
        
        Args:
            error_info: 错误信息
            error_type: 错误类型
            
        Returns:
            (should_retry, abort_reason)
        """
        # 1. 检查是否为不可重试的错误类型
        if error_type.lower() in self.non_retryable_errors:
            return False, f"non_retryable_error: {error_type}"
        
        # 2. 检查错误历史总长度（防止交替错误绕过）
        # 例如：A→B→A→B 模式，每个错误只出现 2 次，但总共 4 次
        if len(self._error_history) >= self.max_retries:
            return False, "total_error_history_exceeded"
        
        # 3. 检查是否为重复错误
        error_hash = self._compute_error_hash(error_info)
        same_error_count = sum(
            1 for h in self._error_history
            if h.error_hash == error_hash
        )
        if same_error_count >= self.max_same_error_count:
            return False, "duplicate_error_detected"
        
        return True, None
    
    # ═══════════════════════════════════════════════════════════════════════
    # 修正逻辑
    # ═══════════════════════════════════════════════════════════════════════
    
    async def correct(
        self,
        question: str,
        previous_output: SemanticOutput,
        error_info: str,
        error_type: str,
        context: Optional[dict] = None,
    ) -> CorrectionResult:
        """基于错误反馈修正
        
        Args:
            question: 原始用户问题
            previous_output: 之前的语义输出
            error_info: 错误信息
            error_type: 错误类型
            context: 额外上下文（如字段列表、数据模型等）
            
        Returns:
            CorrectionResult 包含修正结果
        """
        # 1. 检查是否应该重试
        should_retry, abort_reason = self.should_retry(error_info, error_type)
        
        if not should_retry:
            return CorrectionResult(
                corrected_output=None,
                thinking=f"修正终止: {abort_reason}",
                should_continue=False,
                abort_reason=abort_reason,
            )
        
        # 2. 记录本次错误
        error_hash = self._compute_error_hash(error_info)
        attempt_number = len(self._error_history) + 1
        
        self._error_history.append(ErrorCorrectionHistory(
            error_type=error_type,
            error_hash=error_hash,
            attempt_number=attempt_number,
            correction_applied="",  # 稍后更新
            timestamp=datetime.now(),
        ))
        
        # 3. 调用 LLM 进行修正
        try:
            corrected_output, thinking = await self._llm_correct(
                question=question,
                previous_output=previous_output,
                error_info=error_info,
                error_type=error_type,
                context=context,
            )
            
            # 更新修正记录
            self._error_history[-1].correction_applied = thinking[:100] if thinking else ""
            
            return CorrectionResult(
                corrected_output=corrected_output,
                thinking=thinking,
                should_continue=True,
                abort_reason=None,
            )
            
        except Exception as e:
            logger.error(f"LLM 修正失败: {e}")
            # LLM 调用失败
            return CorrectionResult(
                corrected_output=None,
                thinking=f"LLM 修正失败: {str(e)}",
                should_continue=False,
                abort_reason=f"llm_error: {str(e)}",
            )
    
    async def _llm_correct(
        self,
        question: str,
        previous_output: SemanticOutput,
        error_info: str,
        error_type: str,
        context: Optional[dict] = None,
    ) -> tuple[Optional[SemanticOutput], str]:
        """调用 LLM 进行修正
        
        Args:
            question: 原始用户问题
            previous_output: 之前的语义输出
            error_info: 错误信息
            error_type: 错误类型
            context: 额外上下文
            
        Returns:
            (corrected_output, thinking)
        """
        if self._llm is None:
            # 无 LLM，返回原输出（用于测试）
            return previous_output, "No LLM configured, returning original output"
        
        # 构建修正 Prompt（使用独立的 prompt 模块）
        user_prompt = build_user_prompt(
            question=question,
            previous_output=previous_output.model_dump_json(indent=2),
            error_type=error_type,
            error_info=error_info,
            context=context,
        )
        
        # 构建消息
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]
        
        # 调用 LLM
        result, thinking = await stream_llm_structured(
            llm=self._llm,
            messages=messages,
            output_model=SemanticOutput,
            return_thinking=True,
        )
        
        if not thinking:
            thinking = f"基于错误 '{error_type}' 进行修正"
        return result, thinking
    
    # ═══════════════════════════════════════════════════════════════════════
    # 状态管理
    # ═══════════════════════════════════════════════════════════════════════
    
    def reset_history(self) -> None:
        """重置错误历史
        
        在新的查询开始时调用，清除之前的错误记录。
        """
        self._error_history.clear()

    def restore_history(self, history: list[dict]) -> None:
        """从序列化数据恢复错误历史
        
        在节点调用间恢复之前的错误状态，替代直接访问 _error_history。
        
        Args:
            history: ErrorCorrectionHistory 的字典列表（来自 state 序列化）
        """
        self._error_history.clear()
        for h in history:
            self._error_history.append(
                ErrorCorrectionHistory.model_validate(h)
            )
    
    @property
    def error_history(self) -> list[ErrorCorrectionHistory]:
        """获取错误历史（只读）"""
        return list(self._error_history)
    
    @property
    def retry_count(self) -> int:
        """获取当前重试次数"""
        return len(self._error_history)
    
    @property
    def correction_abort_reason(self) -> Optional[str]:
        """获取修正终止原因（如果已终止）"""
        if len(self._error_history) >= self.max_retries:
            return "total_error_history_exceeded"
        
        # 检查重复错误
        hash_counts: dict[str, int] = {}
        for h in self._error_history:
            hash_counts[h.error_hash] = hash_counts.get(h.error_hash, 0) + 1
            if hash_counts[h.error_hash] >= self.max_same_error_count:
                return "duplicate_error_detected"
        
        return None

__all__ = [
    "ErrorCorrector",
]
