# -*- coding: utf-8 -*-
"""
SemanticChunker Component - 智能优先级分块器

基于设计文档 progressive-insight-analysis/design.md 实现：
- 智能优先级分块（URGENT/HIGH/MEDIUM/LOW/DEFERRED）
- 异常值优先分析
- 尾部数据保留（不丢弃）
- 语义感知分块

核心理念："先吃肉，再吃蔬菜，剩菜也要留着"
"""

import logging
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

from tableau_assistant.src.agents.insight.models import (
    PriorityChunk,
    TailDataSummary,
    ChunkPriority,
    DataChunk,
    SemanticGroup,
    DataInsightProfile,
    ColumnStats,
)
from .utils import to_dataframe

logger = logging.getLogger(__name__)


class SemanticChunker:
    """
    智能优先级分块器
    
    基于"AI 宝宝吃饭"理念：
    1. 异常值优先（URGENT）- 不好吃的或特别好吃的
    2. Top 数据（HIGH）- 肉
    3. 中间数据（MEDIUM）- 蔬菜
    4. 较低数据（LOW）- 汤
    5. 尾部数据（DEFERRED）- 剩菜（保留，不丢弃）
    """
    
    # 分块阈值
    TOP_THRESHOLD = 100      # Top 100 行
    MID_THRESHOLD = 500      # 101-500 行
    LOW_THRESHOLD = 1000     # 501-1000 行
    
    def __init__(
        self,
        dimension_hierarchy: Optional[Dict[str, Any]] = None,
        anomaly_detector: Optional[Any] = None,
    ):
        """
        初始化分块器
        
        Args:
            dimension_hierarchy: 维度层级信息
            anomaly_detector: 异常检测器（可选，用于检测异常值）
        """
        self._dimension_hierarchy = dimension_hierarchy or {}
        self._anomaly_detector = anomaly_detector
    
    def set_dimension_hierarchy(self, hierarchy: Dict[str, Any]):
        """设置维度层级信息"""
        self._dimension_hierarchy = hierarchy or {}
    
    def chunk_with_priority(
        self,
        data: Any,
        detected_anomalies: Optional[List[int]] = None,
    ) -> List[PriorityChunk]:
        """
        智能优先级分块
        
        核心思想（来自设计文档）：
        1. 数据已经排序（VizQL 查询结果）
        2. Top 数据最重要（肉）-> 优先分析
        3. 中间数据次要（蔬菜）-> 根据洞察决定
        4. 尾部数据保留（剩菜）-> AI 决定是否需要
        5. 异常值优先（不好吃的）-> 可能是问题也可能是宝藏
        
        Args:
            data: 输入数据（DataFrame 或 list of dicts）
            detected_anomalies: 已检测到的异常行索引列表
            
        Returns:
            按优先级排序的 PriorityChunk 列表
        """
        df = self._to_dataframe(data)
        
        if df.empty:
            return []
        
        chunks = []
        total_rows = len(df)
        column_names = df.columns.tolist()
        chunk_id = 0
        
        # 1. 异常值块（URGENT）- "不好吃的或者特别好吃的"
        if detected_anomalies and len(detected_anomalies) > 0:
            anomaly_indices = [i for i in detected_anomalies if i < total_rows]
            if anomaly_indices:
                anomaly_df = df.iloc[anomaly_indices]
                chunks.append(PriorityChunk(
                    chunk_id=chunk_id,
                    chunk_type="anomalies",
                    priority=ChunkPriority.URGENT,
                    data=anomaly_df.to_dict('records'),
                    row_count=len(anomaly_df),
                    column_names=column_names,
                    description="异常值数据（可能是问题也可能是宝藏）",
                    estimated_value="high",
                ))
                chunk_id += 1
                logger.info(f"Created anomalies chunk: {len(anomaly_df)} rows")
        
        # 2. 高优先级块（HIGH）- Top 100 行 - "肉"
        if total_rows > 0:
            top_end = min(self.TOP_THRESHOLD, total_rows)
            top_df = df.head(top_end)
            chunks.append(PriorityChunk(
                chunk_id=chunk_id,
                chunk_type="top_data",
                priority=ChunkPriority.HIGH,
                data=top_df.to_dict('records'),
                row_count=len(top_df),
                column_names=column_names,
                description=f"Top {top_end} 行（排名最高的数据）",
                estimated_value="high",
            ))
            chunk_id += 1
            logger.info(f"Created top_data chunk: {len(top_df)} rows")
        
        # 3. 中优先级块（MEDIUM）- 101-500 行 - "蔬菜"
        if total_rows > self.TOP_THRESHOLD:
            mid_start = self.TOP_THRESHOLD
            mid_end = min(self.MID_THRESHOLD, total_rows)
            mid_df = df.iloc[mid_start:mid_end]
            chunks.append(PriorityChunk(
                chunk_id=chunk_id,
                chunk_type="mid_data",
                priority=ChunkPriority.MEDIUM,
                data=mid_df.to_dict('records'),
                row_count=len(mid_df),
                column_names=column_names,
                description=f"第 {mid_start+1}-{mid_end} 行（中间层数据）",
                estimated_value="medium",
            ))
            chunk_id += 1
            logger.info(f"Created mid_data chunk: {len(mid_df)} rows")
        
        # 4. 低优先级块（LOW）- 501-1000 行 - "汤"
        if total_rows > self.MID_THRESHOLD:
            low_start = self.MID_THRESHOLD
            low_end = min(self.LOW_THRESHOLD, total_rows)
            low_df = df.iloc[low_start:low_end]
            chunks.append(PriorityChunk(
                chunk_id=chunk_id,
                chunk_type="low_data",
                priority=ChunkPriority.LOW,
                data=low_df.to_dict('records'),
                row_count=len(low_df),
                column_names=column_names,
                description=f"第 {low_start+1}-{low_end} 行（较低层数据）",
                estimated_value="low",
            ))
            chunk_id += 1
            logger.info(f"Created low_data chunk: {len(low_df)} rows")
        
        # 5. 尾部数据（DEFERRED）- 1000+ 行 - "剩菜"
        # 关键：不丢弃，保留完整数据和摘要，让 AI 决定
        if total_rows > self.LOW_THRESHOLD:
            tail_df = df.iloc[self.LOW_THRESHOLD:]
            tail_summary = self._create_tail_summary(tail_df, detected_anomalies)
            
            # 根据尾部是否有异常值调整估算价值
            estimated_value = "potential" if tail_summary.anomaly_count > 0 else "low"
            
            chunks.append(PriorityChunk(
                chunk_id=chunk_id,
                chunk_type="tail_data",
                priority=ChunkPriority.DEFERRED,
                data=[],  # 尾部数据不直接存储，使用摘要
                tail_summary=tail_summary,
                row_count=len(tail_df),
                column_names=column_names,
                description=f"第 {self.LOW_THRESHOLD+1}+ 行（尾部数据，{len(tail_df)} 行）",
                estimated_value=estimated_value,
            ))
            chunk_id += 1
            logger.info(f"Created tail_data chunk: {len(tail_df)} rows (summary)")
        
        # 按优先级排序
        chunks.sort(key=lambda x: x.priority)
        
        logger.info(f"Total chunks created: {len(chunks)}")
        return chunks
    
    def _create_tail_summary(
        self,
        tail_df: pd.DataFrame,
        detected_anomalies: Optional[List[int]] = None,
    ) -> TailDataSummary:
        """
        创建尾部数据摘要
        
        关键：即使是尾部数据，也可能有重要模式
        """
        total_rows = len(tail_df)
        
        # 采样数据（最多 100 行）
        sample_size = min(100, total_rows)
        if total_rows > sample_size:
            sample_df = tail_df.sample(sample_size, random_state=42)
        else:
            sample_df = tail_df
        
        # 统计信息
        statistics = {}
        for col in tail_df.columns:
            if pd.api.types.is_numeric_dtype(tail_df[col]):
                statistics[col] = {
                    "mean": float(tail_df[col].mean()) if not tail_df[col].isna().all() else None,
                    "median": float(tail_df[col].median()) if not tail_df[col].isna().all() else None,
                    "std": float(tail_df[col].std()) if not tail_df[col].isna().all() else None,
                    "min": float(tail_df[col].min()) if not tail_df[col].isna().all() else None,
                    "max": float(tail_df[col].max()) if not tail_df[col].isna().all() else None,
                }
        
        # 尾部异常值数量
        anomaly_count = 0
        if detected_anomalies:
            tail_start_idx = self.LOW_THRESHOLD
            anomaly_count = sum(1 for i in detected_anomalies if i >= tail_start_idx)
        
        # 模式检测（简化版）
        patterns = self._detect_patterns_summary(tail_df)
        
        return TailDataSummary(
            total_rows=total_rows,
            sample_data=sample_df.to_dict('records'),
            statistics=statistics,
            anomaly_count=anomaly_count,
            patterns=patterns,
        )
    
    def _detect_patterns_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测数据模式摘要
        
        即使是尾部数据，也可能有重要模式：
        - 长尾分布
        - 周期性模式
        - 聚类
        """
        patterns = {
            "distribution": {},
            "trends": {},
            "unique_values": {},
        }
        
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                # 分布特征
                values = df[col].dropna()
                if len(values) > 0:
                    skewness = float(values.skew()) if len(values) > 2 else 0
                    patterns["distribution"][col] = {
                        "skewness": skewness,
                        "is_long_tail": abs(skewness) > 1,
                    }
            else:
                # 分类列的唯一值
                unique_count = df[col].nunique()
                patterns["unique_values"][col] = unique_count
        
        return patterns
    
    def _to_dataframe(self, data: Any) -> pd.DataFrame:
        """转换各种数据格式为 DataFrame"""
        return to_dataframe(data)

    
    # ========== 新的智能分块策略（基于 Phase 1 分析结果）=========
    
    def chunk_by_strategy(
        self,
        data: Any,
        strategy: str,
        insight_profile: Optional[DataInsightProfile] = None,
        semantic_groups: Optional[List[SemanticGroup]] = None,
    ) -> List[PriorityChunk]:
        """
        根据推荐策略执行分块
        
        策略优先级：聚类 > 变点 > 帕累托 > 语义 > 统计 > 位置
        
        Args:
            data: 输入数据
            strategy: 分块策略
            insight_profile: Phase 1 分析结果
            semantic_groups: 语义分组（用于 by_semantic 策略）
            
        Returns:
            按优先级排序的 PriorityChunk 列表
        """
        df = self._to_dataframe(data)
        
        if df.empty:
            return []
        
        logger.info(f"执行分块策略: {strategy}, 数据量: {len(df)} 行")
        
        if strategy == "by_anomaly" and insight_profile and insight_profile.anomaly_indices:
            return self._chunk_by_anomaly(df, insight_profile.anomaly_indices)
        
        elif strategy == "by_change_point" and insight_profile and insight_profile.change_points:
            return self._chunk_by_change_point(df, insight_profile.change_points)
        
        elif strategy == "by_pareto" and insight_profile:
            return self._chunk_by_pareto(df, insight_profile.pareto_threshold)
        
        elif strategy == "by_semantic" and semantic_groups:
            return self._chunk_by_semantic(df, semantic_groups)
        
        elif strategy == "by_statistics" and insight_profile and insight_profile.statistics:
            return self._chunk_by_statistics(df, insight_profile.statistics, insight_profile.primary_measure)
        
        else:
            # 默认：按位置分块
            return self._chunk_by_position(df)
    
    def _chunk_by_anomaly(
        self,
        df: pd.DataFrame,
        anomaly_indices: List[int],
    ) -> List[PriorityChunk]:
        """按异常值分块 - 隔离异常值优先分析"""
        chunks = []
        column_names = df.columns.tolist()
        
        # Filter valid indices
        valid_anomaly_indices = [idx for idx in anomaly_indices if idx < len(df)]
        normal_indices = [i for i in range(len(df)) if i not in valid_anomaly_indices]
        
        chunk_id = 0
        
        # 1. Anomaly chunk (URGENT priority)
        if valid_anomaly_indices:
            anomaly_df = df.iloc[valid_anomaly_indices]
            chunks.append(PriorityChunk(
                chunk_id=chunk_id,
                chunk_type="anomalies",
                priority=ChunkPriority.URGENT,
                data=anomaly_df.to_dict('records'),
                row_count=len(anomaly_df),
                column_names=column_names,
                description=f"异常值数据 ({len(anomaly_df)} 行)",
                estimated_value="high",
            ))
            chunk_id += 1
        
        # 2. Normal data chunks (by position)
        if normal_indices:
            normal_df = df.iloc[normal_indices]
            total_normal = len(normal_df)
            
            # Top portion (HIGH)
            top_end = min(self.TOP_THRESHOLD, total_normal)
            if top_end > 0:
                top_df = normal_df.head(top_end)
                chunks.append(PriorityChunk(
                    chunk_id=chunk_id,
                    chunk_type="normal_top",
                    priority=ChunkPriority.HIGH,
                    data=top_df.to_dict('records'),
                    row_count=len(top_df),
                    column_names=column_names,
                    description=f"正常数据 Top {len(top_df)} 行",
                    estimated_value="high",
                ))
                chunk_id += 1
            
            # Remaining normal data (MEDIUM/LOW)
            if total_normal > self.TOP_THRESHOLD:
                remaining_df = normal_df.iloc[self.TOP_THRESHOLD:]
                chunks.append(PriorityChunk(
                    chunk_id=chunk_id,
                    chunk_type="normal_rest",
                    priority=ChunkPriority.MEDIUM,
                    data=remaining_df.to_dict('records'),
                    row_count=len(remaining_df),
                    column_names=column_names,
                    description=f"正常数据剩余 {len(remaining_df)} 行",
                    estimated_value="medium",
                ))
                chunk_id += 1
        
        chunks.sort(key=lambda x: x.priority)
        logger.info(f"异常值分块完成: {len(chunks)} 个块")
        return chunks
    
    def _chunk_by_change_point(
        self,
        df: pd.DataFrame,
        change_points: List[int],
    ) -> List[PriorityChunk]:
        """按变点分块"""
        chunks = []
        column_names = df.columns.tolist()
        
        points = [0] + sorted(change_points) + [len(df)]
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        primary_col = numeric_cols[0] if numeric_cols else None
        
        segment_changes = []
        for i in range(len(points) - 1):
            start_idx = points[i]
            end_idx = points[i + 1]
            segment_df = df.iloc[start_idx:end_idx]
            
            if primary_col and len(segment_df) > 1:
                change = abs(segment_df[primary_col].iloc[-1] - segment_df[primary_col].iloc[0])
            else:
                change = 0
            
            segment_changes.append((i, start_idx, end_idx, change, segment_df))
        
        segment_changes.sort(key=lambda x: x[3], reverse=True)
        
        for rank, (seg_id, start_idx, end_idx, change, segment_df) in enumerate(segment_changes):
            if rank == 0:
                priority = ChunkPriority.HIGH
                estimated_value = "high"
            elif rank < len(segment_changes) // 2:
                priority = ChunkPriority.MEDIUM
                estimated_value = "medium"
            else:
                priority = ChunkPriority.LOW
                estimated_value = "low"
            
            chunks.append(PriorityChunk(
                chunk_id=seg_id,
                chunk_type=f"segment_{seg_id}",
                priority=priority,
                data=segment_df.to_dict('records'),
                row_count=len(segment_df),
                column_names=column_names,
                description=f"时间段 {seg_id}: 第 {start_idx+1}-{end_idx} 行 (变化量: {change:.2f})",
                estimated_value=estimated_value,
            ))
        
        chunks.sort(key=lambda x: x.priority)
        logger.info(f"变点分块完成: {len(chunks)} 个块")
        return chunks
    
    def _chunk_by_pareto(
        self,
        df: pd.DataFrame,
        pareto_threshold: float,
    ) -> List[PriorityChunk]:
        """按帕累托分块（80/20 法则）"""
        chunks = []
        column_names = df.columns.tolist()
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        if len(numeric_cols) == 0:
            return self._chunk_by_position(df)
        
        primary_col = numeric_cols[0]
        df_sorted = df.sort_values(primary_col, ascending=False).reset_index(drop=True)
        
        total_rows = len(df_sorted)
        top_20_idx = max(1, int(total_rows * 0.2))
        mid_50_idx = max(top_20_idx + 1, int(total_rows * 0.5))
        
        top_df = df_sorted.head(top_20_idx)
        chunks.append(PriorityChunk(
            chunk_id=0,
            chunk_type="pareto_top_20",
            priority=ChunkPriority.HIGH,
            data=top_df.to_dict('records'),
            row_count=len(top_df),
            column_names=column_names,
            description=f"Top 20% ({len(top_df)} 行，贡献约 80% 价值)",
            estimated_value="high",
        ))
        
        if mid_50_idx > top_20_idx:
            mid_df = df_sorted.iloc[top_20_idx:mid_50_idx]
            chunks.append(PriorityChunk(
                chunk_id=1,
                chunk_type="pareto_mid_30",
                priority=ChunkPriority.MEDIUM,
                data=mid_df.to_dict('records'),
                row_count=len(mid_df),
                column_names=column_names,
                description=f"Mid 30% ({len(mid_df)} 行)",
                estimated_value="medium",
            ))
        
        if total_rows > mid_50_idx:
            bottom_df = df_sorted.iloc[mid_50_idx:]
            chunks.append(PriorityChunk(
                chunk_id=2,
                chunk_type="pareto_bottom_50",
                priority=ChunkPriority.LOW,
                data=bottom_df.to_dict('records'),
                row_count=len(bottom_df),
                column_names=column_names,
                description=f"Bottom 50% ({len(bottom_df)} 行)",
                estimated_value="low",
            ))
        
        logger.info(f"帕累托分块完成: {len(chunks)} 个块")
        return chunks
    
    def _chunk_by_semantic(
        self,
        df: pd.DataFrame,
        semantic_groups: List[SemanticGroup],
    ) -> List[PriorityChunk]:
        """按语义值分块"""
        chunks = []
        column_names = df.columns.tolist()
        
        group_col = None
        for group in semantic_groups:
            if group.type in ("time", "geography", "category"):
                for col in group.columns:
                    if col in df.columns:
                        unique_count = df[col].nunique()
                        if 3 <= unique_count <= 20:
                            group_col = col
                            break
                if group_col:
                    break
        
        if not group_col:
            logger.warning("未找到合适的语义分组列，回退到位置分块")
            return self._chunk_by_position(df)
        
        grouped = df.groupby(group_col)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        primary_col = numeric_cols[0] if numeric_cols else None
        
        group_stats = []
        for group_value, group_df in grouped:
            total_value = group_df[primary_col].sum() if primary_col else len(group_df)
            group_stats.append((group_value, group_df, total_value))
        
        group_stats.sort(key=lambda x: x[2], reverse=True)
        
        for i, (group_value, group_df, total_value) in enumerate(group_stats):
            if i < len(group_stats) * 0.2:
                priority = ChunkPriority.HIGH
                estimated_value = "high"
            elif i < len(group_stats) * 0.5:
                priority = ChunkPriority.MEDIUM
                estimated_value = "medium"
            else:
                priority = ChunkPriority.LOW
                estimated_value = "low"
            
            chunks.append(PriorityChunk(
                chunk_id=i,
                chunk_type=f"semantic_{group_col}",
                priority=priority,
                data=group_df.to_dict('records'),
                row_count=len(group_df),
                column_names=column_names,
                description=f"{group_col}={group_value} ({len(group_df)} 行)",
                estimated_value=estimated_value,
            ))
        
        chunks.sort(key=lambda x: x.priority)
        logger.info(f"语义分块完成: {len(chunks)} 个块, 分组列: {group_col}")
        return chunks
    
    def _chunk_by_statistics(
        self,
        df: pd.DataFrame,
        statistics: Dict[str, ColumnStats],
        primary_measure: Optional[str] = None,
    ) -> List[PriorityChunk]:
        """按统计特征分块（Q25/Q75）"""
        chunks = []
        column_names = df.columns.tolist()
        
        if primary_measure and primary_measure in statistics:
            primary_col = primary_measure
        elif statistics:
            primary_col = list(statistics.keys())[0]
        else:
            return self._chunk_by_position(df)
        
        stats = statistics[primary_col]
        iqr = stats.q75 - stats.q25
        lower_bound = stats.q25 - 1.5 * iqr
        upper_bound = stats.q75 + 1.5 * iqr
        
        chunk_id = 0
        
        anomaly_mask = (df[primary_col] < lower_bound) | (df[primary_col] > upper_bound)
        if anomaly_mask.any():
            anomaly_df = df[anomaly_mask]
            chunks.append(PriorityChunk(
                chunk_id=chunk_id,
                chunk_type="anomalies",
                priority=ChunkPriority.URGENT,
                data=anomaly_df.to_dict('records'),
                row_count=len(anomaly_df),
                column_names=column_names,
                description=f"异常值 ({len(anomaly_df)} 行)",
                estimated_value="high",
            ))
            chunk_id += 1
        
        high_mask = (df[primary_col] > stats.q75) & ~anomaly_mask
        if high_mask.any():
            high_df = df[high_mask]
            chunks.append(PriorityChunk(
                chunk_id=chunk_id,
                chunk_type="high_value",
                priority=ChunkPriority.HIGH,
                data=high_df.to_dict('records'),
                row_count=len(high_df),
                column_names=column_names,
                description=f"高价值 (> Q75, {len(high_df)} 行)",
                estimated_value="high",
            ))
            chunk_id += 1
        
        mid_mask = (df[primary_col] >= stats.q25) & (df[primary_col] <= stats.q75)
        if mid_mask.any():
            mid_df = df[mid_mask]
            chunks.append(PriorityChunk(
                chunk_id=chunk_id,
                chunk_type="medium_value",
                priority=ChunkPriority.MEDIUM,
                data=mid_df.to_dict('records'),
                row_count=len(mid_df),
                column_names=column_names,
                description=f"中等价值 (Q25-Q75, {len(mid_df)} 行)",
                estimated_value="medium",
            ))
            chunk_id += 1
        
        low_mask = (df[primary_col] < stats.q25) & ~anomaly_mask
        if low_mask.any():
            low_df = df[low_mask]
            chunks.append(PriorityChunk(
                chunk_id=chunk_id,
                chunk_type="low_value",
                priority=ChunkPriority.LOW,
                data=low_df.to_dict('records'),
                row_count=len(low_df),
                column_names=column_names,
                description=f"低价值 (< Q25, {len(low_df)} 行)",
                estimated_value="low",
            ))
            chunk_id += 1
        
        chunks.sort(key=lambda x: x.priority)
        logger.info(f"统计分块完成: {len(chunks)} 个块")
        return chunks
    
    def _chunk_by_position(
        self,
        df: pd.DataFrame,
    ) -> List[PriorityChunk]:
        """按位置分块（最后手段）"""
        logger.info("使用位置分块策略")
        return self.chunk_with_priority(df.to_dict('records'))
    
    # ========== 兼容旧接口 ==========
    
    def chunk(
        self,
        data: Any,
        semantic_groups: Optional[List[SemanticGroup]] = None
    ) -> List[DataChunk]:
        """兼容旧接口的分块方法"""
        priority_chunks = self.chunk_with_priority(data)
        
        data_chunks = []
        for pc in priority_chunks:
            if pc.chunk_type == "tail_data" and pc.tail_summary:
                chunk_data = pc.tail_summary.sample_data
            else:
                chunk_data = pc.data
            
            data_chunks.append(DataChunk(
                data=chunk_data,
                chunk_id=pc.chunk_id,
                chunk_name=f"{pc.chunk_type} (priority={pc.priority})",
                row_count=pc.row_count,
                column_names=pc.column_names,
            ))
        
        return data_chunks
