# 洞察反思机制 - 设计文档

## 📖 文档导航

### 🔗 相关文档
- **[需求文档](./requirements.md)** - 功能需求和验收标准
- **[任务列表](./tasks.md)** - 可执行的任务分解（待创建）

### 📋 本文档内容
- 系统架构设计
- 核心组件设计
- 数据结构设计
- 反思流程设计
- Prompt 设计
- 接口设计

---

## 1. 系统架构概览

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    InsightAgent（增强版）                     │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  generate_insight_with_reflection()                  │   │
│  │                                                       │   │
│  │  ┌────────────────┐                                  │   │
│  │  │ 生成初始洞察    │                                  │   │
│  │  └────────┬───────┘                                  │   │
│  │           │                                           │   │
│  │           ▼                                           │   │
│  │  ┌────────────────┐                                  │   │
│  │  │ 反思策略决策    │ ← 用户模式 + 任务复杂度          │   │
│  │  └────────┬───────┘                                  │   │
│  │           │                                           │   │
│  │           ▼                                           │   │
│  │  需要反思？                                           │   │
│  │     ├─ 否 → 返回初始洞察                              │   │
│  │     └─ 是 ↓                                          │   │
│  │           │                                           │   │
│  │           ▼                                           │   │
│  │  ┌────────────────┐                                  │   │
│  │  │ 反思评估器      │                                  │   │
│  │  │ - 评估完整性    │                                  │   │
│  │  │ - 识别遗漏      │                                  │   │
│  │  └────────┬───────┘                                  │   │
│  │           │                                           │   │
│  │           ▼                                           │   │
│  │  是否完整？                                           │   │
│  │     ├─ 是 → 返回当前洞察                              │   │
│  │     └─ 否 ↓                                          │   │
│  │           │                                           │   │
│  │           ▼                                           │   │
│  │  ┌────────────────┐                                  │   │
│  │  │ 补充分析器      │                                  │   │
│  │  │ - 轻量级反思    │ ← 基于现有数据                   │   │
│  │  │ - 完整反思      │ ← 可执行补充查询                 │   │
│  │  └────────┬───────┘                                  │   │
│  │           │                                           │   │
│  │           ▼                                           │   │
│  │  ┌────────────────┐                                  │   │
│  │  │ 洞察合并器      │                                  │   │
│  │  └────────┬───────┘                                  │   │
│  │           │                                           │   │
│  │           ▼                                           │   │
│  │  反思次数 < 最大次数？                                 │   │
│  │     ├─ 是 → 回到"反思评估器"                          │   │
│  │     └─ 否 → 返回最终洞察                              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```


### 1.2 与现有系统的集成

```
现有系统：
┌─────────────────────────────────────────────────────────────┐
│ 任务调度器 → 查询执行 → 数据处理 → InsightAgent → 重规划    │
└─────────────────────────────────────────────────────────────┘

增强后：
┌─────────────────────────────────────────────────────────────┐
│ 任务调度器 → 查询执行 → 数据处理 → InsightAgent（带反思）   │
│                                           ↓                  │
│                                    任务级反思循环             │
│                                    （自我评估+补充）          │
│                                           ↓                  │
│                                      重规划Agent              │
│                                    （综合决策）               │
└─────────────────────────────────────────────────────────────┘
```

**关键点**：
- 任务级反思：提高单个洞察的质量
- 分析级重规划：决定整体分析方向
- 两者互补，不冲突

---

## 2. 核心数据结构设计

### 2.1 反思配置

```python
from dataclasses import dataclass
from enum import Enum

class AnalysisMode(Enum):
    """分析模式"""
    FAST = "fast"      # 快速模式
    DEEP = "deep"      # 深度模式
    AUTO = "auto"      # 自动模式

class ReflectionType(Enum):
    """反思类型"""
    NONE = "none"              # 不反思
    LIGHT = "light"            # 轻量级反思
    FULL = "full"              # 完整反思

