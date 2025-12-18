# -*- coding: utf-8 -*-
"""
Replanner Agent

智能重规划 Agent，支持多问题并行执行（类 Tableau Pulse）。

Design Specification: insight-design.md
- 评估当前洞察的完成度
- 识别缺失的分析方面
- 基于 dimension_hierarchy 生成多个探索问题
- 为每个问题分配优先级
"""

import logging
import json
from typing import Dict, List, Any, Optional

from tableau_assistant.src.core.models import ReplanDecision, ExplorationQuestion, Insight
from tableau_assistant.src.agents.base import clean_json_output
from .prompt import REPLANNER_PROMPT

logger = logging.getLogger(__name__)


class ReplannerAgent:
    """
    智能重规划 Agent
    
    核心功能：
    1. 评估当前洞察的完成度
    2. 识别缺失的分析方面
    3. 生成多个探索问题（LLM 直接生成，不使用模板）
    4. 为每个问题分配优先级
    
    与 Middleware 集成：
    - 调用 write_todos 工具存储探索问题（由 TodoListMiddleware 提供）
    - 支持 HumanInTheLoopMiddleware 进行用户审核
    """
    
    def __init__(
        self,
        llm=None,
        max_replan_rounds: int = 3,
        max_questions_per_round: int = 3,
    ):
        """
        初始化 Replanner Agent
        
        Args:
            llm: LangChain LLM 实例
            max_replan_rounds: 最大重规划轮数
            max_questions_per_round: 每轮最多执行几个问题
        """
        self._llm = llm
        self.max_replan_rounds = max_replan_rounds
        self.max_questions_per_round = max_questions_per_round
    
    def _get_llm(self):
        """获取或创建 LLM 实例"""
        if self._llm is None:
            from tableau_assistant.src.infra.ai import get_llm
            self._llm = get_llm()
        return self._llm
    
    async def replan(
        self,
        original_question: str,
        insights: List[Dict[str, Any]],
        data_insight_profile: Optional[Dict[str, Any]] = None,
        dimension_hierarchy: Optional[Dict[str, Any]] = None,
        current_dimensions: Optional[List[str]] = None,
        current_round: int = 1,
        answered_questions: Optional[List[str]] = None,
    ) -> ReplanDecision:
        """
        执行重规划决策
        
        Args:
            original_question: 原始用户问题
            insights: 当前累积的洞察列表
            data_insight_profile: Phase 1 统计分析结果
            dimension_hierarchy: 维度层级信息
            current_dimensions: 当前已分析的维度
            current_round: 当前重规划轮数
            answered_questions: 已回答的问题列表（用于去重）
            
        Returns:
            ReplanDecision 包含是否重规划、探索问题等
        
        **Validates: Requirements 14.3, 14.4, 14.5**
        """
        # 检查是否达到最大轮数
        if current_round >= self.max_replan_rounds:
            logger.info(f"达到最大重规划轮数 ({self.max_replan_rounds})，停止重规划")
            return ReplanDecision(
                completeness_score=0.8,
                should_replan=False,
                reason=f"已达到最大重规划轮数（{self.max_replan_rounds}）",
                missing_aspects=[],
                exploration_questions=[],
                confidence=0.9,
            )
        
        # 检查是否有洞察
        if not insights:
            logger.warning("没有洞察结果，无法评估完成度")
            return ReplanDecision(
                completeness_score=0.0,
                should_replan=False,
                reason="没有洞察结果，无法评估完成度",
                missing_aspects=[],
                exploration_questions=[],
                confidence=0.5,
            )
        
        # 格式化洞察摘要
        insights_summary = self._format_insights_summary(insights)
        
        # 格式化数据洞察画像
        profile_str = self._format_data_insight_profile(data_insight_profile)
        
        # 格式化维度层级
        hierarchy_str = self._format_dimension_hierarchy(dimension_hierarchy)
        
        # 格式化当前维度
        dimensions_str = ", ".join(current_dimensions) if current_dimensions else "（无）"
        
        # 格式化已回答问题（用于去重）
        # **Validates: Requirements 14.3, 14.4**
        answered_str = self._format_answered_questions(answered_questions)
        
        try:
            # 使用 Prompt 格式化消息
            messages = REPLANNER_PROMPT.format_messages(
                original_question=original_question,
                insights_summary=insights_summary,
                data_insight_profile=profile_str,
                dimension_hierarchy=hierarchy_str,
                current_dimensions=dimensions_str,
                answered_questions=answered_str,
                current_round=current_round,
                max_rounds=self.max_replan_rounds,
            )
            
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            
            # 解析响应
            decision = self._parse_response(response.content)
            
            # 限制每轮问题数量
            if decision.exploration_questions:
                decision.exploration_questions = decision.get_top_questions(
                    self.max_questions_per_round
                )
            
            logger.info(
                f"Replanner 决策: should_replan={decision.should_replan}, "
                f"completeness={decision.completeness_score:.2f}, "
                f"questions={len(decision.exploration_questions)}"
            )
            
            return decision
            
        except Exception as e:
            logger.error(f"Replanner 执行失败: {e}")
            return ReplanDecision(
                completeness_score=0.5,
                should_replan=False,
                reason=f"重规划执行失败: {str(e)}",
                missing_aspects=[],
                exploration_questions=[],
                confidence=0.3,
            )
    
    def _format_insights_summary(self, insights: List[Insight]) -> str:
        """格式化洞察摘要
        
        Args:
            insights: Insight Pydantic 对象列表
        """
        if not insights:
            return "（无洞察）"
        
        lines = []
        for i, insight in enumerate(insights):
            # 使用 Pydantic 对象属性访问
            insight_type = insight.type
            title = insight.title
            description = insight.description or ""
            importance = insight.importance
            
            lines.append(
                f"{i+1}. [{insight_type}] {title} (重要性: {importance:.1f})\n"
                f"   {description}..."
            )
        
        return "\n".join(lines)
    
    def _format_data_insight_profile(self, profile: Optional[Dict[str, Any]]) -> str:
        """格式化数据洞察画像"""
        if not profile:
            return "（无统计分析结果）"
        
        lines = []
        
        # 分布信息
        dist_type = profile.get("distribution_type", "unknown")
        skewness = profile.get("skewness", 0)
        lines.append(f"- 分布类型: {dist_type} (偏度: {skewness:.2f})")
        
        # 帕累托信息
        pareto_ratio = profile.get("pareto_ratio", 0)
        lines.append(f"- 帕累托: Top 20% 贡献 {pareto_ratio:.1%}")
        
        # 异常信息
        anomaly_ratio = profile.get("anomaly_ratio", 0)
        anomaly_count = len(profile.get("anomaly_indices", []))
        lines.append(f"- 异常值: {anomaly_count} 个 ({anomaly_ratio:.1%})")
        
        # 聚类信息
        clusters = profile.get("clusters", [])
        if clusters:
            cluster_parts = []
            for i, c in enumerate(clusters):
                label = c.get('label') or f"聚类{c.get('cluster_id', i)}"
                size = c.get('size', 0)
                cluster_parts.append(f"{label}({size}行)")
            cluster_info = ", ".join(cluster_parts)
            lines.append(f"- 聚类: {len(clusters)} 个 ({cluster_info})")
        
        # 趋势信息
        trend = profile.get("trend")
        if trend:
            lines.append(f"- 趋势: {trend}")
        
        # 推荐策略
        strategy = profile.get("recommended_chunking_strategy", "unknown")
        lines.append(f"- 推荐分块策略: {strategy}")
        
        return "\n".join(lines)
    
    def _format_dimension_hierarchy(self, hierarchy: Optional[Dict[str, Any]]) -> str:
        """格式化维度层级信息"""
        if not hierarchy:
            return "（无维度层级信息）"
        
        lines = []
        for dim_name, attrs in hierarchy.items():
            if isinstance(attrs, dict):
                category = attrs.get("category", "other")
                level = attrs.get("level", 0)
                granularity = attrs.get("granularity", "unknown")
                parent = attrs.get("parent_dimension", "无")
                child = attrs.get("child_dimension", "无")
                
                lines.append(
                    f"- {dim_name}: {category} (level={level}, {granularity})\n"
                    f"  父维度: {parent}, 子维度: {child}"
                )
        
        return "\n".join(lines) if lines else "（无维度层级信息）"
    
    def _format_answered_questions(self, questions: Optional[List[str]]) -> str:
        """
        格式化已回答问题列表（用于去重）
        
        Args:
            questions: 已回答的问题列表
        
        Returns:
            格式化的字符串
        
        **Validates: Requirements 14.3, 14.4**
        """
        if not questions:
            return "（无已回答问题）"
        
        # 使用 trim_answered_questions 限制长度
        from tableau_assistant.src.infra.utils.conversation import trim_answered_questions
        trimmed = trim_answered_questions(questions)
        
        lines = []
        for i, q in enumerate(trimmed, 1):
            lines.append(f"{i}. {q}")
        
        if len(questions) > len(trimmed):
            lines.append(f"... 共 {len(questions)} 个问题，显示最近 {len(trimmed)} 个")
        
        return "\n".join(lines)
    
    def _parse_response(self, content: str) -> ReplanDecision:
        """解析 LLM 响应"""
        try:
            # 使用 clean_json_output 清理和修复 JSON
            cleaned_json = clean_json_output(content)
            data = json.loads(cleaned_json)
            
            # 解析探索问题
            exploration_questions = []
            for q_data in data.get("exploration_questions", []):
                try:
                    question = ExplorationQuestion(
                        question=q_data.get("question", ""),
                        exploration_type=q_data.get("exploration_type", "drill_down"),
                        target_dimension=q_data.get("target_dimension", ""),
                        filter=q_data.get("filter"),
                        priority=q_data.get("priority", 5),
                        reasoning=q_data.get("reasoning", ""),
                    )
                    exploration_questions.append(question)
                except Exception as e:
                    logger.warning(f"解析探索问题失败: {e}")
            
            return ReplanDecision(
                completeness_score=float(data.get("completeness_score", 0.5)),
                should_replan=bool(data.get("should_replan", False)),
                reason=data.get("reason", ""),
                missing_aspects=data.get("missing_aspects", []),
                exploration_questions=exploration_questions,
                parallel_execution=data.get("parallel_execution", True),
                max_questions_per_round=data.get("max_questions_per_round", 3),
                confidence=float(data.get("confidence", 0.8)),
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 解析失败: {e}, 原始内容: {content[:200]}...")
            return self._default_decision()
        except Exception as e:
            logger.error(f"响应解析失败: {e}")
            return self._default_decision()
    
    def _default_decision(self) -> ReplanDecision:
        """返回默认决策"""
        return ReplanDecision(
            completeness_score=0.5,
            should_replan=False,
            reason="无法解析 LLM 响应，使用默认决策",
            missing_aspects=[],
            exploration_questions=[],
            confidence=0.3,
        )


__all__ = ["ReplannerAgent"]
