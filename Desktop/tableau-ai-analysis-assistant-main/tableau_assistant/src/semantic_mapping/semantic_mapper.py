"""
Semantic Mapper - 语义映射器 (RAG+LLM)

使用向量检索 + LLM 语义判断实现智能字段映射。
"""
import json
import logging
from typing import Dict, List, Optional, Tuple
from langchain.schema import Document
from langchain.chat_models.base import BaseChatModel
from tableau_assistant.src.models.metadata import Metadata
from tableau_assistant.src.semantic_mapping.field_indexer import FieldIndexer
from tableau_assistant.src.semantic_mapping.embeddings_provider import EmbeddingsProvider

logger = logging.getLogger(__name__)


class SemanticMapper:
    """
    语义映射器 - RAG+LLM 混合模型
    
    工作流程：
    1. 向量检索：从 FAISS 检索 Top-K 候选字段
    2. 过滤：过滤低相似度的候选
    3. LLM 判断：使用 LLM 进行语义判断
    4. 返回结果：最佳匹配 + 置信度 + 推理
    """
    
    def __init__(
        self,
        metadata: Metadata,
        llm: BaseChatModel,
        embeddings_provider: Optional[EmbeddingsProvider] = None
    ):
        """
        初始化 Semantic Mapper
        
        Args:
            metadata: Metadata 对象
            llm: LLM 实例
            embeddings_provider: Embeddings Provider（可选，默认自动创建）
        """
        self.metadata = metadata
        self.llm = llm
        
        # 创建 Embeddings Provider
        if embeddings_provider is None:
            embeddings_provider = EmbeddingsProvider()
        self.embeddings_provider = embeddings_provider
        
        # 创建 Field Indexer
        self.field_indexer = FieldIndexer(metadata, embeddings_provider)
        
        # 构建索引
        self.field_indexer.build_index()
        
        # 获取 Vector Store Manager
        self.vector_store_manager = self.field_indexer.get_vector_store_manager()
    
    def map_field(
        self,
        business_term: str,
        question_context: Optional[str] = None,
        top_k: int = 5,
        threshold: float = 0.3,
        use_llm: bool = True
    ) -> Dict:
        """
        映射业务术语到技术字段
        
        Args:
            business_term: 业务术语（如"销售额"）
            question_context: 问题上下文（可选，用于 LLM 判断）
            top_k: 检索的候选数量
            threshold: 相似度阈值（0-1，FAISS 使用距离，越小越相似）
            use_llm: 是否使用 LLM 进行语义判断
        
        Returns:
            映射结果字典 {
                "matched_field": str,  # 匹配的字段名
                "confidence": float,  # 置信度
                "reasoning": str,  # 推理过程
                "alternatives": List[Dict]  # 备选字段
            }
        """
        logger.info(f"开始字段映射: '{business_term}'")
        
        # 第1步：向量检索
        candidates = self._vector_search(business_term, top_k)
        
        if not candidates:
            logger.warning(f"未找到匹配的字段: '{business_term}'")
            return {
                "matched_field": None,
                "confidence": 0.0,
                "reasoning": "未找到匹配的字段",
                "alternatives": []
            }
        
        # 第2步：过滤低相似度
        filtered_candidates = self._filter_candidates(candidates, threshold)
        
        if not filtered_candidates:
            logger.warning(f"所有候选字段相似度过低: '{business_term}'")
            return {
                "matched_field": None,
                "confidence": 0.0,
                "reasoning": f"所有候选字段相似度低于阈值 {threshold}",
                "alternatives": self._format_alternatives(candidates[:3])
            }
        
        # 第3步：LLM 语义判断（可选）
        if use_llm and len(filtered_candidates) > 1:
            result = self._llm_judge(
                business_term,
                question_context or "",
                filtered_candidates
            )
        else:
            # 直接使用最高分候选
            best_candidate = filtered_candidates[0]
            result = {
                "matched_field": best_candidate[0].metadata["field_caption"],
                "confidence": self._score_to_confidence(best_candidate[1]),
                "reasoning": f"向量检索最高分: {best_candidate[1]:.3f}",
                "alternatives": self._format_alternatives(filtered_candidates[1:3])
            }
        
        logger.info(
            f"字段映射完成: '{business_term}' -> '{result['matched_field']}' "
            f"(置信度: {result['confidence']:.2f})"
        )
        
        return result
    
    def _vector_search(
        self,
        query: str,
        k: int
    ) -> List[Tuple[Document, float]]:
        """
        向量检索
        
        Args:
            query: 查询文本
            k: 返回数量
        
        Returns:
            (Document, score) 列表
        """
        logger.debug(f"执行向量检索: query='{query}', k={k}")
        
        results = self.vector_store_manager.similarity_search(
            query=query,
            k=k
        )
        
        logger.debug(f"检索到 {len(results)} 个候选字段")
        
        return results
    
    def _filter_candidates(
        self,
        candidates: List[Tuple[Document, float]],
        threshold: float
    ) -> List[Tuple[Document, float]]:
        """
        过滤低相似度候选
        
        注意：FAISS 返回的是距离（越小越相似），需要转换
        
        Args:
            candidates: 候选列表
            threshold: 阈值
        
        Returns:
            过滤后的候选列表
        """
        # FAISS 使用 L2 距离，需要根据实际情况调整阈值
        # 这里我们使用一个宽松的策略：保留距离较小的候选
        filtered = []
        
        for doc, score in candidates:
            # 将距离转换为相似度（简单的反比例）
            # 注意：这个转换可能需要根据实际效果调整
            similarity = 1.0 / (1.0 + score)
            
            if similarity >= threshold:
                filtered.append((doc, score))
        
        logger.debug(f"过滤后剩余 {len(filtered)} 个候选")
        
        return filtered
    
    def _llm_judge(
        self,
        business_term: str,
        question_context: str,
        candidates: List[Tuple[Document, float]]
    ) -> Dict:
        """
        LLM 语义判断
        
        Args:
            business_term: 业务术语
            question_context: 问题上下文
            candidates: 候选列表
        
        Returns:
            判断结果
        """
        logger.debug("使用 LLM 进行语义判断")
        
        # 构建候选字段描述
        candidates_text = self._format_candidates_for_llm(candidates)
        
        # 构建 Prompt
        prompt = f"""你是一个数据字段映射专家。请根据用户问题和业务术语，从候选字段中选择最匹配的字段。

用户问题：{question_context}
业务术语：{business_term}

候选字段：
{candidates_text}

请选择最匹配的字段，并返回 JSON 格式（不要包含markdown代码块标记）：
{{
    "matched_field": "字段显示名",
    "confidence": 0.95,
    "reasoning": "选择理由"
}}

要求：
1. matched_field 必须是候选字段中的 field_caption
2. confidence 是 0-1 之间的数字
3. reasoning 简要说明选择理由
"""
        
        try:
            # 调用 LLM
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # 移除可能的 markdown 代码块标记
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            # 解析 JSON
            result = json.loads(content)
            
            # 添加备选字段
            result["alternatives"] = self._format_alternatives(candidates[1:3])
            
            return result
            
        except Exception as e:
            logger.error(f"LLM 判断失败: {e}")
            
            # 回退到最高分候选
            best_candidate = candidates[0]
            return {
                "matched_field": best_candidate[0].metadata["field_caption"],
                "confidence": self._score_to_confidence(best_candidate[1]),
                "reasoning": f"LLM 判断失败，使用向量检索结果",
                "alternatives": self._format_alternatives(candidates[1:3])
            }
    
    def _format_candidates_for_llm(
        self,
        candidates: List[Tuple[Document, float]]
    ) -> str:
        """格式化候选字段用于 LLM"""
        lines = []
        
        for i, (doc, score) in enumerate(candidates, 1):
            meta = doc.metadata
            similarity = self._score_to_confidence(score)
            
            line = (
                f"{i}. {meta['field_caption']} "
                f"({meta['role']}, {meta['data_type']}) "
                f"- 相似度: {similarity:.2f}"
            )
            
            # 添加类别（如果有）
            if meta.get('category'):
                line += f" - 类别: {meta['category']}"
            
            # 添加描述（如果有）
            if meta.get('description'):
                line += f" - 描述: {meta['description']}"
            
            lines.append(line)
        
        return "\n".join(lines)
    
    def _format_alternatives(
        self,
        candidates: List[Tuple[Document, float]]
    ) -> List[Dict]:
        """格式化备选字段"""
        alternatives = []
        
        for doc, score in candidates:
            alternatives.append({
                "field": doc.metadata["field_caption"],
                "score": self._score_to_confidence(score),
                "role": doc.metadata["role"],
                "data_type": doc.metadata["data_type"]
            })
        
        return alternatives
    
    def _score_to_confidence(self, score: float) -> float:
        """
        将 FAISS 距离分数转换为置信度
        
        FAISS 返回 L2 距离，越小越相似
        这里使用简单的反比例转换
        
        Args:
            score: FAISS 距离分数
        
        Returns:
            置信度 (0-1)
        """
        # 简单的转换公式，可以根据实际效果调整
        confidence = 1.0 / (1.0 + score)
        return min(confidence, 1.0)


# ============= 导出 =============

__all__ = ["SemanticMapper"]