@dataclass
class ReflectionConfig:
    """反思配置"""
    enabled: bool = True
    max_reflections: int = 2
    light_reflection_timeout: int = 3  # 秒
    full_reflection_timeout: int = 8   # 秒
    min_completeness_score: float = 0.7  # 最低完整性评分
```

### 2.2 复杂度评估

```python
@dataclass
class ComplexityScore:
    """复杂度评分"""
    overall_score: float  # 总评分（0-1）
    data_score: float     # 数据维度评分
    question_score: float # 问题维度评分
    analysis_score: float # 分析维度评分
    anomaly_score: float  # 异常维度评分
    
    category: str  # simple, medium, complex
    reasoning: str # 评分理由
    
    def is_simple(self) -> bool:
        return self.overall_score < 0.4
    
    def is_medium(self) -> bool:
        return 0.4 <= self.overall_score <= 0.7
    
    def is_complex(self) -> bool:
        return self.overall_score > 0.7
```

### 2.3 反思评估

```python
@dataclass
class ReflectionEvaluation:
    """反思评估结果"""
    is_complete: bool
    completeness_score: float  # 0-1
    missing_aspects: List[str]
    reasoning: str
    
    # 详细评估
    data_coverage: float      # 数据覆盖度
    dimension_completeness: float  # 维度完整性
    trend_analysis: bool      # 是否包含趋势分析
    anomaly_explanation: bool # 是否解释异常
    comparison_analysis: bool # 是否包含对比
    root_cause_depth: float   # 根因挖掘深度
```

### 2.4 反思记录

```python
@dataclass
class ReflectionRecord:
    """反思记录"""
    reflection_id: str
    task_id: str
    reflection_round: int  # 第几轮反思
    
    # 反思前
    initial_insight: str
    initial_completeness: float
    
    # 反思过程
    reflection_type: ReflectionType
    missing_aspects: List[str]
    supplementary_analysis: str
    
    # 反思后
    final_insight: str
    final_completeness: float
    improvement: float  # 改进幅度
    
    # 性能
    time_cost: float  # 秒
    
    timestamp: datetime
