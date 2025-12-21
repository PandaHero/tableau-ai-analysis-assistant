# Tableau Assistant 改进实施指南

> 基于业界主流项目深度分析的具体实施方案
>
> **创建日期**: 2024-12-21
> **优先级**: P0 > P1 > P2

---

## 目录

1. [实施概览](#1-实施概览)
2. [P0: 训练数据管理系统](#2-p0-训练数据管理系统)
3. [P0: 自我纠错机制](#3-p0-自我纠错机制)
4. [P1: 动态 Few-Shot](#4-p1-动态-few-shot)
5. [P1: 置信度评分](#5-p1-置信度评分)
6. [P2: 增强 Schema Linking](#6-p2-增强-schema-linking)
7. [集成测试计划](#7-集成测试计划)

---

## 1. 实施概览

### 1.1 改进优先级矩阵

| 改进项 | 优先级 | 预期收益 | 工作量 | 依赖 |
|--------|--------|---------|--------|------|
| 训练数据管理 | P0 | +15% 准确性 | 5天 | 无 |
| 自我纠错机制 | P0 | +10% 准确性 | 4天 | 无 |
| 动态 Few-Shot | P1 | +10% 准确性 | 3天 | 训练数据 |
| 置信度评分 | P1 | 用户体验提升 | 2天 | 无 |
| 增强 Schema Linking | P2 | +5% 准确性 | 5天 | 无 |

### 1.2 目录结构规划

```
tableau_assistant/src/
├── training/                    # 新增: 训练数据管理
│   ├── __init__.py
│   ├── models.py               # GoldenQuery, UserFeedback 模型
│   ├── store.py                # TrainingDataStore
│   └── feedback_api.py         # 反馈收集 API
├── agents/
│   └── self_correction/        # 新增: 自我纠错
│       ├── __init__.py
│       ├── checker.py          # QueryChecker
│       └── corrector.py        # SelfCorrector
├── evaluation/                  # 新增: 评估模块
│   ├── __init__.py
│   └── confidence.py           # ConfidenceCalculator
└── rag/
    └── schema_linker.py        # 新增: 增强 Schema Linking
```


---

## 2. P0: 训练数据管理系统

### 2.1 核心设计

借鉴 Vanna.ai 和 Dataherald 的训练数据管理模式：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    训练数据管理系统架构                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │ GoldenQuery  │    │ UserFeedback │    │  BusinessDoc │               │
│  │   Store      │    │   Collector  │    │    Store     │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│         │                   │                   │                        │
│         └───────────────────┼───────────────────┘                        │
│                             ▼                                            │
│                    ┌──────────────┐                                      │
│                    │ FAISS Index  │                                      │
│                    │ (向量检索)   │                                      │
│                    └──────────────┘                                      │
│                             │                                            │
│                             ▼                                            │
│                    ┌──────────────┐                                      │
│                    │ Dynamic      │                                      │
│                    │ Few-Shot     │                                      │
│                    └──────────────┘                                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据模型定义

```python
# tableau_assistant/src/training/models.py

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import hashlib


def generate_id() -> str:
    """生成唯一 ID"""
    return hashlib.md5(f"{datetime.now().isoformat()}".encode()).hexdigest()[:12]


class GoldenQuery(BaseModel):
    """
    Golden Query - 经过验证的问题-查询对
    
    来源：
    1. 手动添加（管理员）
    2. 用户反馈自动学习
    3. 批量导入
    """
    id: str = Field(default_factory=generate_id)
    question: str = Field(..., description="用户问题")
    vizql_query: Dict[str, Any] = Field(..., description="VizQL 查询")
    datasource_luid: str = Field(..., description="数据源 LUID")
    
    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)
    created_by: str = Field(default="system")
    verified: bool = Field(default=False, description="是否经过人工验证")
    
    # 使用统计
    success_count: int = Field(default=0, description="成功使用次数")
    failure_count: int = Field(default=0, description="失败次数")
    last_used_at: Optional[datetime] = None
    
    # 语义信息（用于检索增强）
    semantic_query: Optional[Dict[str, Any]] = Field(
        default=None, description="Step1 输出的语义查询"
    )
    mapped_fields: Optional[List[str]] = Field(
        default=None, description="映射的字段列表"
    )
    tags: List[str] = Field(default_factory=list, description="标签")
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


class UserFeedback(BaseModel):
    """
    用户反馈
    
    用于收集用户对生成查询的评价，支持自动学习
    """
    id: str = Field(default_factory=generate_id)
    question: str = Field(..., description="用户问题")
    generated_query: Dict[str, Any] = Field(..., description="生成的查询")
    datasource_luid: str = Field(..., description="数据源 LUID")
    
    # 反馈内容
    is_correct: bool = Field(..., description="查询是否正确")
    correction: Optional[Dict[str, Any]] = Field(
        default=None, description="用户修正后的查询"
    )
    feedback_text: Optional[str] = Field(
        default=None, description="用户反馈文本"
    )
    rating: Optional[int] = Field(
        default=None, ge=1, le=5, description="评分 1-5"
    )
    
    # 元数据
    created_at: datetime = Field(default_factory=datetime.now)
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class BusinessDocument(BaseModel):
    """
    业务文档
    
    存储业务术语、规则、示例等
    """
    id: str = Field(default_factory=generate_id)
    title: str
    content: str
    datasource_luid: str
    category: str = Field(
        ..., description="文档类型: glossary/rule/example/faq"
    )
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
```

### 2.3 存储实现

```python
# tableau_assistant/src/training/store.py

import logging
from typing import List, Optional, Tuple
import numpy as np
import faiss

from langgraph.store.base import BaseStore
from .models import GoldenQuery, UserFeedback, BusinessDocument

logger = logging.getLogger(__name__)


class TrainingDataStore:
    """
    训练数据存储
    
    基于 LangGraph SqliteStore + FAISS 向量索引
    """
    
    NAMESPACE_GOLDEN = "golden_queries"
    NAMESPACE_FEEDBACK = "user_feedback"
    NAMESPACE_DOCS = "business_docs"
    
    def __init__(
        self,
        store: BaseStore,
        embedding_provider,
        similarity_threshold: float = 0.85,
    ):
        """
        初始化
        
        Args:
            store: LangGraph Store 实例
            embedding_provider: Embedding 提供者
            similarity_threshold: 相似度阈值（用于去重）
        """
        self.store = store
        self.embedding_provider = embedding_provider
        self.similarity_threshold = similarity_threshold
        
        # FAISS 索引（按 datasource 分区）
        self._indexes: Dict[str, faiss.Index] = {}
        self._index_to_id: Dict[Tuple[str, int], str] = {}
        self._id_to_index: Dict[Tuple[str, str], int] = {}
    
    # ==================== Golden Query 管理 ====================
    
    async def add_golden_query(
        self,
        query: GoldenQuery,
        check_duplicate: bool = True
    ) -> str:
        """添加 Golden Query"""
        # 1. 检查重复
        if check_duplicate:
            similar = await self.get_similar_queries(
                query.question,
                query.datasource_luid,
                top_k=1
            )
            if similar and similar[0][1] > self.similarity_threshold:
                existing = similar[0][0]
                logger.info(f"Similar query exists: {existing.id}, updating...")
                existing.success_count += 1
                await self._update_golden_query(existing)
                return existing.id
        
        # 2. 生成 Embedding
        embedding = await self.embedding_provider.aembed_query(query.question)
        
        # 3. 存储到 LangGraph Store
        namespace = (self.NAMESPACE_GOLDEN, query.datasource_luid)
        await self.store.aput(
            namespace=namespace,
            key=query.id,
            value=query.model_dump()
        )
        
        # 4. 更新 FAISS 索引
        await self._add_to_index(query.datasource_luid, query.id, embedding)
        
        logger.info(f"Added golden query: {query.id}")
        return query.id
    
    async def get_similar_queries(
        self,
        question: str,
        datasource_luid: str,
        top_k: int = 5,
        min_score: float = 0.3
    ) -> List[Tuple[GoldenQuery, float]]:
        """
        检索相似的 Golden Query
        
        用于动态 Few-Shot
        """
        # 1. 生成问题 Embedding
        query_embedding = await self.embedding_provider.aembed_query(question)
        
        # 2. FAISS 检索
        index = self._get_index(datasource_luid)
        if index is None or index.ntotal == 0:
            return []
        
        query_vector = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query_vector)
        
        k = min(top_k * 2, index.ntotal)
        scores, indices = index.search(query_vector, k)
        
        # 3. 获取完整记录
        results = []
        namespace = (self.NAMESPACE_GOLDEN, datasource_luid)
        
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1 or score < min_score:
                continue
            
            query_id = self._index_to_id.get((datasource_luid, int(idx)))
            if not query_id:
                continue
            
            item = await self.store.aget(namespace=namespace, key=query_id)
            if item:
                query = GoldenQuery(**item.value)
                results.append((query, float(score)))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    # ==================== 用户反馈管理 ====================
    
    async def record_feedback(
        self,
        feedback: UserFeedback,
        auto_learn: bool = True
    ) -> str:
        """
        记录用户反馈
        
        Args:
            feedback: 反馈对象
            auto_learn: 是否自动学习（正确反馈加入 Golden Query）
        """
        # 1. 存储反馈
        namespace = (self.NAMESPACE_FEEDBACK, feedback.datasource_luid)
        await self.store.aput(
            namespace=namespace,
            key=feedback.id,
            value=feedback.model_dump()
        )
        
        # 2. 自动学习
        if auto_learn and feedback.is_correct:
            golden = GoldenQuery(
                question=feedback.question,
                vizql_query=feedback.generated_query,
                datasource_luid=feedback.datasource_luid,
                created_by="user_feedback",
                verified=False,  # 需要人工验证
            )
            await self.add_golden_query(golden)
            logger.info(f"Auto-learned from feedback: {golden.id}")
        
        return feedback.id
    
    # ==================== 索引管理 ====================
    
    def _get_index(self, datasource_luid: str) -> Optional[faiss.Index]:
        """获取 FAISS 索引"""
        return self._indexes.get(datasource_luid)
    
    def _get_or_create_index(self, datasource_luid: str) -> faiss.Index:
        """获取或创建 FAISS 索引"""
        if datasource_luid not in self._indexes:
            dimension = self.embedding_provider.dimension
            self._indexes[datasource_luid] = faiss.IndexFlatIP(dimension)
        return self._indexes[datasource_luid]
    
    async def _add_to_index(
        self,
        datasource_luid: str,
        query_id: str,
        embedding: List[float]
    ):
        """添加到 FAISS 索引"""
        index = self._get_or_create_index(datasource_luid)
        
        vector = np.array([embedding], dtype=np.float32)
        faiss.normalize_L2(vector)
        
        idx = index.ntotal
        index.add(vector)
        
        self._index_to_id[(datasource_luid, idx)] = query_id
        self._id_to_index[(datasource_luid, query_id)] = idx
    
    async def rebuild_index(self, datasource_luid: str):
        """重建索引"""
        # 清空现有索引
        if datasource_luid in self._indexes:
            del self._indexes[datasource_luid]
        
        # 重新加载所有 Golden Query
        namespace = (self.NAMESPACE_GOLDEN, datasource_luid)
        items = await self.store.asearch(namespace=namespace)
        
        for item in items:
            query = GoldenQuery(**item.value)
            embedding = await self.embedding_provider.aembed_query(query.question)
            await self._add_to_index(datasource_luid, query.id, embedding)
        
        logger.info(f"Rebuilt index for {datasource_luid}: {len(items)} queries")
```


---

## 3. P0: 自我纠错机制

### 3.1 核心设计

借鉴 LangChain SQL Agent 的 QueryChecker 和 DIN-SQL 的 Self-Correction：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    自我纠错机制架构                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  VizQL Query ──▶ [QueryChecker] ──▶ 执行前检查                          │
│                        │                                                 │
│                        ├── 静态检查（字段存在性、类型匹配）              │
│                        └── LLM 检查（语义正确性）                        │
│                        │                                                 │
│                        ▼                                                 │
│                   通过? ──No──▶ 自动修复 ──▶ 重新检查                   │
│                        │                                                 │
│                       Yes                                                │
│                        ▼                                                 │
│                   [Execute] ──▶ 执行查询                                │
│                        │                                                 │
│                   成功? ──No──▶ [SelfCorrector] ──▶ 错误分类            │
│                        │              │                                  │
│                       Yes             ├── 字段错误 ──▶ RAG 修复         │
│                        │              ├── 聚合错误 ──▶ LLM 修复         │
│                        ▼              └── 其他错误 ──▶ 通用修复         │
│                   返回结果                                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 QueryChecker 实现

```python
# tableau_assistant/src/agents/self_correction/checker.py

import logging
from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class CheckResult(BaseModel):
    """检查结果"""
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    fixed_query: Optional[Dict[str, Any]] = None
    auto_fixed: bool = False


class QueryChecker:
    """
    查询检查器 - 执行前检查
    
    功能：
    1. 静态检查（不需要 LLM）
    2. LLM 语义检查
    3. 自动修复
    """
    
    COMMON_MISTAKES = """
检查以下常见错误：
1. 字段名是否存在于数据模型中
2. 度量字段是否有正确的聚合方式
3. 过滤器值是否有效
4. 日期格式是否正确
5. 计算类型是否支持
6. 排序字段是否在查询字段中
"""
    
    def __init__(self, llm, field_mapper=None):
        """
        初始化
        
        Args:
            llm: LLM 实例
            field_mapper: 字段映射器（用于修复字段错误）
        """
        self.llm = llm
        self.field_mapper = field_mapper
    
    async def check(
        self,
        query: Dict[str, Any],
        data_model,
        auto_fix: bool = True
    ) -> CheckResult:
        """
        检查查询
        
        Args:
            query: VizQL 查询
            data_model: 数据模型
            auto_fix: 是否自动修复
            
        Returns:
            CheckResult
        """
        errors = []
        warnings = []
        
        # 1. 静态检查
        static_errors, static_warnings = self._static_check(query, data_model)
        errors.extend(static_errors)
        warnings.extend(static_warnings)
        
        # 2. 如果有静态错误且允许自动修复
        if errors and auto_fix:
            fixed_query = await self._auto_fix(query, errors, data_model)
            if fixed_query:
                # 重新检查修复后的查询
                new_errors, new_warnings = self._static_check(fixed_query, data_model)
                if not new_errors:
                    return CheckResult(
                        is_valid=True,
                        errors=[],
                        warnings=warnings + new_warnings,
                        fixed_query=fixed_query,
                        auto_fixed=True
                    )
        
        # 3. LLM 语义检查（仅当静态检查通过时）
        if not errors:
            llm_errors, llm_warnings = await self._llm_check(query, data_model)
            errors.extend(llm_errors)
            warnings.extend(llm_warnings)
        
        return CheckResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _static_check(
        self,
        query: Dict[str, Any],
        data_model
    ) -> Tuple[List[str], List[str]]:
        """静态检查"""
        errors = []
        warnings = []
        
        # 获取数据模型中的所有字段
        valid_fields = set()
        if hasattr(data_model, 'fields'):
            for field in data_model.fields:
                valid_fields.add(field.fieldCaption)
                valid_fields.add(field.name)
        
        # 检查查询字段
        for field in query.get("fields", []):
            field_name = field.get("fieldCaption") or field.get("name")
            if field_name and field_name not in valid_fields:
                errors.append(f"字段不存在: {field_name}")
        
        # 检查过滤器字段
        for filter_item in query.get("filters", []):
            field_info = filter_item.get("field", {})
            field_name = field_info.get("fieldCaption") or field_info.get("name")
            if field_name and field_name not in valid_fields:
                errors.append(f"过滤器字段不存在: {field_name}")
        
        # 检查排序字段
        for sort in query.get("sorts", []):
            field_info = sort.get("field", {})
            field_name = field_info.get("fieldCaption") or field_info.get("name")
            if field_name and field_name not in valid_fields:
                warnings.append(f"排序字段不存在: {field_name}")
        
        return errors, warnings
    
    async def _llm_check(
        self,
        query: Dict[str, Any],
        data_model
    ) -> Tuple[List[str], List[str]]:
        """LLM 语义检查"""
        import json
        
        prompt = f"""
检查以下 VizQL 查询是否有语义错误。

查询:
{json.dumps(query, ensure_ascii=False, indent=2)}

{self.COMMON_MISTAKES}

如果发现错误，请列出。如果没有错误，返回 "无错误"。

格式：
错误: [错误列表]
警告: [警告列表]
"""
        
        try:
            response = await self.llm.agenerate([prompt])
            text = response.generations[0][0].text
            
            errors = []
            warnings = []
            
            if "无错误" not in text:
                # 解析错误和警告
                if "错误:" in text:
                    error_section = text.split("错误:")[1].split("警告:")[0]
                    errors = [e.strip() for e in error_section.strip().split("\n") if e.strip()]
                if "警告:" in text:
                    warning_section = text.split("警告:")[1]
                    warnings = [w.strip() for w in warning_section.strip().split("\n") if w.strip()]
            
            return errors, warnings
            
        except Exception as e:
            logger.warning(f"LLM check failed: {e}")
            return [], []
    
    async def _auto_fix(
        self,
        query: Dict[str, Any],
        errors: List[str],
        data_model
    ) -> Optional[Dict[str, Any]]:
        """自动修复"""
        if not self.field_mapper:
            return None
        
        fixed_query = query.copy()
        
        for error in errors:
            if "字段不存在" in error:
                # 提取错误的字段名
                import re
                match = re.search(r"字段不存在: (.+)", error)
                if match:
                    wrong_field = match.group(1)
                    # 使用 RAG 找到正确的字段
                    correct_field = await self.field_mapper.map_single_field(
                        wrong_field, data_model
                    )
                    if correct_field:
                        # 替换字段
                        fixed_query = self._replace_field(
                            fixed_query, wrong_field, correct_field
                        )
        
        return fixed_query if fixed_query != query else None
    
    def _replace_field(
        self,
        query: Dict[str, Any],
        old_field: str,
        new_field: str
    ) -> Dict[str, Any]:
        """替换字段"""
        import json
        query_str = json.dumps(query)
        query_str = query_str.replace(f'"{old_field}"', f'"{new_field}"')
        return json.loads(query_str)
```

### 3.3 SelfCorrector 实现

```python
# tableau_assistant/src/agents/self_correction/corrector.py

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """错误类型"""
    FIELD_NOT_FOUND = "field_not_found"
    INVALID_AGGREGATION = "invalid_aggregation"
    INVALID_FILTER = "invalid_filter"
    TYPE_MISMATCH = "type_mismatch"
    SYNTAX_ERROR = "syntax_error"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


class CorrectionResult(BaseModel):
    """纠错结果"""
    success: bool
    original_query: Dict[str, Any]
    corrected_query: Optional[Dict[str, Any]] = None
    error_type: ErrorType
    correction_applied: Optional[str] = None
    attempts: int = 0


class SelfCorrector:
    """
    自我纠错器 - 执行后纠错
    
    功能：
    1. 错误分类
    2. 针对性修复策略
    3. 最多 N 次尝试
    """
    
    ERROR_PATTERNS = {
        ErrorType.FIELD_NOT_FOUND: [
            r"field.*not found",
            r"unknown field",
            r"invalid field",
            r"字段.*不存在",
            r"找不到字段",
        ],
        ErrorType.INVALID_AGGREGATION: [
            r"cannot aggregate",
            r"aggregation.*not supported",
            r"invalid aggregation",
            r"聚合.*不支持",
        ],
        ErrorType.INVALID_FILTER: [
            r"invalid filter",
            r"filter value.*not found",
            r"过滤.*无效",
        ],
        ErrorType.TYPE_MISMATCH: [
            r"type mismatch",
            r"cannot compare",
            r"incompatible types",
            r"类型.*不匹配",
        ],
        ErrorType.RATE_LIMIT: [
            r"rate limit",
            r"too many requests",
            r"请求过于频繁",
        ],
    }
    
    # 不可修复的错误类型
    NON_CORRECTABLE = {
        ErrorType.PERMISSION_DENIED,
        ErrorType.TIMEOUT,
        ErrorType.RATE_LIMIT,
    }
    
    def __init__(
        self,
        llm,
        field_mapper,
        max_attempts: int = 3,
    ):
        self.llm = llm
        self.field_mapper = field_mapper
        self.max_attempts = max_attempts
    
    async def correct(
        self,
        query: Dict[str, Any],
        error: Exception,
        data_model,
        context: Optional[Dict[str, Any]] = None
    ) -> CorrectionResult:
        """
        纠正查询错误
        
        Args:
            query: 原始查询
            error: 执行错误
            data_model: 数据模型
            context: 额外上下文
            
        Returns:
            CorrectionResult
        """
        error_str = str(error)
        error_type = self._classify_error(error_str)
        
        logger.info(f"Correcting error type: {error_type.value}")
        
        # 不可修复的错误
        if error_type in self.NON_CORRECTABLE:
            return CorrectionResult(
                success=False,
                original_query=query,
                error_type=error_type,
                correction_applied=f"Error type {error_type.value} is not correctable"
            )
        
        # 尝试修复
        current_query = query.copy()
        for attempt in range(self.max_attempts):
            try:
                if error_type == ErrorType.FIELD_NOT_FOUND:
                    current_query, correction = await self._fix_field_error(
                        current_query, error_str, data_model
                    )
                elif error_type == ErrorType.INVALID_AGGREGATION:
                    current_query, correction = await self._fix_aggregation_error(
                        current_query, error_str, data_model
                    )
                elif error_type == ErrorType.INVALID_FILTER:
                    current_query, correction = await self._fix_filter_error(
                        current_query, error_str, data_model
                    )
                elif error_type == ErrorType.TYPE_MISMATCH:
                    current_query, correction = await self._fix_type_error(
                        current_query, error_str, data_model
                    )
                else:
                    current_query, correction = await self._generic_fix(
                        current_query, error_str, data_model, context
                    )
                
                return CorrectionResult(
                    success=True,
                    original_query=query,
                    corrected_query=current_query,
                    error_type=error_type,
                    correction_applied=correction,
                    attempts=attempt + 1
                )
                
            except Exception as e:
                logger.warning(f"Correction attempt {attempt + 1} failed: {e}")
                continue
        
        return CorrectionResult(
            success=False,
            original_query=query,
            error_type=error_type,
            attempts=self.max_attempts
        )
    
    def _classify_error(self, error_str: str) -> ErrorType:
        """分类错误"""
        error_lower = error_str.lower()
        
        for error_type, patterns in self.ERROR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, error_lower, re.IGNORECASE):
                    return error_type
        
        return ErrorType.UNKNOWN
    
    async def _fix_field_error(
        self,
        query: Dict[str, Any],
        error_str: str,
        data_model
    ) -> Tuple[Dict[str, Any], str]:
        """修复字段错误"""
        # 提取错误的字段名
        wrong_field = self._extract_field_from_error(error_str)
        if not wrong_field:
            raise ValueError("Cannot extract field name from error")
        
        # 使用 RAG 找到正确的字段
        correct_field = await self.field_mapper.map_single_field(
            wrong_field, data_model
        )
        
        if not correct_field:
            raise ValueError(f"Cannot find similar field for: {wrong_field}")
        
        # 替换字段
        query = self._replace_field(query, wrong_field, correct_field)
        
        return query, f"Replaced '{wrong_field}' with '{correct_field}'"
    
    async def _fix_aggregation_error(
        self,
        query: Dict[str, Any],
        error_str: str,
        data_model
    ) -> Tuple[Dict[str, Any], str]:
        """修复聚合错误"""
        prompt = f"""
修复以下 VizQL 查询的聚合错误。

查询:
{json.dumps(query, ensure_ascii=False, indent=2)}

错误: {error_str}

请返回修复后的查询（JSON 格式）。
"""
        response = await self.llm.agenerate([prompt])
        fixed_query = self._parse_json_response(response.generations[0][0].text)
        
        return fixed_query, "Fixed aggregation error"
    
    async def _fix_filter_error(
        self,
        query: Dict[str, Any],
        error_str: str,
        data_model
    ) -> Tuple[Dict[str, Any], str]:
        """修复过滤器错误"""
        # 获取字段的有效值并修复
        filters = query.get("filters", [])
        
        for i, filter_item in enumerate(filters):
            field_info = filter_item.get("field", {})
            field_name = field_info.get("fieldCaption")
            if not field_name:
                continue
            
            # 获取字段元数据
            field_meta = data_model.get_field(field_name)
            if field_meta and hasattr(field_meta, 'sampleValues'):
                valid_values = field_meta.sampleValues
                filter_values = filter_item.get("values", [])
                
                # 模糊匹配修复
                corrected_values = []
                for val in filter_values:
                    best_match = self._fuzzy_match(val, valid_values)
                    corrected_values.append(best_match or val)
                
                filters[i]["values"] = corrected_values
        
        query["filters"] = filters
        return query, "Fixed filter values"
    
    async def _fix_type_error(
        self,
        query: Dict[str, Any],
        error_str: str,
        data_model
    ) -> Tuple[Dict[str, Any], str]:
        """修复类型错误"""
        prompt = f"""
修复以下 VizQL 查询的类型错误。

查询:
{json.dumps(query, ensure_ascii=False, indent=2)}

错误: {error_str}

常见类型问题：
1. 字符串和数字比较
2. 日期格式不正确
3. 布尔值格式错误

请返回修复后的查询（JSON 格式）。
"""
        response = await self.llm.agenerate([prompt])
        fixed_query = self._parse_json_response(response.generations[0][0].text)
        
        return fixed_query, "Fixed type mismatch"
    
    async def _generic_fix(
        self,
        query: Dict[str, Any],
        error_str: str,
        data_model,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[Dict[str, Any], str]:
        """通用修复"""
        original_question = context.get("question", "") if context else ""
        
        prompt = f"""
修复以下 VizQL 查询的错误。

原始问题: {original_question}

查询:
{json.dumps(query, ensure_ascii=False, indent=2)}

错误: {error_str}

请分析错误原因，并返回修复后的查询（JSON 格式）。
"""
        response = await self.llm.agenerate([prompt])
        fixed_query = self._parse_json_response(response.generations[0][0].text)
        
        return fixed_query, "Applied generic fix"
    
    def _extract_field_from_error(self, error_str: str) -> Optional[str]:
        """从错误消息中提取字段名"""
        patterns = [
            r"field ['\"]?([^'\"]+)['\"]? not found",
            r"unknown field ['\"]?([^'\"]+)['\"]?",
            r"字段 ['\"]?([^'\"]+)['\"]? 不存在",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, error_str, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _replace_field(
        self,
        query: Dict[str, Any],
        old_field: str,
        new_field: str
    ) -> Dict[str, Any]:
        """替换字段"""
        query_str = json.dumps(query)
        query_str = query_str.replace(f'"{old_field}"', f'"{new_field}"')
        return json.loads(query_str)
    
    def _fuzzy_match(
        self,
        target: str,
        candidates: List[str],
        threshold: float = 0.6
    ) -> Optional[str]:
        """模糊匹配"""
        from difflib import SequenceMatcher
        
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            score = SequenceMatcher(
                None, target.lower(), candidate.lower()
            ).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = candidate
        
        return best_match
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """解析 JSON 响应"""
        # 尝试提取 JSON 块
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        
        # 尝试直接解析
        return json.loads(text)
```


---

## 4. P1: 动态 Few-Shot

### 4.1 集成到 SemanticParser

修改 Step1Component 以支持动态 Few-Shot：

```python
# 修改 tableau_assistant/src/agents/semantic_parser/components/step1.py

class Step1Component:
    """Step 1: 语义理解和问题重述"""
    
    def __init__(self, llm=None, training_store=None):
        self._llm = llm
        self._training_store = training_store  # 新增
    
    async def execute(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Step1Output:
        """执行 Step 1"""
        
        # 新增: 检索相似的 Golden Query
        similar_queries = []
        if self._training_store and state:
            datasource_luid = state.get("datasource_luid")
            if datasource_luid:
                similar_queries = await self._training_store.get_similar_queries(
                    question=question,
                    datasource_luid=datasource_luid,
                    top_k=3,
                    min_score=0.5
                )
        
        # 格式化 Few-Shot 示例
        few_shot_str = self._format_few_shot(similar_queries)
        
        # 构建 Prompt（包含 Few-Shot）
        messages = STEP1_PROMPT.format_messages(
            question=question,
            history=self._format_history(history),
            metadata=self._format_metadata(metadata),
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            few_shot_examples=few_shot_str,  # 新增
        )
        
        # ... 其余逻辑不变
    
    def _format_few_shot(
        self,
        similar_queries: List[Tuple["GoldenQuery", float]]
    ) -> str:
        """格式化 Few-Shot 示例"""
        if not similar_queries:
            return "(无相似示例)"
        
        examples = []
        for query, score in similar_queries:
            example = f"""
示例 (相似度: {score:.2f}):
问题: {query.question}
语义查询: {json.dumps(query.semantic_query, ensure_ascii=False, indent=2) if query.semantic_query else "N/A"}
"""
            examples.append(example)
        
        return "\n".join(examples)
```

### 4.2 更新 Prompt 模板

```python
# 修改 tableau_assistant/src/agents/semantic_parser/prompts/step1.py

STEP1_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个 Tableau 数据分析专家，负责理解用户的数据分析问题。

当前时间: {current_time}

可用字段:
{metadata}

{few_shot_examples}

请分析用户问题，提取以下信息：
1. 重述问题（完整、明确）
2. What: 需要查询什么数据
3. Where: 过滤条件
4. How: 如何计算/展示

输出 JSON 格式。
"""),
    ("human", """
对话历史:
{history}

当前问题: {question}
"""),
])
```

---

## 5. P1: 置信度评分

### 5.1 ConfidenceCalculator 实现

```python
# tableau_assistant/src/evaluation/confidence.py

from typing import Dict, List, Optional
from pydantic import BaseModel
from enum import Enum


class ConfidenceDecision(str, Enum):
    """置信度决策"""
    AUTO_EXECUTE = "auto_execute"
    SUGGEST_REVIEW = "suggest_review"
    REQUIRE_CONFIRM = "require_confirm"


class ConfidenceScore(BaseModel):
    """置信度分数"""
    total: float
    breakdown: Dict[str, float]
    decision: ConfidenceDecision
    explanation: str


class ConfidenceCalculator:
    """置信度计算器"""
    
    DEFAULT_WEIGHTS = {
        "schema_linking": 0.30,
        "icl_similarity": 0.25,
        "validation": 0.20,
        "complexity": 0.15,
        "history_success": 0.10,
    }
    
    def __init__(
        self,
        high_threshold: float = 0.8,
        low_threshold: float = 0.5,
        weights: Optional[Dict[str, float]] = None
    ):
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.weights = weights or self.DEFAULT_WEIGHTS
    
    def calculate(
        self,
        schema_link_scores: List[float],
        icl_similarity: float,
        validation_passed: bool,
        query_complexity: Optional[Dict[str, int]] = None,
        history_success_rate: Optional[float] = None
    ) -> ConfidenceScore:
        """计算置信度"""
        scores = {}
        explanations = []
        
        # 1. Schema Linking 分数
        if schema_link_scores:
            avg = sum(schema_link_scores) / len(schema_link_scores)
            min_score = min(schema_link_scores)
            scores["schema_linking"] = 0.7 * avg + 0.3 * min_score
            if min_score < 0.5:
                explanations.append(f"部分字段匹配置信度较低 ({min_score:.2f})")
        else:
            scores["schema_linking"] = 0.0
        
        # 2. ICL 相似度
        scores["icl_similarity"] = icl_similarity
        if icl_similarity > 0.8:
            explanations.append("找到高度相似的历史查询")
        elif icl_similarity < 0.3:
            explanations.append("未找到相似的历史查询")
        
        # 3. 验证分数
        scores["validation"] = 1.0 if validation_passed else 0.0
        if not validation_passed:
            explanations.append("语法验证未通过")
        
        # 4. 复杂度分数
        scores["complexity"] = self._complexity_score(query_complexity)
        
        # 5. 历史成功率
        scores["history_success"] = history_success_rate or 0.5
        
        # 计算总分
        total = sum(scores[k] * self.weights[k] for k in scores)
        
        # 决策
        if total >= self.high_threshold:
            decision = ConfidenceDecision.AUTO_EXECUTE
        elif total >= self.low_threshold:
            decision = ConfidenceDecision.SUGGEST_REVIEW
        else:
            decision = ConfidenceDecision.REQUIRE_CONFIRM
        
        return ConfidenceScore(
            total=total,
            breakdown=scores,
            decision=decision,
            explanation="; ".join(explanations) if explanations else "置信度正常"
        )
    
    def _complexity_score(
        self,
        complexity: Optional[Dict[str, int]]
    ) -> float:
        """计算复杂度分数"""
        if not complexity:
            return 0.7
        
        penalty = 0.0
        penalty += max(0, complexity.get("fields", 0) - 5) * 0.05
        penalty += max(0, complexity.get("filters", 0) - 3) * 0.1
        penalty += complexity.get("calculations", 0) * 0.15
        
        return max(0.0, 1.0 - penalty)
```

### 5.2 集成到工作流

```python
# 修改 tableau_assistant/src/nodes/query_builder/node.py

async def query_builder_node(state: VizQLState, config: RunnableConfig) -> Dict:
    """QueryBuilder 节点"""
    
    # ... 现有逻辑 ...
    
    # 新增: 计算置信度
    from tableau_assistant.src.evaluation.confidence import ConfidenceCalculator
    
    calculator = ConfidenceCalculator()
    
    # 收集置信度输入
    schema_link_scores = state.get("field_mapping_scores", [])
    icl_similarity = state.get("icl_similarity", 0.0)
    
    confidence = calculator.calculate(
        schema_link_scores=schema_link_scores,
        icl_similarity=icl_similarity,
        validation_passed=True,  # 假设验证通过
        query_complexity={
            "fields": len(vizql_query.fields),
            "filters": len(vizql_query.filters or []),
            "calculations": sum(1 for f in vizql_query.fields if f.calculation),
        }
    )
    
    return {
        "vizql_query": vizql_query,
        "confidence_score": confidence,  # 新增
        "query_builder_complete": True,
    }
```

---

## 6. P2: 增强 Schema Linking

### 6.1 EnhancedSchemaLinker 实现

```python
# tableau_assistant/src/rag/schema_linker.py

from typing import List, Tuple, Optional
from pydantic import BaseModel


class SchemaLinkResult(BaseModel):
    """Schema Linking 结果"""
    tables: List[str]
    fields: List[Tuple[str, float]]  # (field_name, confidence)
    values: List[Tuple[str, str]]  # (field_name, value)
    icl_examples: List[dict] = []


class EnhancedSchemaLinker:
    """
    增强的 Schema Linker
    
    借鉴 DIN-SQL 和 RESDSQL 的设计：
    1. 层次化链接（先表后字段）
    2. Cross-Encoder Rerank
    3. 外键关系利用
    """
    
    def __init__(
        self,
        bi_encoder,
        cross_encoder=None,
        training_store=None,
    ):
        self.bi_encoder = bi_encoder
        self.cross_encoder = cross_encoder
        self.training_store = training_store
    
    async def link(
        self,
        question: str,
        data_model,
        top_k_tables: int = 5,
        top_k_fields: int = 10
    ) -> SchemaLinkResult:
        """执行 Schema Linking"""
        
        # 1. 检索 ICL 示例
        icl_examples = []
        if self.training_store:
            similar = await self.training_store.get_similar_queries(
                question, data_model.datasource_luid, top_k=3
            )
            icl_examples = [q.model_dump() for q, _ in similar]
        
        # 2. 表级链接
        tables = await self._link_tables(question, data_model, top_k_tables)
        
        # 3. 添加关联表
        tables = self._add_related_tables(tables, data_model)
        
        # 4. 字段级链接
        fields = await self._link_fields(question, tables, data_model, top_k_fields)
        
        # 5. 值链接
        values = self._extract_values(question, fields, data_model)
        
        return SchemaLinkResult(
            tables=[t[0] for t in tables],
            fields=fields,
            values=values,
            icl_examples=icl_examples,
        )
    
    async def _link_tables(
        self,
        question: str,
        data_model,
        top_k: int
    ) -> List[Tuple[str, float]]:
        """表级链接"""
        # Bi-Encoder 初筛
        tables = data_model.get_tables() if hasattr(data_model, 'get_tables') else []
        if not tables:
            return []
        
        table_texts = [self._table_to_text(t) for t in tables]
        question_embedding = await self.bi_encoder.aembed_query(question)
        table_embeddings = await self.bi_encoder.aembed_documents(table_texts)
        
        # 计算相似度
        import numpy as np
        scores = np.dot(table_embeddings, question_embedding)
        
        # 排序
        ranked = sorted(
            zip([t.name for t in tables], scores),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Cross-Encoder Rerank（如果可用）
        if self.cross_encoder:
            candidates = ranked[:top_k * 2]
            pairs = [(question, self._table_to_text(data_model.get_table(t))) 
                     for t, _ in candidates]
            rerank_scores = self.cross_encoder.predict(pairs)
            ranked = sorted(
                zip([t for t, _ in candidates], rerank_scores),
                key=lambda x: x[1],
                reverse=True
            )
        
        return ranked[:top_k]
    
    async def _link_fields(
        self,
        question: str,
        tables: List[Tuple[str, float]],
        data_model,
        top_k: int
    ) -> List[Tuple[str, float]]:
        """字段级链接"""
        all_fields = []
        
        for table_name, table_score in tables:
            table = data_model.get_table(table_name) if hasattr(data_model, 'get_table') else None
            if not table:
                continue
            
            fields = table.fields if hasattr(table, 'fields') else []
            for field in fields:
                field_text = self._field_to_text(field)
                all_fields.append((field.fieldCaption, field_text, table_score))
        
        if not all_fields:
            # 回退到所有字段
            fields = data_model.fields if hasattr(data_model, 'fields') else []
            for field in fields:
                field_text = self._field_to_text(field)
                all_fields.append((field.fieldCaption, field_text, 1.0))
        
        # Bi-Encoder 检索
        question_embedding = await self.bi_encoder.aembed_query(question)
        field_texts = [f[1] for f in all_fields]
        field_embeddings = await self.bi_encoder.aembed_documents(field_texts)
        
        import numpy as np
        scores = np.dot(field_embeddings, question_embedding)
        
        # 结合表分数
        final_scores = [
            (all_fields[i][0], scores[i] * 0.7 + all_fields[i][2] * 0.3)
            for i in range(len(all_fields))
        ]
        
        # 排序并去重
        seen = set()
        ranked = []
        for field_name, score in sorted(final_scores, key=lambda x: x[1], reverse=True):
            if field_name not in seen:
                seen.add(field_name)
                ranked.append((field_name, score))
        
        return ranked[:top_k]
    
    def _add_related_tables(
        self,
        tables: List[Tuple[str, float]],
        data_model
    ) -> List[Tuple[str, float]]:
        """添加外键关联的表"""
        if not hasattr(data_model, 'relationships'):
            return tables
        
        table_names = {t[0] for t in tables}
        
        for rel in data_model.relationships:
            if rel.from_table in table_names and rel.to_table not in table_names:
                tables.append((rel.to_table, 0.5))  # 关联表给较低分数
                table_names.add(rel.to_table)
        
        return tables
    
    def _extract_values(
        self,
        question: str,
        fields: List[Tuple[str, float]],
        data_model
    ) -> List[Tuple[str, str]]:
        """从问题中提取可能的值"""
        values = []
        
        for field_name, _ in fields:
            field = data_model.get_field(field_name) if hasattr(data_model, 'get_field') else None
            if not field or not hasattr(field, 'sampleValues'):
                continue
            
            for sample in field.sampleValues:
                if str(sample).lower() in question.lower():
                    values.append((field_name, str(sample)))
        
        return values
    
    def _table_to_text(self, table) -> str:
        """表转文本"""
        if hasattr(table, 'description'):
            return f"{table.name}: {table.description}"
        return table.name
    
    def _field_to_text(self, field) -> str:
        """字段转文本"""
        parts = [field.fieldCaption or field.name]
        if hasattr(field, 'description') and field.description:
            parts.append(field.description)
        if hasattr(field, 'role'):
            parts.append(f"({field.role})")
        return " | ".join(parts)
```

---

## 7. 集成测试计划

### 7.1 单元测试

```python
# tests/test_training_store.py

import pytest
from tableau_assistant.src.training.store import TrainingDataStore
from tableau_assistant.src.training.models import GoldenQuery, UserFeedback


@pytest.fixture
def training_store(mock_store, mock_embedding):
    return TrainingDataStore(mock_store, mock_embedding)


class TestTrainingDataStore:
    
    async def test_add_golden_query(self, training_store):
        query = GoldenQuery(
            question="各产品类别的销售额",
            vizql_query={"fields": [...]},
            datasource_luid="test-ds"
        )
        
        query_id = await training_store.add_golden_query(query)
        assert query_id == query.id
    
    async def test_get_similar_queries(self, training_store):
        # 添加测试数据
        await training_store.add_golden_query(GoldenQuery(
            question="各产品类别的销售额",
            vizql_query={},
            datasource_luid="test-ds"
        ))
        
        # 检索相似查询
        results = await training_store.get_similar_queries(
            "产品类别销售情况",
            "test-ds",
            top_k=5
        )
        
        assert len(results) > 0
        assert results[0][1] > 0.5  # 相似度 > 0.5
    
    async def test_auto_learn_from_feedback(self, training_store):
        feedback = UserFeedback(
            question="各地区的利润",
            generated_query={"fields": [...]},
            datasource_luid="test-ds",
            is_correct=True
        )
        
        await training_store.record_feedback(feedback, auto_learn=True)
        
        # 验证自动学习
        results = await training_store.get_similar_queries(
            "各地区的利润",
            "test-ds"
        )
        assert len(results) > 0
```

### 7.2 集成测试

```python
# tests/integration/test_self_correction.py

import pytest
from tableau_assistant.src.agents.self_correction import QueryChecker, SelfCorrector


class TestSelfCorrection:
    
    async def test_query_checker_detects_invalid_field(
        self, mock_llm, mock_data_model
    ):
        checker = QueryChecker(mock_llm)
        
        query = {
            "fields": [{"fieldCaption": "不存在的字段"}]
        }
        
        result = await checker.check(query, mock_data_model)
        
        assert not result.is_valid
        assert "字段不存在" in result.errors[0]
    
    async def test_self_corrector_fixes_field_error(
        self, mock_llm, mock_field_mapper, mock_data_model
    ):
        corrector = SelfCorrector(mock_llm, mock_field_mapper)
        
        query = {"fields": [{"fieldCaption": "销售金额"}]}
        error = Exception("field '销售金额' not found")
        
        result = await corrector.correct(query, error, mock_data_model)
        
        assert result.success
        assert result.corrected_query != query
```

### 7.3 端到端测试

```python
# tests/e2e/test_workflow_with_improvements.py

import pytest
from tableau_assistant.src.orchestration.workflow.executor import WorkflowExecutor


class TestWorkflowWithImprovements:
    
    async def test_workflow_uses_dynamic_few_shot(self, executor):
        # 先添加一个 Golden Query
        await executor.training_store.add_golden_query(...)
        
        # 执行相似问题
        result = await executor.run("各产品类别的销售额是多少?")
        
        assert result.success
        # 验证使用了 Few-Shot
        assert result.icl_similarity > 0.5
    
    async def test_workflow_self_corrects_on_error(self, executor):
        # 模拟一个会产生错误的查询
        result = await executor.run("显示不存在字段的数据")
        
        # 验证自我纠错
        assert result.success or result.correction_applied
```

---

## 8. 总结

本指南提供了基于业界主流项目分析的具体改进实施方案：

### 实施优先级

1. **P0 (立即)**: 训练数据管理 + 自我纠错机制
2. **P1 (短期)**: 动态 Few-Shot + 置信度评分
3. **P2 (中期)**: 增强 Schema Linking

### 预期收益

| 改进项 | 准确性提升 | 用户体验 |
|--------|-----------|---------|
| 训练数据管理 | +15% | 持续改进 |
| 自我纠错 | +10% | 减少错误 |
| 动态 Few-Shot | +10% | 更准确 |
| 置信度评分 | - | 透明度提升 |
| 增强 Schema Linking | +5% | 更准确 |

### 下一步

1. 创建 `tableau_assistant/src/training/` 目录
2. 实现 TrainingDataStore
3. 实现 SelfCorrector
4. 集成到现有工作流
5. 编写测试用例

---

*文档创建时间: 2024-12-21*
*版本: 1.0*