```



---

## 3. 核心组件设计

### 3.1 复杂度评估器 (ComplexityAssessor)

```python
class ComplexityAssessor:
    """任务复杂度评估器"""
    
    def assess(self, task: TaskInsight) -> ComplexityScore:
        """
        评估任务复杂度
        
        Args:
            task: 任务洞察对象
            
        Returns:
            复杂度评分
        """
        # 1. 数据维度评分（权重30%）
        data_score = self._assess_data_dimension(task)
        
        # 2. 问题维度评分（权重30%）
        question_score = self._assess_question_dimension(task)
        
        # 3. 分析维度评分（权重20%）
        analysis_score = self._assess_analysis_dimension(task)
        
        # 4. 异常维度评分（权重20%）
        anomaly_score = self._assess_anomaly_dimension(task)
        
        # 5. 计算总评分
        overall_score = (
            data_score * 0.3 +
            question_score * 0.3 +
            analysis_score * 0.2 +
            anomaly_score * 0.2
        )
        
        # 6. 分类
        if overall_score < 0.4:
            category = "simple"
        elif overall_score <= 0.7:
            category = "medium"
        else:
            category = "complex"
        
        return ComplexityScore(
            overall_score=overall_score,
            data_score=data_score,
            question_score=question_score,
            analysis_score=analysis_score,
            anomaly_score=anomaly_score,
            category=category,
            reasoning=self._generate_reasoning(...)
        )
    
    def _assess_data_dimension(self, task: TaskInsight) -> float:
        """评估数据维度"""
        row_count = task.query_metadata.get('row_count', 0)
        col_count = task.query_metadata.get('col_count', 0)
        
        row_score = 0.0
        if row_count > 1000:
            row_score = 1.0
        elif row_count > 100:
            row_score = 0.5
        
        col_score = 0.0
        if col_count > 10:
            col_score = 1.0
        elif col_count > 5:
            col_score = 0.5
        
        return (row_score + col_score) / 2
    
    def _assess_question_dimension(self, task: TaskInsight) -> float:
        """评估问题维度"""
        question = task.question.lower()
        
        # 问题类型评分
        type_score = 0.0
        if any(word in question for word in ['why', '为什么', '原因']):
            type_score = 1.0  # 根因分析
        elif any(word in question for word in ['compare', '对比', '哪个']):
            type_score = 0.5  # 对比分析
        
        # 问题复杂度评分
        complexity_score = 0.0
        if '和' in question or 'and' in question:
            complexity_score = 0.5  # 多指标
        if len(question) > 50:
            complexity_score = min(complexity_score + 0.3, 1.0)
        
        return (type_score + complexity_score) / 2
    
    def _assess_analysis_dimension(self, task: TaskInsight) -> float:
        """评估分析维度"""
        dimension_count = task.query_metadata.get('dimension_count', 0)
        time_span_days = task.query_metadata.get('time_span_days', 0)
        
        dim_score = 0.0
        if dimension_count > 3:
            dim_score = 1.0
        elif dimension_count > 1:
            dim_score = 0.5
        
        time_score = 0.0
        if time_span_days > 90:
            time_score = 1.0
        elif time_span_days > 30:
            time_score = 0.5
        
        return (dim_score + time_score) / 2
    
    def _assess_anomaly_dimension(self, task: TaskInsight) -> float:
        """评估异常维度"""
        has_anomaly = task.query_metadata.get('has_anomaly', False)
        has_null = task.query_metadata.get('has_null', False)
        
        score = 0.0
        if has_anomaly:
            score += 1.0
        if has_null:
            score += 0.5
        
        return min(score, 1.0)
```

### 3.2 反思策略决策器 (ReflectionStrategyDecider)

```python
class ReflectionStrategyDecider:
    """反思策略决策器"""
    
    def decide(
        self,
        user_mode: AnalysisMode,
        complexity: ComplexityScore,
        analysis_type: AnalysisType,
        is_critical_task: bool = False
    ) -> Tuple[ReflectionType, int]:
        """
        决定反思策略
        
        Args:
            user_mode: 用户选择的模式
            complexity: 任务复杂度
            analysis_type: 分析类型（NORMAL/EXPLORATORY）
            is_critical_task: 是否是关键任务
            
        Returns:
            (反思类型, 最大反思次数)
        """
        # 快速模式
        if user_mode == AnalysisMode.FAST:
            return self._decide_fast_mode(
                complexity, analysis_type, is_critical_task
            )
        
        # 深度模式
        elif user_mode == AnalysisMode.DEEP:
            return self._decide_deep_mode(
                complexity, analysis_type, is_critical_task
            )
        
        # 自动模式
        else:
            return self._decide_auto_mode(
                complexity, analysis_type, is_critical_task
            )
    
    def _decide_fast_mode(
        self, 
        complexity: ComplexityScore,
        analysis_type: AnalysisType,
        is_critical_task: bool
    ) -> Tuple[ReflectionType, int]:
        """快速模式决策"""
        # 关键任务：完整反思1次
        if is_critical_task:
            return (ReflectionType.FULL, 1)
        
        # 探索式分析 + 复杂任务：轻量级反思1次
        if analysis_type == AnalysisType.EXPLORATORY and complexity.is_complex():
            return (ReflectionType.LIGHT, 1)
        
        # 其他：不反思
        return (ReflectionType.NONE, 0)
    
    def _decide_deep_mode(
        self,
        complexity: ComplexityScore,
        analysis_type: AnalysisType,
        is_critical_task: bool
    ) -> Tuple[ReflectionType, int]:
        """深度模式决策"""
        # 关键任务或复杂任务：完整反思2次
        if is_critical_task or complexity.is_complex():
            return (ReflectionType.FULL, 2)
        
        # 中等任务：完整反思1次
        if complexity.is_medium():
            return (ReflectionType.FULL, 1)
        
        # 简单任务：轻量级反思1次
        return (ReflectionType.LIGHT, 1)
    
    def _decide_auto_mode(
        self,
        complexity: ComplexityScore,
        analysis_type: AnalysisType,
        is_critical_task: bool
    ) -> Tuple[ReflectionType, int]:
        """自动模式决策"""
        # 关键任务：完整反思2次
        if is_critical_task:
            return (ReflectionType.FULL, 2)
        
        # 复杂任务：完整反思1次
        if complexity.is_complex():
            return (ReflectionType.FULL, 1)
        
        # 中等任务：轻量级反思1次
        if complexity.is_medium():
            return (ReflectionType.LIGHT, 1)
        
        # 简单任务：不反思
        return (ReflectionType.NONE, 0)
```



### 3.3 反思评估器 (ReflectionEvaluator)

```python
class ReflectionEvaluator:
    """反思评估器"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    async def evaluate(
        self,
        question: str,
        insight: str,
        query_results: Dict,
        task_metadata: Dict
    ) -> ReflectionEvaluation:
        """
        评估洞察的完整性
        
        Args:
            question: 分析问题
            insight: 当前洞察
            query_results: 查询结果
            task_metadata: 任务元数据
            
        Returns:
            反思评估结果
        """
        # 构建评估prompt
        prompt = self._build_evaluation_prompt(
            question, insight, query_results, task_metadata
        )
        
        # 调用LLM评估
        response = await self.llm_client.invoke(
            system_prompt=REFLECTION_EVALUATION_PROMPT,
            user_message=prompt
        )
        
        # 解析评估结果
        evaluation = self._parse_evaluation(response)
        
        return evaluation
    
    def _build_evaluation_prompt(
        self,
        question: str,
        insight: str,
        query_results: Dict,
        task_metadata: Dict
    ) -> str:
        """构建评估prompt"""
        return f"""
【分析问题】
{question}

【当前洞察】
{insight}

【数据概况】
- 数据行数：{task_metadata.get('row_count', 'N/A')}
- 维度数量：{task_metadata.get('dimension_count', 'N/A')}
- 时间跨度：{task_metadata.get('time_span_days', 'N/A')}天
- 是否有异常：{task_metadata.get('has_anomaly', False)}

【评估任务】
请评估当前洞察的完整性，识别可能遗漏的方面。
"""
```

### 3.4 补充分析器 (SupplementaryAnalyzer)

```python
class SupplementaryAnalyzer:
    """补充分析器"""
    
    def __init__(self, llm_client, query_executor):
        self.llm_client = llm_client
        self.query_executor = query_executor
    
    async def analyze_light(
        self,
        question: str,
        current_insight: str,
        missing_aspects: List[str],
        query_results: Dict
    ) -> str:
        """
        轻量级补充分析（基于现有数据）
        
        Args:
            question: 分析问题
            current_insight: 当前洞察
            missing_aspects: 遗漏的方面
            query_results: 现有查询结果
            
        Returns:
            补充洞察
        """
        prompt = f"""
【分析问题】
{question}

【当前洞察】
{current_insight}

【识别的遗漏方面】
{self._format_missing_aspects(missing_aspects)}

【现有数据】
{self._format_query_results(query_results)}

【任务】
基于现有数据，从不同角度补充分析遗漏的方面。
不要重复当前洞察中已有的内容。
"""
        
        response = await self.llm_client.invoke(
            system_prompt=SUPPLEMENTARY_ANALYSIS_PROMPT,
            user_message=prompt
        )
        
        return response
    
    async def analyze_full(
        self,
        question: str,
        current_insight: str,
        missing_aspects: List[str],
        original_query_spec: Dict
    ) -> str:
        """
        完整补充分析（可执行补充查询）
        
        Args:
            question: 分析问题
            current_insight: 当前洞察
            missing_aspects: 遗漏的方面
            original_query_spec: 原始查询规格
            
        Returns:
            补充洞察
        """
        # 1. 生成补充查询
        supplementary_queries = await self._generate_supplementary_queries(
            missing_aspects, original_query_spec
        )
        
        # 2. 执行补充查询
        supplementary_results = []
        for query in supplementary_queries:
            result = await self.query_executor.execute(query)
            supplementary_results.append(result)
        
        # 3. 基于新数据生成补充洞察
        prompt = f"""
【分析问题】
{question}

【当前洞察】
{current_insight}

【识别的遗漏方面】
{self._format_missing_aspects(missing_aspects)}

【补充查询结果】
{self._format_supplementary_results(supplementary_results)}

【任务】
基于补充查询的结果，生成补充洞察。
不要重复当前洞察中已有的内容。
"""
        
        response = await self.llm_client.invoke(
            system_prompt=SUPPLEMENTARY_ANALYSIS_PROMPT,
            user_message=prompt
        )
        
        return response
```

### 3.5 洞察合并器 (InsightMerger)

```python
class InsightMerger:
    """洞察合并器"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    async def merge(
        self,
        initial_insight: str,
        supplementary_insight: str,
        question: str
    ) -> str:
        """
        合并初始洞察和补充洞察
        
        Args:
            initial_insight: 初始洞察
            supplementary_insight: 补充洞察
            question: 分析问题
            
        Returns:
            合并后的洞察
        """
        prompt = f"""
【分析问题】
{question}

【初始洞察】
{initial_insight}

【补充洞察】
{supplementary_insight}

【任务】
将初始洞察和补充洞察整合为一个完整、连贯的分析。
要求：
1. 保留初始洞察的核心内容
2. 有机融入补充洞察
3. 去除重复内容
4. 保持逻辑连贯
5. 突出关键发现
"""
        
        response = await self.llm_client.invoke(
            system_prompt=INSIGHT_MERGE_PROMPT,
            user_message=prompt
        )
        
        return response
```



---

## 4. 反思流程设计

### 4.1 完整反思流程

```python
class InsightAgent:
    """增强版洞察Agent（支持反思）"""
    
    def __init__(
        self,
        llm_client,
        query_executor,
        config: ReflectionConfig
    ):
        self.llm_client = llm_client
        self.query_executor = query_executor
        self.config = config
        
        # 初始化组件
        self.complexity_assessor = ComplexityAssessor()
        self.strategy_decider = ReflectionStrategyDecider()
        self.reflection_evaluator = ReflectionEvaluator(llm_client)
        self.supplementary_analyzer = SupplementaryAnalyzer(
            llm_client, query_executor
        )
        self.insight_merger = InsightMerger(llm_client)
    
    async def generate_insight(
        self,
        task: TaskInsight,
        user_mode: AnalysisMode,
        analysis_type: AnalysisType,
        is_critical_task: bool = False
    ) -> str:
        """
        生成洞察（带反思）
        
        Args:
            task: 任务洞察对象
            user_mode: 用户选择的模式
            analysis_type: 分析类型
            is_critical_task: 是否是关键任务
            
        Returns:
            最终洞察
        """
        # 1. 生成初始洞察
        initial_insight = await self._generate_initial_insight(task)
        
        # 2. 评估任务复杂度
        complexity = self.complexity_assessor.assess(task)
        
        # 3. 决定反思策略
        reflection_type, max_reflections = self.strategy_decider.decide(
            user_mode, complexity, analysis_type, is_critical_task
        )
        
        # 4. 如果不需要反思，直接返回
        if reflection_type == ReflectionType.NONE:
            return initial_insight
        
        # 5. 执行反思循环
        return await self._reflection_loop(
            task,
            initial_insight,
            reflection_type,
            max_reflections
        )
    
    async def _reflection_loop(
        self,
        task: TaskInsight,
        initial_insight: str,
        reflection_type: ReflectionType,
        max_reflections: int
    ) -> str:
        """
        反思循环
        
        Args:
            task: 任务对象
            initial_insight: 初始洞察
            reflection_type: 反思类型
            max_reflections: 最大反思次数
            
        Returns:
            最终洞察
        """
        current_insight = initial_insight
        reflection_records = []
        
        for round_num in range(1, max_reflections + 1):
            logger.info(f"开始第 {round_num} 轮反思...")
            
            # 1. 评估当前洞察
            evaluation = await self.reflection_evaluator.evaluate(
                question=task.question,
                insight=current_insight,
                query_results=task.query_results,
                task_metadata=task.query_metadata
            )
            
            # 2. 如果已经完整，停止反思
            if evaluation.is_complete:
                logger.info(f"洞察已完整（评分：{evaluation.completeness_score:.2f}），停止反思")
                break
            
            # 3. 如果评分过低，也停止（避免无效反思）
            if evaluation.completeness_score < self.config.min_completeness_score:
                logger.warning(f"洞察评分过低（{evaluation.completeness_score:.2f}），停止反思")
                break
            
            logger.info(f"发现遗漏方面：{evaluation.missing_aspects}")
            
            # 4. 执行补充分析
            if reflection_type == ReflectionType.LIGHT:
                supplementary_insight = await self.supplementary_analyzer.analyze_light(
                    question=task.question,
                    current_insight=current_insight,
                    missing_aspects=evaluation.missing_aspects,
                    query_results=task.query_results
                )
            else:  # FULL
                supplementary_insight = await self.supplementary_analyzer.analyze_full(
                    question=task.question,
                    current_insight=current_insight,
                    missing_aspects=evaluation.missing_aspects,
                    original_query_spec=task.query_spec
                )
            
            # 5. 合并洞察
            merged_insight = await self.insight_merger.merge(
                initial_insight=current_insight,
                supplementary_insight=supplementary_insight,
                question=task.question
            )
            
            # 6. 记录反思
            record = ReflectionRecord(
                reflection_id=f"{task.task_id}_r{round_num}",
                task_id=task.task_id,
                reflection_round=round_num,
                initial_insight=current_insight,
                initial_completeness=evaluation.completeness_score,
                reflection_type=reflection_type,
                missing_aspects=evaluation.missing_aspects,
                supplementary_analysis=supplementary_insight,
                final_insight=merged_insight,
                final_completeness=0.0,  # 下一轮会评估
                improvement=0.0,
                time_cost=0.0,  # 实际实现时记录
                timestamp=datetime.now()
            )
            reflection_records.append(record)
            
            # 7. 更新当前洞察
            current_insight = merged_insight
            
            logger.info(f"第 {round_num} 轮反思完成")
        
        # 8. 保存反思记录到任务
        task.reflection_records = reflection_records
        
        return current_insight
    
    async def _generate_initial_insight(self, task: TaskInsight) -> str:
        """生成初始洞察（现有逻辑）"""
        # 现有的洞察生成逻辑
        pass
```

### 4.2 快速模式流程示例

```
用户选择：快速模式
任务：简单查询（"2024年各地区销售额"）

流程：
1. 生成初始洞察 ✓
2. 评估复杂度：简单任务（0.3）
3. 决定策略：不反思
4. 直接返回初始洞察

总耗时：5秒（无额外开销）
```

### 4.3 深度模式流程示例

```
用户选择：深度模式
任务：复杂根因分析（"为什么华东利润率低"）

流程：
1. 生成初始洞察 ✓（5秒）
   "华东利润率12%，低于全国平均15%"

2. 评估复杂度：复杂任务（0.8）

3. 决定策略：完整反思，最多2次

4. 第1轮反思：
   - 评估：遗漏了产品维度分析
   - 补充查询：查询各产品类别利润率
   - 补充洞察："家具类利润率仅8%"
   - 合并洞察 ✓（8秒）

5. 第2轮反思：
   - 评估：遗漏了折扣分析
   - 补充查询：查询折扣情况
   - 补充洞察："家具类折扣率22%，过高"
   - 合并洞察 ✓（8秒）

6. 返回最终洞察

总耗时：21秒（+16秒，+76%）
质量提升：发现了根本原因
```



---

## 5. Prompt 设计

### 5.1 反思评估 Prompt

```python
REFLECTION_EVALUATION_PROMPT = """
你是一位专业的数据分析质量评估专家。你的任务是评估数据洞察的完整性，识别可能遗漏的关键信息。

【评估维度】
1. **数据覆盖度** - 是否分析了所有关键数据点
2. **维度完整性** - 是否考虑了所有相关维度
3. **趋势分析** - 是否分析了时间趋势（如适用）
4. **异常识别** - 是否识别和解释了异常值
5. **对比分析** - 是否进行了必要的对比（如适用）
6. **根因挖掘** - 是否深入到根本原因（如适用）

【输出格式】
请以JSON格式输出评估结果：
{
  "is_complete": true/false,
  "completeness_score": 0.0-1.0,
  "missing_aspects": ["遗漏方面1", "遗漏方面2"],
  "reasoning": "评估理由",
  "data_coverage": 0.0-1.0,
  "dimension_completeness": 0.0-1.0,
  "trend_analysis": true/false,
  "anomaly_explanation": true/false,
  "comparison_analysis": true/false,
  "root_cause_depth": 0.0-1.0
}

【评估标准】
- completeness_score >= 0.8：完整，无需补充
- completeness_score 0.6-0.8：基本完整，可以补充
- completeness_score < 0.6：不完整，需要补充

请客观、严格地评估，不要过于宽松。
"""
```

### 5.2 补充分析 Prompt

```python
SUPPLEMENTARY_ANALYSIS_PROMPT = """
你是一位专业的数据分析师。你需要针对识别出的遗漏方面，进行补充分析。

【分析原则】
1. **聚焦遗漏** - 只分析遗漏的方面，不重复已有内容
2. **基于数据** - 所有结论必须基于提供的数据
3. **深入挖掘** - 不要停留在表面，要深入分析
4. **结构清晰** - 使用清晰的结构组织补充内容
5. **关联分析** - 尝试将补充发现与已有洞察关联

【输出要求】
- 使用Markdown格式
- 突出关键发现
- 提供具体数据支撑
- 保持客观和准确

请生成补充洞察。
"""
```

### 5.3 洞察合并 Prompt

```python
INSIGHT_MERGE_PROMPT = """
你是一位专业的数据分析报告编辑。你需要将初始洞察和补充洞察整合为一个完整、连贯的分析。

【合并原则】
1. **保留核心** - 保留初始洞察的核心内容和结构
2. **有机融入** - 将补充洞察自然地融入到合适的位置
3. **去除冗余** - 删除重复的内容
4. **逻辑连贯** - 确保整体逻辑流畅
5. **突出重点** - 突出最关键的发现

【输出要求】
- 使用Markdown格式
- 保持专业的分析风格
- 结构清晰，层次分明
- 关键发现使用加粗或列表突出

请生成合并后的完整洞察。
"""
```

---

## 6. 接口设计

### 6.1 用户接口

```python
# 前端调用示例
analysis_request = {
    "question": "为什么华东地区利润率低？",
    "mode": "deep",  # fast, deep, auto
    "analysis_type": "exploratory"
}

result = await analysis_engine.analyze(analysis_request)
```

### 6.2 InsightAgent 接口

```python
class InsightAgent:
    async def generate_insight(
        self,
        task: TaskInsight,
        user_mode: AnalysisMode,
        analysis_type: AnalysisType,
        is_critical_task: bool = False
    ) -> str:
        """生成洞察（带反思）"""
        pass
    
    async def generate_insight_without_reflection(
        self,
        task: TaskInsight
    ) -> str:
        """生成洞察（不反思，兼容旧版）"""
        pass
```

### 6.3 配置接口

```python
# 全局配置
reflection_config = ReflectionConfig(
    enabled=True,
    max_reflections=2,
    light_reflection_timeout=3,
    full_reflection_timeout=8,
    min_completeness_score=0.7
)

# 用户偏好配置
user_preferences = {
    "default_mode": "auto",
    "enable_reflection": True
}
```

---

## 7. 性能优化

### 7.1 并行优化

```python
# 多任务并行时，反思也并行
async def process_multiple_tasks(tasks: List[TaskInsight]):
    # 所有任务的洞察生成（包括反思）并行执行
    insights = await asyncio.gather(*[
        insight_agent.generate_insight(task, user_mode, analysis_type)
        for task in tasks
    ])
    return insights
```

### 7.2 缓存优化

```python
class ReflectionCache:
    """反思结果缓存"""
    
    def __init__(self):
        self.cache = {}
    
    def get_cached_evaluation(
        self,
        question: str,
        insight: str
    ) -> Optional[ReflectionEvaluation]:
        """获取缓存的评估结果"""
        key = self._generate_key(question, insight)
        return self.cache.get(key)
    
    def cache_evaluation(
        self,
        question: str,
        insight: str,
        evaluation: ReflectionEvaluation
    ):
        """缓存评估结果"""
        key = self._generate_key(question, insight)
        self.cache[key] = evaluation
```

### 7.3 超时控制

```python
async def _reflection_loop_with_timeout(self, ...):
    """带超时控制的反思循环"""
    try:
        async with asyncio.timeout(self.config.full_reflection_timeout):
            return await self._reflection_loop(...)
    except asyncio.TimeoutError:
        logger.warning("反思超时，返回当前洞察")
        return current_insight
```

---

## 8. 监控和日志

### 8.1 反思监控指标

```python
@dataclass
class ReflectionMetrics:
    """反思监控指标"""
    # 质量指标
    total_reflections: int
    successful_reflections: int
    average_improvement: float
    
    # 性能指标
    average_reflection_time: float
    timeout_count: int
    
    # 策略指标
    no_reflection_count: int
    light_reflection_count: int
    full_reflection_count: int
    
    # 模式指标
    fast_mode_count: int
    deep_mode_count: int
    auto_mode_count: int
```

### 8.2 日志设计

```python
# 反思开始
logger.info(f"[Reflection] 开始反思 - Task: {task.task_id}, Mode: {user_mode}, Type: {reflection_type}")

# 评估结果
logger.info(f"[Reflection] 评估完成 - Score: {evaluation.completeness_score:.2f}, Missing: {evaluation.missing_aspects}")

# 补充分析
logger.info(f"[Reflection] 补充分析完成 - Type: {reflection_type}, Time: {time_cost:.2f}s")

# 反思完成
logger.info(f"[Reflection] 反思完成 - Rounds: {round_num}, Final Score: {final_score:.2f}, Improvement: {improvement:.2f}")
```

---

## 9. 测试策略

### 9.1 单元测试

- ComplexityAssessor 测试
- ReflectionStrategyDecider 测试
- ReflectionEvaluator 测试
- SupplementaryAnalyzer 测试
- InsightMerger 测试

### 9.2 集成测试

- 完整反思流程测试
- 不同模式下的反思测试
- 超时和异常处理测试

### 9.3 端到端测试

- 快速模式场景测试
- 深度模式场景测试
- 自动模式场景测试

---

**设计文档版本**: v1.0
**最后更新**: 2025-01-14
**文档状态**: 待审核
