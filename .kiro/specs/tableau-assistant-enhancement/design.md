# Tableau Assistant 系统化增强 - 设计文档

## 📖 文档导航

### 🔗 相关文档
- **[需求文档](./requirements.md)** - 功能需求和验收标准
- **[任务列表](./tasks.md)** - 可执行的任务分解（待创建）

### 📋 本文档内容
- 系统架构设计
- 核心组件设计
- 数据结构设计
- 接口设计
- 工作流设计
- 技术选型

---

## 1. 系统架构概览

### 1.1 当前架构分析

**现有优势**：
- ✅ **BaseAgent 架构**：统一的 Agent 执行流程，支持流式输出
- ✅ **MetadataManager**：完善的元数据管理和缓存（1小时TTL）
- ✅ **QueryExecutor**：支持重试、超时控制、QueryBuilder 集成
- ✅ **LangGraph Store**：PersistentStore 提供 SQLite 持久化
- ✅ **Pydantic 验证**：所有数据模型都有结构化验证
- ✅ **LLM 缓存**：LLMCache 缓存 LLM 响应（1小时TTL）

**需要增强的部分**：
- ❌ **任务调度器缺失**：QuerySubTask 生成后没有自动调度执行
- ❌ **查询结果缓存缺失**：重规划时需要重新执行所有查询
- ❌ **累积洞察缺失**：没有多 AI 并行分析和智能合成机制
- ❌ **上下文优化不足**：元数据没有基于 Category 过滤，Token 消耗高
- ❌ **错误修正缺失**：查询失败后没有自动修正机制

### 1.2 增强后的架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                                │
│                    (Tableau Extension UI)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      VizQL 工作流引擎                             │
│                    (LangGraph StateGraph)                       │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │Understanding │→│  Planning    │→│  Execution   │          │
│  │   Agent      │  │   Agent      │  │   Layer      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                              │                   │
│                                              ▼                   │
│  ┌─────────────────────────────────────────────────┐            │
│  │         任务调度器 (TaskScheduler) 【新增】      │            │
│  │  - 调度所有 QuerySubTask                        │            │
│  │  - 并行执行（asyncio）                          │            │
│  │  - 依赖管理（拓扑排序）                         │            │
│  │  - 查询结果缓存（1-2小时TTL）                   │            │
│  │  - 进度跟踪和实时反馈                           │            │
│  └─────────────────────────────────────────────────┘            │
│                             │                                     │
│                             ▼                                     │
│  ┌──────────────────────────────────────────────┐               │
│  │    查询验证和错误修正 【新增】                │               │
│  │  - 字段存在性验证                             │               │
│  │  - 聚合函数合法性验证                         │               │
│  │  - LLM 驱动的错误分析和修正                   │               │
│  │  - 智能重试（最多3次）                        │               │
│  └──────────────────────────────────────────────┘               │
│                             │                                     │
│                             ▼                                     │
│  ┌──────────────────────────────────────────────┐               │
│  │    上下文智能管理 【增强】                    │               │
│  │  - 基于 Category 过滤元数据                   │               │
│  │  - Token 预算管理（8000 tokens）             │               │
│  │  - 对话历史压缩（保留最近5轮）                │               │
│  └──────────────────────────────────────────────┘               │
│                                                                   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      持久化层（已有）                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │SQLite        │  │PersistentStore│  │InMemorySaver │          │
│  │Tracking      │  │(查询缓存)     │  │(会话管理)    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 核心设计原则

1. **复用现有架构**：基于 BaseAgent、MetadataManager、QueryExecutor 等现有组件
2. **异步优先**：充分利用 asyncio，提升并发性能
3. **缓存优先**：多级缓存策略（LLM缓存、元数据缓存、查询结果缓存）
4. **错误恢复**：智能错误处理和自动修正
5. **可观测性**：完整的日志和监控（SQLiteTrackingCallback）
6. **渐进式增强**：保持向后兼容，支持渐进式迁移

---

## 2. 核心组件设计

### 2.1 任务调度器 (TaskScheduler) 【新增】

**职责**：
- 自动调度执行所有 QuerySubTask
- 管理并行和串行执行（基于依赖关系）
- 查询结果缓存（1-2小时TTL）
- 进度跟踪和实时反馈
- 配合累积洞察机制

**为什么需要任务调度器？**
1. **当前问题**：QuerySubTask 生成后需要手动调用 QueryExecutor
2. **解决方案**：自动调度，支持并行执行，提升效率
3. **累积洞察支持**：为每个查询结果启动独立的洞察分析
4. **缓存支持**：避免重规划时重复查询（150x 提升）

**与现有组件的关系**：
- 使用 `QueryExecutor` 执行单个查询
- 使用 `PersistentStore` 缓存查询结果
- 使用 `asyncio` 实现并行执行
- 集成到 `vizql_workflow.py` 中作为新节点

---


### 2.2 任务调度器 (TaskScheduler)

**职责**：
- 自动执行 QuerySubTask
- 管理并行和串行执行
- 处理任务依赖关系
- 查询结果缓存
- 进度跟踪

**接口设计**：
```python
from typing import List, Dict, Optional
from dataclasses import dataclass
import asyncio
from datetime import datetime

@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    cached: bool = False

class TaskScheduler:
    """任务调度器"""
    
    def __init__(
        self,
        query_executor,
        result_cache,
        max_concurrent: int = 3
    ):
        self.query_executor = query_executor
        self.result_cache = result_cache
        self.max_concurrent = max_concurrent
    
    async def schedule_tasks(
        self,
        tasks: List[QuerySubTask],
        progress_callback: Optional[callable] = None
    ) -> List[TaskResult]:
        """
        调度并执行任务
        
        Args:
            tasks: 任务列表
            progress_callback: 进度回调函数
            
        Returns:
            所有任务的执行结果
        """
        # 1. 分析依赖关系
        dependency_graph = self._analyze_dependencies(tasks)
        
        # 2. 拓扑排序
        execution_order = self._topological_sort(dependency_graph)
        
        # 3. 分批执行
        results = []
        for batch in execution_order:
            batch_results = await self._execute_batch(
                batch, 
                progress_callback
            )
            results.extend(batch_results)
        
        return results
    
    def _analyze_dependencies(
        self, 
        tasks: List[QuerySubTask]
    ) -> Dict[str, List[str]]:
        """分析任务依赖关系"""
        graph = {}
        for task in tasks:
            graph[task.task_id] = task.depends_on or []
        return graph
    
    def _topological_sort(
        self, 
        graph: Dict[str, List[str]]
    ) -> List[List[str]]:
        """
        拓扑排序，返回分批执行的任务列表
        
        Returns:
            [[batch1_tasks], [batch2_tasks], ...]
        """
        # 计算入度
        in_degree = {node: 0 for node in graph}
        for node in graph:
            for dep in graph[node]:
                in_degree[node] += 1
        
        # 分批处理
        batches = []
        remaining = set(graph.keys())
        
        while remaining:
            # 找出所有入度为0的节点（可以并行执行）
            batch = [
                node for node in remaining 
                if in_degree[node] == 0
            ]
            
            if not batch:
                raise ValueError("检测到循环依赖")
            
            batches.append(batch)
            
            # 更新入度
            for node in batch:
                remaining.remove(node)
                for other in remaining:
                    if node in graph[other]:
                        in_degree[other] -= 1
        
        return batches
    
    async def _execute_batch(
        self,
        task_ids: List[str],
        progress_callback: Optional[callable] = None
    ) -> List[TaskResult]:
        """
        并行执行一批任务
        
        Args:
            task_ids: 任务ID列表
            progress_callback: 进度回调
        """
        # 使用 asyncio.Semaphore 控制并发数
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def execute_with_semaphore(task_id: str):
            async with semaphore:
                return await self._execute_single_task(
                    task_id, 
                    progress_callback
                )
        
        # 并行执行
        tasks = [
            execute_with_semaphore(task_id) 
            for task_id in task_ids
        ]
        return await asyncio.gather(*tasks)
    
    async def _execute_single_task(
        self,
        task_id: str,
        progress_callback: Optional[callable] = None
    ) -> TaskResult:
        """执行单个任务"""
        start_time = datetime.now()
        
        try:
            # 1. 检查缓存
            cached_result = await self.result_cache.get(task_id)
            if cached_result:
                if progress_callback:
                    await progress_callback(task_id, "cached")
                return TaskResult(
                    task_id=task_id,
                    success=True,
                    data=cached_result,
                    cached=True,
                    execution_time=0.0
                )
            
            # 2. 执行查询
            if progress_callback:
                await progress_callback(task_id, "executing")
            
            result = await self.query_executor.execute_subtask(task_id)
            
            # 3. 缓存结果
            await self.result_cache.set(task_id, result)
            
            # 4. 返回结果
            execution_time = (datetime.now() - start_time).total_seconds()
            
            if progress_callback:
                await progress_callback(task_id, "completed")
            
            return TaskResult(
                task_id=task_id,
                success=True,
                data=result,
                cached=False,
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            
            if progress_callback:
                await progress_callback(task_id, "failed")
            
            return TaskResult(
                task_id=task_id,
                success=False,
                error=str(e),
                execution_time=execution_time
            )
```

---

### 2.3 查询结果缓存 (QueryResultCache)

**职责**：
- 缓存查询结果
- 支持 TTL（1-2小时）
- 基于查询内容的哈希键
- 缓存命中率统计

**接口设计**：
```python
from typing import Optional, Dict
import hashlib
import json
from datetime import datetime, timedelta

class QueryResultCache:
    """查询结果缓存"""
    
    def __init__(
        self,
        persistent_store,
        ttl_hours: int = 2
    ):
        self.store = persistent_store
        self.ttl = timedelta(hours=ttl_hours)
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0
        }
    
    def _generate_cache_key(
        self, 
        task_id: str, 
        query_spec: Dict
    ) -> str:
        """
        生成缓存键
        
        基于查询内容的哈希，确保相同查询使用相同缓存
        """
        # 将查询规格序列化为稳定的字符串
        query_str = json.dumps(query_spec, sort_keys=True)
        hash_obj = hashlib.sha256(query_str.encode())
        return f"query_cache:{hash_obj.hexdigest()}"
    
    async def get(
        self, 
        task_id: str, 
        query_spec: Dict
    ) -> Optional[Dict]:
        """获取缓存的查询结果"""
        cache_key = self._generate_cache_key(task_id, query_spec)
        
        # 从持久化存储获取
        cached_data = await self.store.get(cache_key)
        
        if cached_data is None:
            self.stats["misses"] += 1
            return None
        
        # 检查是否过期
        cached_time = datetime.fromisoformat(cached_data["timestamp"])
        if datetime.now() - cached_time > self.ttl:
            # 过期，删除缓存
            await self.store.delete(cache_key)
            self.stats["misses"] += 1
            return None
        
        self.stats["hits"] += 1
        return cached_data["result"]
    
    async def set(
        self, 
        task_id: str, 
        query_spec: Dict, 
        result: Dict
    ) -> None:
        """设置缓存"""
        cache_key = self._generate_cache_key(task_id, query_spec)
        
        cached_data = {
            "task_id": task_id,
            "result": result,
            "timestamp": datetime.now().isoformat()
        }
        
        await self.store.set(cache_key, cached_data)
        self.stats["sets"] += 1
    
    def get_hit_rate(self) -> float:
        """获取缓存命中率"""
        total = self.stats["hits"] + self.stats["misses"]
        if total == 0:
            return 0.0
        return self.stats["hits"] / total
```

---


### 2.4 增强数据处理器 (Enhanced Data Processor) 【重大增强】

**为什么需要增强？**
- **当前限制**：只支持基础的同比、环比、占比计算
- **业务需求**：需要更强大的数据分析能力（统计分析、时间序列预测、机器学习）
- **技术栈**：从 Polars 迁移到 pandas，利用更丰富的数据科学生态

**增强功能模块**：

#### 2.4.1 基础数据处理（保留现有功能）
- 同比分析（YoY）
- 环比分析（MoM）
- 增长率计算
- 占比分析
- 自定义公式计算

#### 2.4.2 派生指标计算 【新增】
**功能**：基于原始数据自动计算业务指标
- **移动平均**：MA(7), MA(30), EMA
- **累计指标**：累计销售额、累计用户数
- **排名指标**：RANK, DENSE_RANK, ROW_NUMBER
- **窗口函数**：LEAD, LAG, FIRST_VALUE, LAST_VALUE
- **业务指标**：
  - 客户生命周期价值（LTV）
  - 留存率（Retention Rate）
  - 流失率（Churn Rate）
  - 转化率（Conversion Rate）
  - RFM 分析（Recency, Frequency, Monetary）

**实现库**：pandas + numpy

#### 2.4.3 数据画像 【新增】
**功能**：自动生成数据的统计描述和分布特征

**描述性统计**：
- 基础统计：均值、中位数、众数、标准差、方差
- 分位数：Q1, Q2, Q3, IQR
- 偏度（Skewness）和峰度（Kurtosis）
- 缺失值分析
- 异常值检测（IQR方法、Z-score方法）

**分布分析**：
- 数值型字段：直方图统计、正态性检验
- 分类型字段：频数统计、基数分析
- 时间型字段：时间跨度、采样频率

**相关性分析**：
- Pearson 相关系数
- Spearman 秩相关系数
- 协方差矩阵
- 特征重要性分析

**实现库**：pandas + scipy.stats + numpy

#### 2.4.4 统计分析 【新增】
**功能**：提供专业的统计检验和分析方法

**假设检验**：
- t检验（单样本、双样本、配对）
- 卡方检验（独立性检验、拟合优度检验）
- 方差分析（ANOVA）
- 非参数检验（Mann-Whitney U、Kruskal-Wallis）

**回归分析**：
- 线性回归（OLS）
- 多元回归
- 逻辑回归
- 岭回归（Ridge）、Lasso回归

**置信区间**：
- 均值置信区间
- 比例置信区间
- 预测区间

**实现库**：scipy.stats + statsmodels + scikit-learn

#### 2.4.5 时间序列分析 【新增】
**功能**：专业的时间序列分析和预测

**时间序列分解**：
- 趋势分析（Trend）
- 季节性分析（Seasonality）
- 周期性分析（Cycle）
- 残差分析（Residual）

**平稳性检验**：
- ADF检验（Augmented Dickey-Fuller）
- KPSS检验
- 自相关分析（ACF）
- 偏自相关分析（PACF）

**时间序列预测**：
- **ARIMA模型**：自动参数选择（auto_arima）
- **SARIMA模型**：季节性ARIMA
- **Prophet模型**：Facebook开源的时间序列预测
- **指数平滑**：Holt-Winters方法
- **LSTM模型**：深度学习时间序列预测（可选）

**异常检测**：
- 基于统计的异常检测
- 基于预测的异常检测
- 季节性异常检测

**实现库**：
- statsmodels（ARIMA、SARIMA、指数平滑）
- prophet（Facebook Prophet）
- pmdarima（auto_arima）
- tensorflow/pytorch（LSTM，可选）

#### 2.4.6 机器学习分析 【新增】
**功能**：提供常用的机器学习算法

**聚类分析**：
- K-Means聚类
- DBSCAN密度聚类
- 层次聚类（Hierarchical）
- 高斯混合模型（GMM）
- 客户分群（Customer Segmentation）

**分类分析**：
- 决策树（Decision Tree）
- 随机森林（Random Forest）
- 梯度提升（XGBoost、LightGBM）
- 支持向量机（SVM）
- 朴素贝叶斯（Naive Bayes）

**异常检测**：
- Isolation Forest
- One-Class SVM
- Local Outlier Factor（LOF）
- Autoencoder（深度学习，可选）

**特征工程**：
- 特征选择（SelectKBest、RFE）
- 特征重要性排序
- 主成分分析（PCA）
- 特征标准化/归一化

**模型评估**：
- 分类指标：准确率、精确率、召回率、F1-score、AUC-ROC
- 聚类指标：轮廓系数、Calinski-Harabasz指数
- 回归指标：MAE、MSE、RMSE、R²

**实现库**：
- scikit-learn（核心算法）
- xgboost（梯度提升）
- lightgbm（轻量级梯度提升）
- tensorflow/pytorch（深度学习，可选）

#### 2.4.7 智能分析建议 【新增】
**功能**：基于数据特征自动推荐合适的分析方法

**自动分析流程**：
1. **数据类型识别**：自动识别数值型、分类型、时间型字段
2. **数据质量评估**：缺失值、异常值、数据分布
3. **分析方法推荐**：
   - 时间序列数据 → 推荐时间序列分析和预测
   - 分类数据 → 推荐分组统计和卡方检验
   - 数值数据 → 推荐相关性分析和回归分析
   - 多维数据 → 推荐聚类分析和降维
4. **结果解释**：用自然语言解释分析结果

**实现方式**：
- 使用 LLM 分析数据特征
- 基于规则引擎推荐分析方法
- 自动生成分析报告

---

### 2.4.8 数据处理器架构设计

**新架构**：
```
DataProcessor (主处理器)
├── BasicProcessor (基础处理器)
│   ├── YoYProcessor (同比)
│   ├── MoMProcessor (环比)
│   ├── GrowthRateProcessor (增长率)
│   ├── PercentageProcessor (占比)
│   └── CustomProcessor (自定义公式)
│
├── DerivedMetricsProcessor (派生指标处理器) 【新增】
│   ├── MovingAverageCalculator (移动平均)
│   ├── CumulativeCalculator (累计指标)
│   ├── RankingCalculator (排名指标)
│   ├── WindowFunctionCalculator (窗口函数)
│   └── BusinessMetricsCalculator (业务指标)
│
├── DataProfilingProcessor (数据画像处理器) 【新增】
│   ├── DescriptiveStatistics (描述性统计)
│   ├── DistributionAnalyzer (分布分析)
│   ├── CorrelationAnalyzer (相关性分析)
│   └── OutlierDetector (异常值检测)
│
├── StatisticalProcessor (统计分析处理器) 【新增】
│   ├── HypothesisTest (假设检验)
│   ├── RegressionAnalyzer (回归分析)
│   └── ConfidenceInterval (置信区间)
│
├── TimeSeriesProcessor (时间序列处理器) 【新增】
│   ├── Decomposer (时间序列分解)
│   ├── StationarityTest (平稳性检验)
│   ├── Forecaster (预测器)
│   │   ├── ARIMAForecaster
│   │   ├── ProphetForecaster
│   │   └── ExponentialSmoothingForecaster
│   └── AnomalyDetector (异常检测)
│
├── MachineLearningProcessor (机器学习处理器) 【新增】
│   ├── ClusteringAnalyzer (聚类分析)
│   ├── ClassificationAnalyzer (分类分析)
│   ├── AnomalyDetector (异常检测)
│   └── FeatureEngineer (特征工程)
│
└── IntelligentAdvisor (智能分析建议) 【新增】
    ├── DataTypeIdentifier (数据类型识别)
    ├── QualityAssessor (数据质量评估)
    ├── MethodRecommender (方法推荐)
    └── ResultInterpreter (结果解释)
```

**技术栈变更**：
```python
# 旧技术栈
import polars as pl

# 新技术栈
import pandas as pd
import numpy as np
from scipy import stats
import statsmodels.api as sm
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import adfuller, kpss
from statsmodels.tsa.arima.model import ARIMA
from prophet import Prophet
from pmdarima import auto_arima
from sklearn.cluster import KMeans, DBSCAN
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import xgboost as xgb
import lightgbm as lgb
```

**数据流设计**：
```
查询结果 (pandas DataFrame)
    ↓
数据预处理
    ├── 数据类型转换
    ├── 缺失值处理
    ├── 异常值处理
    └── 数据验证
    ↓
智能分析建议 (可选)
    ├── 识别数据特征
    ├── 推荐分析方法
    └── 生成分析计划
    ↓
执行分析任务
    ├── 基础处理
    ├── 派生指标计算
    ├── 数据画像
    ├── 统计分析
    ├── 时间序列分析
    └── 机器学习分析
    ↓
结果封装和解释
    ├── 结构化结果
    ├── 可视化建议
    └── 自然语言解释
    ↓
返回 ProcessingResult
```

---

### 2.5 查询验证和错误修正 【新增】

**为什么需要？**
- **当前问题**：查询失败后直接返回错误，没有自动修正
- **解决方案**：在查询执行前后进行验证和修正，提升成功率 20-30%

**验证策略**：
1. **Pydantic 结构验证**（已有）：所有数据模型都有 Pydantic 验证
2. **字段存在性验证**（新增）：检查字段是否在元数据中
3. **聚合函数验证**（新增）：检查聚合函数是否适用于字段类型

**错误修正策略**：
1. **字段不存在** → 搜索相似字段（基于字符串相似度）
2. **聚合函数错误** → 建议合适的聚合函数
3. **VizQL 语法错误** → 使用 LLM 分析并修正
4. **查询超时** → 简化查询（减少字段、添加限制）

**实现方式**：
- 在 `QueryExecutor.execute_query()` 中添加验证逻辑
- 使用 `difflib.SequenceMatcher` 查找相似字段
- 使用 LLM 分析复杂错误并生成修正方案
- 最多重试 3 次

---


### 2.6 增强数据处理器接口设计

#### 2.6.1 派生指标处理器接口

```python
from typing import Dict, List, Optional
import pandas as pd
from enum import Enum

class WindowType(Enum):
    """窗口类型"""
    ROLLING = "rolling"  # 滚动窗口
    EXPANDING = "expanding"  # 扩展窗口
    EWMA = "ewma"  # 指数加权移动平均

class DerivedMetricsProcessor:
    """派生指标处理器"""
    
    def calculate_moving_average(
        self,
        df: pd.DataFrame,
        value_col: str,
        window: int = 7,
        window_type: WindowType = WindowType.ROLLING,
        group_by: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        计算移动平均
        
        Args:
            df: 输入数据
            value_col: 数值列名
            window: 窗口大小
            window_type: 窗口类型
            group_by: 分组字段
            
        Returns:
            添加了移动平均列的DataFrame
        """
        pass
    
    def calculate_cumulative(
        self,
        df: pd.DataFrame,
        value_col: str,
        group_by: Optional[List[str]] = None,
        order_by: Optional[str] = None
    ) -> pd.DataFrame:
        """
        计算累计指标
        
        Args:
            df: 输入数据
            value_col: 数值列名
            group_by: 分组字段
            order_by: 排序字段
            
        Returns:
            添加了累计列的DataFrame
        """
        pass
    
    def calculate_ranking(
        self,
        df: pd.DataFrame,
        value_col: str,
        method: str = "dense",  # dense, min, max, average
        ascending: bool = False,
        group_by: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        计算排名
        
        Args:
            df: 输入数据
            value_col: 数值列名
            method: 排名方法
            ascending: 是否升序
            group_by: 分组字段
            
        Returns:
            添加了排名列的DataFrame
        """
        pass
    
    def calculate_rfm(
        self,
        df: pd.DataFrame,
        customer_col: str,
        date_col: str,
        amount_col: str,
        reference_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        计算RFM指标
        
        Args:
            df: 输入数据
            customer_col: 客户ID列
            date_col: 日期列
            amount_col: 金额列
            reference_date: 参考日期
            
        Returns:
            RFM分析结果
        """
        pass
```

#### 2.6.2 数据画像处理器接口

```python
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class DataProfile:
    """数据画像结果"""
    # 基础信息
    row_count: int
    column_count: int
    memory_usage: int
    
    # 字段统计
    numeric_fields: Dict[str, Dict[str, Any]]  # 数值字段统计
    categorical_fields: Dict[str, Dict[str, Any]]  # 分类字段统计
    datetime_fields: Dict[str, Dict[str, Any]]  # 时间字段统计
    
    # 数据质量
    missing_values: Dict[str, int]
    duplicate_rows: int
    outliers: Dict[str, List[Any]]
    
    # 相关性分析
    correlation_matrix: Optional[pd.DataFrame]
    high_correlations: List[tuple]  # [(col1, col2, corr_value), ...]

class DataProfilingProcessor:
    """数据画像处理器"""
    
    def generate_profile(
        self,
        df: pd.DataFrame,
        include_correlation: bool = True,
        outlier_method: str = "iqr"  # iqr, zscore
    ) -> DataProfile:
        """
        生成完整的数据画像
        
        Args:
            df: 输入数据
            include_correlation: 是否包含相关性分析
            outlier_method: 异常值检测方法
            
        Returns:
            数据画像结果
        """
        pass
    
    def analyze_distribution(
        self,
        df: pd.DataFrame,
        column: str
    ) -> Dict[str, Any]:
        """
        分析单个字段的分布
        
        Args:
            df: 输入数据
            column: 列名
            
        Returns:
            分布分析结果（包含直方图数据、正态性检验等）
        """
        pass
    
    def detect_outliers(
        self,
        df: pd.DataFrame,
        column: str,
        method: str = "iqr",
        threshold: float = 1.5
    ) -> pd.Series:
        """
        检测异常值
        
        Args:
            df: 输入数据
            column: 列名
            method: 检测方法（iqr, zscore）
            threshold: 阈值
            
        Returns:
            布尔Series，True表示异常值
        """
        pass
```

#### 2.6.3 时间序列处理器接口

```python
from typing import Tuple, Optional
import pandas as pd

@dataclass
class ForecastResult:
    """预测结果"""
    forecast: pd.Series  # 预测值
    lower_bound: pd.Series  # 置信区间下界
    upper_bound: pd.Series  # 置信区间上界
    model_name: str  # 模型名称
    metrics: Dict[str, float]  # 评估指标（MAE, RMSE等）
    model_params: Dict[str, Any]  # 模型参数

class TimeSeriesProcessor:
    """时间序列处理器"""
    
    def decompose(
        self,
        df: pd.DataFrame,
        value_col: str,
        date_col: str,
        model: str = "additive",  # additive, multiplicative
        period: Optional[int] = None
    ) -> Dict[str, pd.Series]:
        """
        时间序列分解
        
        Args:
            df: 输入数据
            value_col: 数值列
            date_col: 日期列
            model: 分解模型
            period: 周期
            
        Returns:
            分解结果（trend, seasonal, residual）
        """
        pass
    
    def test_stationarity(
        self,
        series: pd.Series
    ) -> Dict[str, Any]:
        """
        平稳性检验
        
        Args:
            series: 时间序列
            
        Returns:
            检验结果（ADF检验、KPSS检验）
        """
        pass
    
    def forecast_arima(
        self,
        df: pd.DataFrame,
        value_col: str,
        date_col: str,
        periods: int = 30,
        auto_params: bool = True,
        seasonal: bool = False
    ) -> ForecastResult:
        """
        ARIMA预测
        
        Args:
            df: 输入数据
            value_col: 数值列
            date_col: 日期列
            periods: 预测期数
            auto_params: 是否自动选择参数
            seasonal: 是否使用季节性ARIMA
            
        Returns:
            预测结果
        """
        pass
    
    def forecast_prophet(
        self,
        df: pd.DataFrame,
        value_col: str,
        date_col: str,
        periods: int = 30,
        include_holidays: bool = False,
        country: str = "CN"
    ) -> ForecastResult:
        """
        Prophet预测
        
        Args:
            df: 输入数据
            value_col: 数值列
            date_col: 日期列
            periods: 预测期数
            include_holidays: 是否包含节假日效应
            country: 国家代码
            
        Returns:
            预测结果
        """
        pass
    
    def detect_anomalies(
        self,
        df: pd.DataFrame,
        value_col: str,
        date_col: str,
        method: str = "statistical",  # statistical, prophet, isolation_forest
        sensitivity: float = 0.95
    ) -> pd.DataFrame:
        """
        时间序列异常检测
        
        Args:
            df: 输入数据
            value_col: 数值列
            date_col: 日期列
            method: 检测方法
            sensitivity: 敏感度
            
        Returns:
            添加了异常标记的DataFrame
        """
        pass
```

#### 2.6.4 机器学习处理器接口

```python
from sklearn.base import BaseEstimator

@dataclass
class ClusteringResult:
    """聚类结果"""
    labels: pd.Series  # 聚类标签
    n_clusters: int  # 聚类数量
    cluster_centers: Optional[np.ndarray]  # 聚类中心
    metrics: Dict[str, float]  # 评估指标
    model: BaseEstimator  # 训练好的模型

@dataclass
class ClassificationResult:
    """分类结果"""
    predictions: pd.Series  # 预测结果
    probabilities: Optional[pd.DataFrame]  # 预测概率
    metrics: Dict[str, float]  # 评估指标
    feature_importance: Optional[pd.Series]  # 特征重要性
    model: BaseEstimator  # 训练好的模型

class MachineLearningProcessor:
    """机器学习处理器"""
    
    def cluster_kmeans(
        self,
        df: pd.DataFrame,
        features: List[str],
        n_clusters: Optional[int] = None,
        auto_select: bool = True,
        max_clusters: int = 10
    ) -> ClusteringResult:
        """
        K-Means聚类
        
        Args:
            df: 输入数据
            features: 特征列
            n_clusters: 聚类数量
            auto_select: 是否自动选择最优聚类数
            max_clusters: 最大聚类数
            
        Returns:
            聚类结果
        """
        pass
    
    def classify_random_forest(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        features: List[str],
        target: str,
        n_estimators: int = 100
    ) -> ClassificationResult:
        """
        随机森林分类
        
        Args:
            train_df: 训练数据
            test_df: 测试数据
            features: 特征列
            target: 目标列
            n_estimators: 树的数量
            
        Returns:
            分类结果
        """
        pass
    
    def detect_anomalies_isolation_forest(
        self,
        df: pd.DataFrame,
        features: List[str],
        contamination: float = 0.1
    ) -> pd.Series:
        """
        Isolation Forest异常检测
        
        Args:
            df: 输入数据
            features: 特征列
            contamination: 异常值比例
            
        Returns:
            异常标记（1=正常，-1=异常）
        """
        pass
    
    def reduce_dimensions_pca(
        self,
        df: pd.DataFrame,
        features: List[str],
        n_components: Optional[int] = None,
        variance_threshold: float = 0.95
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        PCA降维
        
        Args:
            df: 输入数据
            features: 特征列
            n_components: 主成分数量
            variance_threshold: 方差阈值
            
        Returns:
            降维后的数据和分析结果
        """
        pass
```

#### 2.6.5 智能分析建议接口

```python
@dataclass
class AnalysisRecommendation:
    """分析建议"""
    recommended_methods: List[str]  # 推荐的分析方法
    reasons: Dict[str, str]  # 推荐原因
    priority: Dict[str, int]  # 优先级（1-5）
    expected_insights: Dict[str, str]  # 预期洞察

class IntelligentAdvisor:
    """智能分析建议"""
    
    def recommend_analysis(
        self,
        df: pd.DataFrame,
        question: str,
        metadata: Optional[Dict] = None
    ) -> AnalysisRecommendation:
        """
        推荐合适的分析方法
        
        Args:
            df: 输入数据
            question: 用户问题
            metadata: 元数据
            
        Returns:
            分析建议
        """
        pass
    
    def interpret_results(
        self,
        results: Dict[str, Any],
        analysis_type: str
    ) -> str:
        """
        解释分析结果
        
        Args:
            results: 分析结果
            analysis_type: 分析类型
            
        Returns:
            自然语言解释
        """
        pass
```

---

### 2.7 错误修正器 (ErrorCorrector)

**职责**：
- 分析查询执行错误
- 使用 LLM 生成修正方案
- 自动修正查询计划
- 管理重试策略

**接口设计**：
```python
from typing import Optional, List
from dataclasses import dataclass

@dataclass
class CorrectionStrategy:
    """修正策略"""
    strategy_type: str  # field_replacement, aggregation_change, simplification
    description: str
    modified_query_plan: QueryPlanningResult

class ErrorCorrector:
    """错误修正器"""
    
    def __init__(self, llm, metadata_manager, validator):
        self.llm = llm
        self.metadata_manager = metadata_manager
        self.validator = validator
    
    async def analyze_and_correct(
        self,
        error: Exception,
        query_plan: QueryPlanningResult,
        datasource_luid: str,
        attempt: int = 1
    ) -> Optional[CorrectionStrategy]:
        """
        分析错误并生成修正策略
        
        Args:
            error: 执行错误
            query_plan: 原始查询计划
            datasource_luid: 数据源 LUID
            attempt: 当前尝试次数
            
        Returns:
            修正策略，如果无法修正则返回 None
        """
        # 1. 提取错误信息
        error_info = self._extract_error_info(error)
        
        # 2. 获取元数据
        metadata = await self.metadata_manager.get_metadata(datasource_luid)
        
        # 3. 使用 LLM 分析错误
        correction_prompt = self._build_correction_prompt(
            error_info,
            query_plan,
            metadata,
            attempt
        )
        
        correction_response = await self.llm.ainvoke(correction_prompt)
        
        # 4. 解析修正方案
        strategy = self._parse_correction_response(correction_response)
        
        # 5. 验证修正后的查询计划
        if strategy:
            validation_result = await self.validator.validate_query_plan(
                strategy.modified_query_plan,
                datasource_luid
            )
            
            if not validation_result.is_valid:
                # 修正方案仍然有问题，尝试下一个策略
                return None
        
        return strategy
    
    def _extract_error_info(self, error: Exception) -> Dict:
        """提取错误信息"""
        return {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "error_details": getattr(error, "details", None)
        }
    
    def _build_correction_prompt(
        self,
        error_info: Dict,
        query_plan: QueryPlanningResult,
        metadata: Dict,
        attempt: int
    ) -> str:
        """构建修正提示"""
        return f"""
你是一个 VizQL 查询错误修正专家。

**错误信息**：
- 类型：{error_info['error_type']}
- 消息：{error_info['error_message']}

**原始查询计划**：
{query_plan.model_dump_json(indent=2)}

**可用元数据**：
{json.dumps(metadata, indent=2, ensure_ascii=False)}

**当前尝试次数**：{attempt}/3

请分析错误原因，并提供修正方案。修正方案应该：
1. 明确说明错误原因
2. 提供修正后的查询计划（JSON 格式）
3. 说明修正策略类型（field_replacement, aggregation_change, simplification）

如果是第 3 次尝试，请提供最简化的查询方案。
"""
    
    def _parse_correction_response(self, response: str) -> Optional[CorrectionStrategy]:
        """解析 LLM 的修正响应"""
        # 简化实现，实际需要更复杂的解析逻辑
        try:
            # 假设 LLM 返回 JSON 格式
            data = json.loads(response)
            return CorrectionStrategy(
                strategy_type=data["strategy_type"],
                description=data["description"],
                modified_query_plan=QueryPlanningResult(**data["modified_query_plan"])
            )
        except Exception:
            return None
```

---

### 2.5 上下文智能管理 【增强】

**为什么需要？**
- **当前问题**：元数据直接传递给 LLM，没有过滤，Token 消耗高
- **解决方案**：基于 Category 过滤元数据，减少 Token 消耗 50%

**优化策略**：

1. **元数据过滤**（新增）：
   - 从 Understanding 结果中提取涉及的 Category
   - 只保留相关 Category 的维度字段
   - 保留所有度量字段
   - 在 `MetadataManager.get_metadata()` 中添加过滤参数

2. **对话历史压缩**（新增）：
   - 保留最近 5 轮完整对话
   - 压缩早期对话为摘要（使用 LLM）
   - 摘要长度不超过原内容的 30%
   - 在 `vizql_workflow.py` 中实现

3. **Token 预算管理**（新增）：
   - 设置总 Token 预算（默认 8000）
   - 使用 `tiktoken` 准确计算 Token 数量
   - 按优先级裁剪上下文（元数据 > 对话历史 > 示例）

**实现方式**：
- 在 `MetadataManager` 中添加 `filter_by_categories()` 方法
- 在 `BaseAgent` 中添加 `compress_history()` 方法
- 使用 `tiktoken` 库计算 Token 数量

---


## 6. Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. 
Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

基于需求文档中的验收标准，我们定义以下正确性属性：

### 6.1 工具注册与调用属性

**Property 1: 工具注册后可检索**
*For any* 工具实例，当注册到工具注册表后，应该能够通过工具名称和分类检索到该工具
**Validates: Requirements 1.3**

**Property 2: 工具调用失败返回结构化错误**
*For any* 会导致失败的工具调用，系统应该返回包含 error_type, error_message, suggestions, retry_count 的结构化错误信息
**Validates: Requirements 1.7**

**Property 3: 工具调用记录完整性**
*For any* 工具调用，SQLiteTrackingCallback 应该记录工具名称、输入参数、输出结果、耗时、成功/失败状态
**Validates: Requirements 1.9**

**Property 4: 缓存一致性**
*For any* 查询，第一次执行后缓存，第二次执行应该返回相同的结果且标记为 cached=True
**Validates: Requirements 1.5, 1.10**

### 6.2 任务调度属性

**Property 5: 任务依赖顺序正确性**
*For any* 任务列表（包含依赖关系），任务调度器执行的顺序应该满足：如果任务 A 依赖任务 B，则 B 必须在 A 之前执行
**Validates: Requirements 1.4**

**Property 6: 并行任务不超过并发限制**
*For any* 时刻，正在执行的并行任务数量不应该超过 max_concurrent 设置
**Validates: Requirements 1.4**

**Property 7: 所有任务都被执行**
*For any* 任务列表，调度器应该执行所有任务（无论成功或失败），返回的结果数量应该等于任务数量
**Validates: Requirements 1.4**

### 6.3 查询验证属性

**Property 8: 不存在字段被检测**
*For any* 包含不存在字段的查询计划，验证器应该返回 is_valid=False 并包含 field_not_found 类型的错误
**Validates: Requirements 2.1**

**Property 9: 相似字段搜索有效性**
*For any* 拼写错误的字段名（与真实字段名相似度 > 0.6），验证器应该在 suggestions 中包含正确的字段名
**Validates: Requirements 2.2**

**Property 10: 聚合函数类型检查**
*For any* 不合法的聚合函数组合（如对字符串字段使用 SUM），验证器应该返回 invalid_aggregation 类型的错误
**Validates: Requirements 2.3**

### 6.4 错误修正属性

**Property 11: 重试次数限制**
*For any* 查询执行，如果持续失败，系统应该最多重试 3 次，然后返回详细错误信息
**Validates: Requirements 2.5**

**Property 12: 修正记录完整性**
*For any* 成功的修正，系统应该记录修正前的查询计划、修正后的查询计划、修正原因
**Validates: Requirements 2.7**

**Property 13: 错误统计准确性**
*For any* 一批查询执行（包含各种错误类型），错误统计应该准确反映每种错误类型的数量和修正成功率
**Validates: Requirements 2.8**

### 6.5 上下文管理属性

**Property 14: Category 过滤正确性**
*For any* 包含特定 Category 的查询，元数据提供器应该只返回该 Category 的维度字段和所有度量字段
**Validates: Requirements 3.3**

**Property 15: Token 计算准确性**
*For any* 上下文数据，使用 tiktoken 计算的 Token 数量应该与实际发送给 LLM 的 Token 数量误差在 5% 以内
**Validates: Requirements 3.4**

**Property 16: Token 预算遵守**
*For any* 上下文分配，最终使用的总 Token 数量不应该超过设定的 Token 预算
**Validates: Requirements 3.5**

**Property 17: 对话历史压缩率**
*For any* 对话历史压缩，压缩后的长度应该不超过原内容的 30%
**Validates: Requirements 3.6**

**Property 18: 上下文记录完整性**
*For any* 上下文分配，应该记录每个提供器的 Token 消耗、裁剪的内容、过滤前后的字段数量
**Validates: Requirements 3.7**

**Property 19: Token 消耗优化效果**
*For any* 相同的查询，使用上下文管理后的 Token 消耗应该比不使用时减少至少 30%
**Validates: Requirements 3.8**

### 6.6 会话管理属性

**Property 20: 会话 ID 唯一性**
*For any* 创建的会话，session_id 应该是唯一的（UUID 格式）
**Validates: Requirements 4.2**

**Property 21: 会话持久化完整性**
*For any* 会话，保存后应该持久化完整的状态、对话历史、工具调用记录、性能指标
**Validates: Requirements 4.3**

**Property 22: 会话恢复一致性（Round-trip）**
*For any* 会话，保存后立即恢复应该得到完全相同的状态
**Validates: Requirements 4.4**

**Property 23: 会话列表完整性**
*For any* 用户，列出会话应该返回该用户创建的所有会话
**Validates: Requirements 4.5**

**Property 24: 会话搜索正确性**
*For any* 搜索条件（时间范围、关键词、数据源、状态），搜索结果应该只包含满足所有条件的会话
**Validates: Requirements 4.6**

**Property 25: 会话删除完整性**
*For any* 会话，删除后应该从 Checkpointer、Store、工具调用记录中完全移除
**Validates: Requirements 4.7**

**Property 26: 会话导出完整性**
*For any* 会话，导出的 JSON 应该包含完整的对话历史、所有状态变化、工具调用记录、性能指标
**Validates: Requirements 4.8**

---

## 7. Error Handling

### 7.1 错误分类

```python
class ErrorCategory(Enum):
    """错误分类"""
    VALIDATION_ERROR = "validation"  # 验证错误
    EXECUTION_ERROR = "execution"    # 执行错误
    TIMEOUT_ERROR = "timeout"        # 超时错误
    NETWORK_ERROR = "network"        # 网络错误
    PERMISSION_ERROR = "permission"  # 权限错误
    RESOURCE_ERROR = "resource"      # 资源错误
```

### 7.2 错误处理策略

| 错误类型 | 处理策略 | 重试次数 | 降级方案 |
|---------|---------|---------|---------|
| 字段不存在 | 自动修正（相似字段） | 3 | 返回建议 |
| 聚合函数错误 | 自动修正（建议函数） | 3 | 返回建议 |
| VizQL 语法错误 | LLM 分析修正 | 3 | 简化查询 |
| 查询超时 | 简化查询 | 2 | 返回部分结果 |
| 网络错误 | 指数退避重试 | 5 | 使用缓存 |
| 权限错误 | 不重试 | 0 | 返回错误 |

### 7.3 错误恢复流程

```python
async def execute_with_recovery(
    query_plan: QueryPlanningResult,
    max_retries: int = 3
) -> QueryResult:
    """带错误恢复的查询执行"""
    
    for attempt in range(1, max_retries + 1):
        try:
            # 1. 验证查询计划
            validation_result = await validator.validate(query_plan)
            if not validation_result.is_valid:
                # 尝试自动修正
                query_plan = await corrector.auto_fix(
                    query_plan, 
                    validation_result.errors
                )
            
            # 2. 执行查询
            result = await executor.execute(query_plan)
            return result
            
        except ValidationError as e:
            if attempt < max_retries:
                # 使用 LLM 分析并修正
                strategy = await corrector.analyze_and_correct(
                    e, query_plan, attempt
                )
                if strategy:
                    query_plan = strategy.modified_query_plan
                else:
                    raise
            else:
                raise
                
        except ExecutionError as e:
            if attempt < max_retries:
                # 简化查询
                query_plan = await simplify_query(query_plan)
            else:
                raise
                
        except TimeoutError as e:
            if attempt < max_retries:
                # 减少数据量
                query_plan = await reduce_data_scope(query_plan)
            else:
                # 返回部分结果
                return await get_partial_results(query_plan)
```

---

## 8. Testing Strategy

### 8.1 测试方法

我们采用**双重测试策略**：

1. **单元测试（Unit Tests）**：
   - 验证具体示例和边缘情况
   - 测试集成点
   - 快速反馈

2. **属性测试（Property-Based Tests）**：
   - 验证通用属性
   - 覆盖大量输入组合
   - 发现意外边缘情况

### 8.2 属性测试框架

使用 **Hypothesis** 作为 Python 的属性测试库：

```python
from hypothesis import given, strategies as st
import hypothesis

# 配置
hypothesis.settings.register_profile("ci", max_examples=100)
hypothesis.settings.load_profile("ci")

# 示例：测试工具注册属性
@given(
    tool_name=st.text(min_size=1, max_size=50),
    category=st.sampled_from(["metadata", "query", "validation"])
)
def test_tool_registration_retrieval(tool_name, category):
    """
    Property 1: 工具注册后可检索
    Feature: tableau-assistant-enhancement, Property 1
    """
    # 创建模拟工具
    tool = create_mock_tool(tool_name)
    
    # 注册工具
    registry = ToolRegistry()
    registry.register(tool, category)
    
    # 验证可以检索
    retrieved_tool = registry.get_tool(tool_name)
    assert retrieved_tool is not None
    assert retrieved_tool.name == tool_name
    
    # 验证可以按分类检索
    category_tools = registry.get_tools_by_category(category)
    assert tool in category_tools
```

### 8.3 测试覆盖目标

| 组件 | 单元测试覆盖率 | 属性测试数量 | 集成测试 |
|------|--------------|-------------|---------|
| 工具注册表 | 90% | 3 | 2 |
| 任务调度器 | 85% | 4 | 3 |
| 查询验证器 | 90% | 3 | 2 |
| 错误修正器 | 80% | 3 | 2 |
| 上下文管理 | 85% | 6 | 2 |
| 会话管理 | 90% | 7 | 3 |

### 8.4 测试数据生成策略

使用 Hypothesis 的策略生成测试数据：

```python
# 查询计划策略
@st.composite
def query_plan_strategy(draw):
    """生成随机查询计划"""
    num_subtasks = draw(st.integers(min_value=1, max_value=10))
    subtasks = []
    
    for i in range(num_subtasks):
        subtask = QuerySubTask(
            task_id=f"r1_q{i}",
            question_text=draw(st.text(min_size=10, max_size=100)),
            intents=draw(st.lists(
                intent_strategy(), 
                min_size=1, 
                max_size=5
            )),
            depends_on=draw(st.one_of(
                st.none(),
                st.lists(st.sampled_from([f"r1_q{j}" for j in range(i)]))
            ))
        )
        subtasks.append(subtask)
    
    return QueryPlanningResult(subtasks=subtasks)

# 元数据策略
@st.composite
def metadata_strategy(draw):
    """生成随机元数据"""
    num_fields = draw(st.integers(min_value=5, max_value=50))
    fields = []
    
    for i in range(num_fields):
        field = {
            "name": draw(st.text(min_size=3, max_size=20)),
            "dataType": draw(st.sampled_from(["integer", "real", "string", "date"])),
            "role": draw(st.sampled_from(["dimension", "measure"])),
            "category": draw(st.sampled_from(["产品", "地区", "时间", "客户"]))
        }
        fields.append(field)
    
    return {"fields": fields}
```

---

## 9. Performance Considerations

### 9.1 性能目标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| 查询成功率 | 70% | 90% | +20-30% |
| Token 消耗 | 100% | 50% | -50% |
| 缓存命中时查询速度 | 5s | 0.1s | 50x |
| 重规划时查询速度 | 15s | 0.1s | 150x |
| 并发任务执行 | 串行 | 3并发 | 3x |

### 9.2 优化策略

1. **查询结果缓存**：
   - 使用 PersistentStore 缓存查询结果
   - TTL 1-2 小时
   - 基于查询内容的哈希键
   - 预期缓存命中率：60-70%

2. **并行任务执行**：
   - 使用 asyncio 并行执行独立任务
   - 最大并发数：3
   - 预期加速：2-3x

3. **上下文智能过滤**：
   - 基于 Category 过滤元数据
   - 只保留相关字段
   - 预期 Token 减少：50%

4. **对话历史压缩**：
   - 保留最近 5 轮完整对话
   - 压缩早期对话为摘要
   - 预期压缩率：70%

### 9.3 监控指标

```python
class PerformanceMetrics(BaseModel):
    """性能指标"""
    # 查询指标
    total_queries: int
    successful_queries: int
    failed_queries: int
    avg_query_time: float
    
    # 缓存指标
    cache_hits: int
    cache_misses: int
    cache_hit_rate: float
    
    # Token 指标
    total_tokens_used: int
    avg_tokens_per_query: int
    token_reduction_rate: float
    
    # 错误修正指标
    total_corrections: int
    successful_corrections: int
    correction_success_rate: float
    avg_retries: float
    
    # 任务调度指标
    total_tasks: int
    parallel_tasks: int
    serial_tasks: int
    avg_task_time: float
```

---

## 10. Deployment Considerations

### 10.1 配置管理

```python
class SystemConfig(BaseModel):
    """系统配置"""
    # 任务调度配置
    max_concurrent_tasks: int = 3
    task_timeout_seconds: int = 30
    
    # 缓存配置
    query_cache_ttl_hours: int = 2
    metadata_cache_ttl_hours: int = 1
    
    # Token 配置
    token_budget: int = 8000
    max_context_tokens: int = 6000
    
    # 重试配置
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    
    # 会话配置
    session_expiry_days: int = 30
    checkpoint_db_path: str = "data/checkpoints.db"
```

### 10.2 数据库迁移

```sql
-- 查询结果缓存表
CREATE TABLE IF NOT EXISTS query_cache (
    cache_key TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    result JSON NOT NULL,
    timestamp DATETIME NOT NULL,
    expires_at DATETIME NOT NULL
);

-- 工具调用记录表
CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    input_params JSON NOT NULL,
    output_result JSON,
    execution_time REAL NOT NULL,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    timestamp DATETIME NOT NULL
);

-- 错误修正记录表
CREATE TABLE IF NOT EXISTS correction_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    strategy_type TEXT NOT NULL,
    description TEXT NOT NULL,
    original_plan JSON NOT NULL,
    modified_plan JSON,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    timestamp DATETIME NOT NULL
);
```

### 10.3 监控和告警

```python
# 监控指标收集
async def collect_metrics():
    """收集性能指标"""
    metrics = PerformanceMetrics(
        total_queries=await get_total_queries(),
        successful_queries=await get_successful_queries(),
        cache_hit_rate=await get_cache_hit_rate(),
        # ... 其他指标
    )
    
    # 检查告警条件
    if metrics.cache_hit_rate < 0.3:
        await send_alert("缓存命中率过低")
    
    if metrics.correction_success_rate < 0.5:
        await send_alert("错误修正成功率过低")
    
    return metrics
```

---

## 11. 累积洞察和重规划设计

### 11.1 累积洞察 Agent (Insight Agent)

**位置**：`tableau_assistant/src/agents/insight_agent.py`

**职责**：
- 分析单个查询结果
- 提取关键发现
- 生成结构化洞察

**接口设计**：
```python
class InsightAgent(BaseVizQLAgent):
    """洞察分析 Agent"""
    
    async def analyze(
        self,
        task_result: TaskResult,
        context: Dict[str, Any]
    ) -> Insight:
        """
        分析单个查询结果
        
        Args:
            task_result: 查询结果
            context: 上下文信息（问题、元数据等）
        
        Returns:
            Insight: 结构化洞察
        """
        # 准备输入数据
        input_data = {
            "question": context["question"],
            "data": task_result.data,
            "metadata": context["metadata"]
        }
        
        # 调用 LLM 分析
        result = await self.execute(input_data)
        
        return result
```

**输出模型**：
```python
class Insight(BaseModel):
    """洞察结构"""
    task_id: str
    key_finding: str  # 关键发现
    metrics: Dict[str, float]  # 关键指标
    comparison: Optional[str]  # 对比分析
    anomaly: Optional[str]  # 异常发现
    confidence: float  # 置信度
```

### 11.2 洞察协调器 (Insight Coordinator)

**位置**：`tableau_assistant/src/agents/insight_coordinator.py`

**职责**：
- 收集所有洞察
- 识别关键发现
- 智能合成最终洞察

**接口设计**：
```python
class InsightCoordinator(BaseVizQLAgent):
    """洞察协调器"""
    
    async def synthesize(
        self,
        insights: List[Insight],
        context: Dict[str, Any]
    ) -> FinalInsight:
        """
        智能合成洞察
        
        Args:
            insights: 所有洞察列表
            context: 上下文信息
        
        Returns:
            FinalInsight: 最终洞察
        """
        # 准备输入数据
        input_data = {
            "question": context["question"],
            "insights": [i.model_dump() for i in insights],
            "metadata": context["metadata"]
        }
        
        # 调用 LLM 合成
        result = await self.execute(input_data)
        
        return result
```

**输出模型**：
```python
class FinalInsight(BaseModel):
    """最终洞察"""
    executive_summary: str  # 执行摘要
    key_findings: List[str]  # 关键发现列表
    comparisons: List[str]  # 对比分析列表
    anomalies: List[str]  # 异常发现列表
    recommendations: List[str]  # 建议列表
    confidence: float  # 整体置信度
```

### 11.3 重规划 Agent (Replan Agent)

**位置**：`tableau_assistant/src/agents/replan_agent.py`

**职责**：
- 判断是否充分回答问题
- 生成新问题（如果需要重规划）
- 决定是否继续分析

**接口设计**：
```python
class ReplanAgent(BaseVizQLAgent):
    """重规划 Agent"""
    
    async def decide(
        self,
        question: str,
        final_insight: FinalInsight,
        current_round: int,
        max_rounds: int = 3
    ) -> ReplanDecision:
        """
        判断是否需要重规划
        
        Args:
            question: 原始问题
            final_insight: 当前轮的最终洞察
            current_round: 当前轮次
            max_rounds: 最大轮次
        
        Returns:
            ReplanDecision: 重规划决策
        """
        # 准备输入数据
        input_data = {
            "question": question,
            "final_insight": final_insight.model_dump(),
            "current_round": current_round,
            "max_rounds": max_rounds
        }
        
        # 调用 LLM 判断
        result = await self.execute(input_data)
        
        return result
```

**输出模型**：
```python
class ReplanDecision(BaseModel):
    """重规划决策"""
    need_replan: bool  # 是否需要重规划
    reason: str  # 原因
    new_question: Optional[str]  # 新问题（如果需要重规划）
    focus_areas: Optional[List[str]]  # 关注领域
    confidence: float  # 决策置信度
```

### 11.4 工作流集成

**在 vizql_workflow.py 中添加节点**：
```python
def create_vizql_workflow():
    graph = StateGraph(...)
    
    # 添加任务调度节点
    graph.add_node("task_scheduling", task_scheduling_node)
    
    # 添加累积洞察节点
    graph.add_node("accumulate_insights", accumulate_insights_node)
    
    # 添加重规划节点
    graph.add_node("replan", replan_node)
    
    # 连接节点
    graph.add_edge("planning", "task_scheduling")
    graph.add_edge("task_scheduling", "accumulate_insights")
    graph.add_edge("accumulate_insights", "replan")
    
    # 重规划条件边
    graph.add_conditional_edges(
        "replan",
        should_replan,
        {
            "continue": "understanding",  # 重规划：回到 Understanding
            "finish": "summary"  # 完成：进入 Summary
        }
    )
```

**累积洞察节点实现**：
```python
async def accumulate_insights_node(
    state: VizQLState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """累积洞察节点"""
    # 获取任务结果
    task_results = state["task_results"]
    
    # 并行分析每个结果
    insight_agent = InsightAgent()
    insights = await asyncio.gather(*[
        insight_agent.analyze(result, {
            "question": state["question"],
            "metadata": state["metadata"]
        })
        for result in task_results.values()
    ])
    
    # 智能合成洞察
    coordinator = InsightCoordinator()
    final_insight = await coordinator.synthesize(insights, {
        "question": state["question"],
        "metadata": state["metadata"]
    })
    
    return {
        "insights": insights,
        "final_insight": final_insight
    }
```

**重规划节点实现**：
```python
async def replan_node(
    state: VizQLState,
    config: RunnableConfig
) -> Dict[str, Any]:
    """重规划节点"""
    # 获取当前轮次
    current_round = state.get("current_round", 1)
    max_rounds = config["configurable"].get("max_replan_rounds", 3)
    
    # 判断是否需要重规划
    replan_agent = ReplanAgent()
    decision = await replan_agent.decide(
        question=state["question"],
        final_insight=state["final_insight"],
        current_round=current_round,
        max_rounds=max_rounds
    )
    
    return {
        "replan_decision": decision,
        "current_round": current_round + 1 if decision.need_replan else current_round
    }
```

---

## 12. Migration Path

### 11.1 从当前系统迁移

**阶段 1：工具系统重构（2周）**
- 将现有工具迁移到 LangChain Tool 接口
- 建立工具注册表
- 保持向后兼容

**阶段 2：任务调度器实现（2周）**
- 实现任务调度器
- 实现查询结果缓存
- 集成到现有工作流

**阶段 3：查询验证和修正（2周）**
- 实现查询验证器
- 实现错误修正器
- 集成重试机制

**阶段 4：上下文管理优化（2周）**
- 实现上下文提供器系统
- 实现 Token 预算管理
- 实现对话历史压缩

**阶段 5：会话管理完善（1周）**
- 配置 SQLite Checkpointer
- 实现会话管理 API
- 数据迁移

### 11.2 兼容性保证

- 保持现有 API 接口不变
- 新功能通过配置开关控制
- 支持渐进式迁移
- 提供回滚机制

---

## 12. Future Enhancements

### 12.1 短期（3-6个月）

- 支持更多数据源类型
- 优化 LLM 提示词
- 增强错误分析能力
- 支持自定义工具

### 12.2 中期（6-12个月）

- 支持更复杂的累积洞察分析
- 优化重规划策略
- 实现智能数据分块
- 支持查询优化建议

### 12.3 长期（12个月+）

- 支持多模态输入（图表、图片）
- 实现自动化测试生成
- 支持分布式任务调度
- 实现智能查询推荐

---

**文档版本**: 1.0  
**创建时间**: 2025-11-20  
**作者**: Kiro AI Assistant  
**状态**: 待审核


---

## 13. 数据处理器详细实现

### 13.1 数据模型更新

**从 Polars 到 pandas 的数据模型迁移**：

```python
# 旧模型（Polars）
from pydantic import BaseModel
import polars as pl

class QueryResult(BaseModel):
    task_id: str
    data: pl.DataFrame  # Polars DataFrame
    row_count: int
    columns: List[str]
    
    class Config:
        arbitrary_types_allowed = True

# 新模型（pandas）
import pandas as pd

class QueryResult(BaseModel):
    task_id: str
    data: pd.DataFrame  # pandas DataFrame
    row_count: int
    columns: List[str]
    
    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            pd.DataFrame: lambda df: df.to_dict(orient='records')
        }
```

### 13.2 处理器工厂模式更新

```python
from enum import Enum
from typing import Dict, Type

class ProcessingType(Enum):
    """处理类型枚举"""
    # 基础处理
    YOY = "yoy"
    MOM = "mom"
    GROWTH_RATE = "growth_rate"
    PERCENTAGE = "percentage"
    CUSTOM = "custom"
    
    # 派生指标
    MOVING_AVERAGE = "moving_average"
    CUMULATIVE = "cumulative"
    RANKING = "ranking"
    RFM = "rfm"
    
    # 数据画像
    DATA_PROFILE = "data_profile"
    CORRELATION = "correlation"
    OUTLIER_DETECTION = "outlier_detection"
    
    # 统计分析
    HYPOTHESIS_TEST = "hypothesis_test"
    REGRESSION = "regression"
    
    # 时间序列
    TS_DECOMPOSE = "ts_decompose"
    TS_FORECAST_ARIMA = "ts_forecast_arima"
    TS_FORECAST_PROPHET = "ts_forecast_prophet"
    
    # 机器学习
    CLUSTERING = "clustering"
    CLASSIFICATION = "classification"
    ANOMALY_DETECTION = "anomaly_detection"

class ProcessorFactory:
    """处理器工厂"""
    
    def __init__(self):
        self._processors: Dict[ProcessingType, Type[BaseProcessor]] = {}
        self._register_default_processors()
    
    def _register_default_processors(self):
        """注册默认处理器"""
        # 基础处理器
        self.register(ProcessingType.YOY, YoYProcessor)
        self.register(ProcessingType.MOM, MoMProcessor)
        self.register(ProcessingType.PERCENTAGE, PercentageProcessor)
        self.register(ProcessingType.CUSTOM, CustomProcessor)
        
        # 派生指标处理器
        self.register(ProcessingType.MOVING_AVERAGE, MovingAverageProcessor)
        self.register(ProcessingType.CUMULATIVE, CumulativeProcessor)
        self.register(ProcessingType.RANKING, RankingProcessor)
        self.register(ProcessingType.RFM, RFMProcessor)
        
        # 数据画像处理器
        self.register(ProcessingType.DATA_PROFILE, DataProfilingProcessor)
        self.register(ProcessingType.CORRELATION, CorrelationProcessor)
        
        # 时间序列处理器
        self.register(ProcessingType.TS_FORECAST_ARIMA, ARIMAProcessor)
        self.register(ProcessingType.TS_FORECAST_PROPHET, ProphetProcessor)
        
        # 机器学习处理器
        self.register(ProcessingType.CLUSTERING, ClusteringProcessor)
```



### 13.3 基础处理器迁移示例

**YoY 处理器（同比分析）**：

```python
import pandas as pd
from typing import Dict
from datetime import datetime

class YoYProcessor(BaseProcessor):
    """同比分析处理器（pandas 版本）"""
    
    def process(
        self,
        source_data: Dict[str, pd.DataFrame],
        instruction: ProcessingInstruction
    ) -> pd.DataFrame:
        """
        执行同比分析
        
        输入示例：
        | date       | category | sales |
        |------------|----------|-------|
        | 2023-01-01 | A        | 100   |
        | 2024-01-01 | A        | 120   |
        
        输出示例：
        | date       | category | sales | yoy_growth | yoy_rate |
        |------------|----------|-------|------------|----------|
        | 2024-01-01 | A        | 120   | 20         | 20.0%    |
        """
        # 获取源数据
        source_task_id = instruction.source_tasks[0]
        df = source_data[source_task_id].copy()
        
        # 提取参数
        date_col = instruction.parameters.get("date_column")
        value_col = instruction.parameters.get("value_column")
        group_cols = instruction.parameters.get("group_columns", [])
        
        # 确保日期列是 datetime 类型
        df[date_col] = pd.to_datetime(df[date_col])
        
        # 提取年份
        df['year'] = df[date_col].dt.year
        
        # 按分组和年份聚合
        if group_cols:
            agg_df = df.groupby(group_cols + ['year'])[value_col].sum().reset_index()
        else:
            agg_df = df.groupby('year')[value_col].sum().reset_index()
        
        # 计算同比
        if group_cols:
            agg_df = agg_df.sort_values(group_cols + ['year'])
            agg_df['yoy_growth'] = agg_df.groupby(group_cols)[value_col].diff()
            agg_df['yoy_rate'] = (
                agg_df.groupby(group_cols)[value_col].pct_change() * 100
            )
        else:
            agg_df = agg_df.sort_values('year')
            agg_df['yoy_growth'] = agg_df[value_col].diff()
            agg_df['yoy_rate'] = agg_df[value_col].pct_change() * 100
        
        # 格式化百分比
        agg_df['yoy_rate_formatted'] = agg_df['yoy_rate'].apply(
            lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A"
        )
        
        return agg_df
```

### 13.4 派生指标处理器实现

**移动平均处理器**：

```python
class MovingAverageProcessor(BaseProcessor):
    """移动平均处理器"""
    
    def process(
        self,
        source_data: Dict[str, pd.DataFrame],
        instruction: ProcessingInstruction
    ) -> pd.DataFrame:
        """
        计算移动平均
        
        支持：
        - 简单移动平均（SMA）
        - 指数移动平均（EMA）
        - 加权移动平均（WMA）
        """
        source_task_id = instruction.source_tasks[0]
        df = source_data[source_task_id].copy()
        
        # 提取参数
        value_col = instruction.parameters.get("value_column")
        window = instruction.parameters.get("window", 7)
        ma_type = instruction.parameters.get("type", "sma")  # sma, ema, wma
        group_cols = instruction.parameters.get("group_columns", [])
        
        # 计算移动平均
        if ma_type == "sma":
            # 简单移动平均
            if group_cols:
                df[f'ma_{window}'] = (
                    df.groupby(group_cols)[value_col]
                    .rolling(window=window, min_periods=1)
                    .mean()
                    .reset_index(level=group_cols, drop=True)
                )
            else:
                df[f'ma_{window}'] = (
                    df[value_col]
                    .rolling(window=window, min_periods=1)
                    .mean()
                )
        
        elif ma_type == "ema":
            # 指数移动平均
            if group_cols:
                df[f'ema_{window}'] = (
                    df.groupby(group_cols)[value_col]
                    .ewm(span=window, adjust=False)
                    .mean()
                    .reset_index(level=group_cols, drop=True)
                )
            else:
                df[f'ema_{window}'] = (
                    df[value_col]
                    .ewm(span=window, adjust=False)
                    .mean()
                )
        
        return df
```



### 13.5 与现有系统集成

**集成点 1：QueryExecutor**

```python
class QueryExecutor:
    """查询执行器（已有）"""
    
    def __init__(self):
        self.data_processor = DataProcessor()  # 使用新的数据处理器
    
    async def execute_subtask(
        self,
        subtask: QuerySubTask,
        datasource_luid: str
    ) -> QueryResult:
        """执行查询子任务"""
        # 1. 构建 VizQL 查询
        vizql_query = self.query_builder.build(subtask)
        
        # 2. 执行查询
        raw_result = await self.vds_client.execute(vizql_query)
        
        # 3. 转换为 pandas DataFrame
        df = pd.DataFrame(raw_result['data'])
        
        # 4. 封装为 QueryResult
        return QueryResult(
            task_id=subtask.task_id,
            data=df,  # pandas DataFrame
            row_count=len(df),
            columns=list(df.columns)
        )
```

**集成点 2：DataProcessor**

```python
class DataProcessor:
    """主数据处理器（更新后）"""
    
    def __init__(self):
        self.factory = ProcessorFactory()
        logger.info("DataProcessor initialized with pandas")
    
    def process_subtask(
        self,
        subtask: ProcessingSubTask,
        query_results: Dict[str, QueryResult]
    ) -> ProcessingResult:
        """
        处理单个 ProcessingSubTask
        
        变更：
        - 从 Polars 改为 pandas
        - 支持更多处理类型
        - 增强错误处理
        """
        start_time = time.time()
        
        try:
            # 1. 验证输入
            self._validate_input(subtask, query_results)
            
            # 2. 获取处理指令
            instruction = subtask.processing_instruction
            
            # 3. 创建对应的处理器
            processor = self.factory.create_processor(instruction.processing_type)
            
            # 4. 准备源数据（pandas DataFrame）
            source_data = self._prepare_source_data(
                instruction.source_tasks, 
                query_results
            )
            
            # 5. 执行处理
            result_df = processor.process(source_data, instruction)
            
            # 6. 验证输出
            self._validate_output(result_df)
            
            # 7. 封装结果
            return ProcessingResult(
                task_id=subtask.question_id,
                data=result_df,
                row_count=len(result_df),
                columns=list(result_df.columns),
                processing_type=instruction.processing_type,
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
            
        except Exception as e:
            logger.error(f"Processing failed: {e}", exc_info=True)
            raise ProcessingError(f"Processing failed: {e}")
```

**集成点 3：Agent 调用**

```python
class PlanningAgent(BaseVizQLAgent):
    """规划 Agent（已有）"""
    
    async def plan(
        self,
        understanding_result: UnderstandingResult,
        metadata: Dict
    ) -> QueryPlanningResult:
        """
        生成查询计划
        
        新增：支持数据处理任务的规划
        """
        # ... 现有逻辑 ...
        
        # 新增：如果需要高级数据分析，添加处理子任务
        if self._needs_advanced_analysis(understanding_result):
            processing_subtasks = self._plan_processing_tasks(
                understanding_result,
                query_subtasks
            )
            
            return QueryPlanningResult(
                query_subtasks=query_subtasks,
                processing_subtasks=processing_subtasks  # 新增
            )
    
    def _needs_advanced_analysis(
        self,
        understanding: UnderstandingResult
    ) -> bool:
        """判断是否需要高级分析"""
        keywords = [
            "预测", "forecast", "趋势", "trend",
            "聚类", "cluster", "分群", "segment",
            "相关性", "correlation", "关联", "relationship",
            "异常", "anomaly", "outlier"
        ]
        
        question_lower = understanding.question.lower()
        return any(keyword in question_lower for keyword in keywords)
    
    def _plan_processing_tasks(
        self,
        understanding: UnderstandingResult,
        query_subtasks: List[QuerySubTask]
    ) -> List[ProcessingSubTask]:
        """规划数据处理任务"""
        processing_tasks = []
        
        # 示例：如果问题包含"预测"，添加时间序列预测任务
        if "预测" in understanding.question or "forecast" in understanding.question.lower():
            processing_tasks.append(ProcessingSubTask(
                question_id=f"p_{len(processing_tasks)}",
                question_text="时间序列预测",
                processing_instruction=ProcessingInstruction(
                    processing_type=ProcessingType.TS_FORECAST_PROPHET,
                    source_tasks=[query_subtasks[0].task_id],
                    parameters={
                        "value_column": "sales",
                        "date_column": "date",
                        "periods": 30
                    }
                )
            ))
        
        return processing_tasks
```



### 13.6 智能分析建议集成

**在 Understanding Agent 中集成**：

```python
class UnderstandingAgent(BaseVizQLAgent):
    """理解 Agent（增强）"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.intelligent_advisor = IntelligentAdvisor()
    
    async def understand(
        self,
        question: str,
        metadata: Dict,
        conversation_history: List[Dict]
    ) -> UnderstandingResult:
        """
        理解用户问题
        
        新增：提供智能分析建议
        """
        # 现有逻辑：理解问题
        understanding = await self._analyze_question(question, metadata)
        
        # 新增：如果有初步数据，提供分析建议
        if hasattr(understanding, 'sample_data') and understanding.sample_data is not None:
            recommendations = self.intelligent_advisor.recommend_analysis(
                df=understanding.sample_data,
                question=question,
                metadata=metadata
            )
            understanding.analysis_recommendations = recommendations
        
        return understanding
```

### 13.7 性能优化实现

**分块处理大数据集**：

```python
class DataProcessor:
    """数据处理器（性能优化版）"""
    
    def __init__(self, chunk_size: int = 10000):
        self.factory = ProcessorFactory()
        self.chunk_size = chunk_size
    
    def process_subtask(
        self,
        subtask: ProcessingSubTask,
        query_results: Dict[str, QueryResult]
    ) -> ProcessingResult:
        """处理子任务（支持分块）"""
        instruction = subtask.processing_instruction
        source_data = self._prepare_source_data(
            instruction.source_tasks, 
            query_results
        )
        
        # 检查数据大小
        total_rows = sum(df.shape[0] for df in source_data.values())
        
        if total_rows > self.chunk_size:
            # 大数据集：分块处理
            return self._process_in_chunks(subtask, source_data)
        else:
            # 小数据集：直接处理
            processor = self.factory.create_processor(instruction.processing_type)
            result_df = processor.process(source_data, instruction)
            return self._wrap_result(subtask, result_df)
    
    def _process_in_chunks(
        self,
        subtask: ProcessingSubTask,
        source_data: Dict[str, pd.DataFrame]
    ) -> ProcessingResult:
        """分块处理"""
        instruction = subtask.processing_instruction
        processor = self.factory.create_processor(instruction.processing_type)
        
        # 获取主数据源
        main_task_id = instruction.source_tasks[0]
        main_df = source_data[main_task_id]
        
        # 分块处理
        chunks = []
        for i in range(0, len(main_df), self.chunk_size):
            chunk = main_df.iloc[i:i+self.chunk_size]
            chunk_source = {main_task_id: chunk}
            
            # 处理分块
            chunk_result = processor.process(chunk_source, instruction)
            chunks.append(chunk_result)
            
            # 进度反馈
            progress = (i + len(chunk)) / len(main_df) * 100
            logger.info(f"Processing progress: {progress:.1f}%")
        
        # 合并结果
        result_df = pd.concat(chunks, ignore_index=True)
        return self._wrap_result(subtask, result_df)
```

**向量化操作优化**：

```python
class OptimizedProcessor(BaseProcessor):
    """优化的处理器基类"""
    
    def _calculate_growth_rate(
        self,
        df: pd.DataFrame,
        value_col: str,
        group_cols: List[str] = None
    ) -> pd.Series:
        """
        向量化计算增长率
        
        避免循环，使用 pandas 向量化操作
        """
        if group_cols:
            # 分组计算
            return df.groupby(group_cols)[value_col].pct_change() * 100
        else:
            # 全局计算
            return df[value_col].pct_change() * 100
    
    def _apply_window_function(
        self,
        df: pd.DataFrame,
        value_col: str,
        window_size: int,
        func: str = "mean"
    ) -> pd.Series:
        """
        向量化窗口函数
        
        使用 pandas rolling 而不是循环
        """
        rolling = df[value_col].rolling(window=window_size, min_periods=1)
        
        if func == "mean":
            return rolling.mean()
        elif func == "sum":
            return rolling.sum()
        elif func == "std":
            return rolling.std()
        else:
            raise ValueError(f"Unsupported function: {func}")
```



### 13.8 错误处理和验证

**数据处理器错误处理**：

```python
class DataProcessorError(Exception):
    """数据处理器基础异常"""
    pass

class DataValidationError(DataProcessorError):
    """数据验证错误"""
    pass

class ProcessingExecutionError(DataProcessorError):
    """处理执行错误"""
    pass

class DataProcessor:
    """数据处理器（完整错误处理）"""
    
    def _validate_input(
        self,
        subtask: ProcessingSubTask,
        query_results: Dict[str, QueryResult]
    ) -> None:
        """
        验证输入数据
        
        检查：
        1. 所有依赖任务的结果都存在
        2. 数据不为空
        3. 必需的列存在
        4. 数据类型正确
        """
        instruction = subtask.processing_instruction
        
        # 检查依赖任务
        for task_id in instruction.source_tasks:
            if task_id not in query_results:
                raise DataValidationError(
                    f"Missing source data for task {task_id}"
                )
            
            result = query_results[task_id]
            
            # 检查数据不为空
            if result.data.empty:
                raise DataValidationError(
                    f"Empty data from task {task_id}"
                )
            
            # 检查必需的列
            required_cols = self._get_required_columns(instruction)
            missing_cols = set(required_cols) - set(result.data.columns)
            if missing_cols:
                raise DataValidationError(
                    f"Missing required columns: {missing_cols}"
                )
            
            # 检查数据类型
            self._validate_column_types(result.data, instruction)
    
    def _validate_column_types(
        self,
        df: pd.DataFrame,
        instruction: ProcessingInstruction
    ) -> None:
        """验证列的数据类型"""
        # 根据处理类型验证
        if instruction.processing_type in [
            ProcessingType.MOVING_AVERAGE,
            ProcessingType.CUMULATIVE,
            ProcessingType.YOY
        ]:
            # 需要数值列
            value_col = instruction.parameters.get("value_column")
            if value_col and not pd.api.types.is_numeric_dtype(df[value_col]):
                raise DataValidationError(
                    f"Column {value_col} must be numeric for {instruction.processing_type}"
                )
        
        elif instruction.processing_type in [
            ProcessingType.TS_FORECAST_ARIMA,
            ProcessingType.TS_FORECAST_PROPHET
        ]:
            # 需要日期列
            date_col = instruction.parameters.get("date_column")
            if date_col and not pd.api.types.is_datetime64_any_dtype(df[date_col]):
                # 尝试转换
                try:
                    df[date_col] = pd.to_datetime(df[date_col])
                except Exception as e:
                    raise DataValidationError(
                        f"Column {date_col} cannot be converted to datetime: {e}"
                    )
    
    def _validate_output(self, result: pd.DataFrame) -> None:
        """
        验证输出数据
        
        检查：
        1. 结果不为空
        2. 无 NaN/Inf（对数值列）
        3. 数据完整性
        """
        if result.empty:
            raise ProcessingExecutionError("Processing result is empty")
        
        # 检查数值列
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            # 检查 NaN
            nan_count = result[col].isna().sum()
            if nan_count > 0:
                logger.warning(
                    f"Column {col} contains {nan_count} NaN values"
                )
            
            # 检查 Inf
            if np.isinf(result[col]).any():
                raise ProcessingExecutionError(
                    f"Column {col} contains infinite values"
                )
```

### 13.9 测试策略

**单元测试示例**：

```python
import pytest
import pandas as pd
from tableau_assistant.src.components.data_processor import DataProcessor

class TestMovingAverageProcessor:
    """移动平均处理器测试"""
    
    def test_simple_moving_average(self):
        """测试简单移动平均"""
        # 准备测试数据
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=5),
            'sales': [100, 120, 110, 130, 125]
        })
        
        query_result = QueryResult(
            task_id="q1",
            data=df,
            row_count=5,
            columns=['date', 'sales']
        )
        
        # 创建处理指令
        instruction = ProcessingInstruction(
            processing_type=ProcessingType.MOVING_AVERAGE,
            source_tasks=["q1"],
            parameters={
                "value_column": "sales",
                "window": 3,
                "type": "sma"
            }
        )
        
        # 执行处理
        processor = DataProcessor()
        result = processor.process_subtask(
            ProcessingSubTask(
                question_id="p1",
                question_text="计算3日移动平均",
                processing_instruction=instruction
            ),
            {"q1": query_result}
        )
        
        # 验证结果
        assert 'ma_3' in result.data.columns
        assert len(result.data) == 5
        assert result.data['ma_3'].iloc[2] == pytest.approx(110.0)
    
    def test_exponential_moving_average(self):
        """测试指数移动平均"""
        # ... 类似的测试逻辑 ...
    
    def test_grouped_moving_average(self):
        """测试分组移动平均"""
        # 准备分组数据
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=6).tolist() * 2,
            'category': ['A'] * 6 + ['B'] * 6,
            'sales': [100, 120, 110, 130, 125, 135] * 2
        })
        
        # ... 测试逻辑 ...
```

**属性测试示例**：

```python
from hypothesis import given, strategies as st
import hypothesis

@given(
    window=st.integers(min_value=2, max_value=10),
    data_size=st.integers(min_value=10, max_value=100)
)
def test_moving_average_properties(window, data_size):
    """
    Property: 移动平均的结果长度应该等于输入长度
    Feature: tableau-assistant-enhancement, Property 27
    """
    # 生成随机数据
    df = pd.DataFrame({
        'value': np.random.randn(data_size)
    })
    
    # 计算移动平均
    result = df['value'].rolling(window=window, min_periods=1).mean()
    
    # 验证属性
    assert len(result) == len(df)
    assert not result.isna().all()  # 至少有一些非NaN值
```



---

## 14. 配置和部署指南

### 14.1 依赖包更新

**requirements.txt 更新**：

```txt
# 核心框架（已有）
langchain==0.3.21
langgraph==0.3.21
pydantic==2.x

# 数据处理（更新）
pandas>=2.0.0  # 替代 polars
numpy>=1.24.0
scipy>=1.10.0

# 统计分析
statsmodels>=0.14.0

# 时间序列
prophet>=1.1.0
pmdarima>=2.0.0

# 机器学习
scikit-learn>=1.3.0
xgboost>=2.0.0
lightgbm>=4.0.0

# 可选：深度学习（如果需要 LSTM）
# tensorflow>=2.13.0
# torch>=2.0.0

# 工具
tiktoken>=0.5.0
```

### 14.2 配置文件

**config/data_processor.yaml**：

```yaml
data_processor:
  # 基础配置
  chunk_size: 10000  # 分块处理阈值
  max_memory_mb: 1000  # 最大内存使用
  
  # 性能配置
  use_vectorization: true
  enable_parallel: true
  max_workers: 4
  
  # 缓存配置
  enable_cache: true
  cache_ttl_hours: 2
  
  # 时间序列配置
  time_series:
    arima:
      auto_params: true
      max_p: 5
      max_d: 2
      max_q: 5
    
    prophet:
      yearly_seasonality: true
      weekly_seasonality: true
      daily_seasonality: false
      include_holidays: true
      country: "CN"
  
  # 机器学习配置
  machine_learning:
    clustering:
      auto_select_k: true
      max_clusters: 10
      random_state: 42
    
    classification:
      test_size: 0.3
      cv_folds: 5
      random_state: 42
  
  # 数据画像配置
  profiling:
    include_correlation: true
    outlier_method: "iqr"  # iqr, zscore
    outlier_threshold: 1.5
```

### 14.3 环境变量

**.env 文件**：

```bash
# 数据处理器配置
DATA_PROCESSOR_CHUNK_SIZE=10000
DATA_PROCESSOR_MAX_MEMORY_MB=1000

# 时间序列配置
TS_FORECAST_DEFAULT_PERIODS=30
TS_PROPHET_COUNTRY=CN

# 机器学习配置
ML_RANDOM_STATE=42
ML_MAX_CLUSTERS=10

# 性能配置
ENABLE_PARALLEL_PROCESSING=true
MAX_WORKERS=4
```

### 14.4 数据库迁移脚本

**migrations/001_add_data_processor_tables.sql**：

```sql
-- 数据处理任务表
CREATE TABLE IF NOT EXISTS processing_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT UNIQUE NOT NULL,
    processing_type TEXT NOT NULL,
    parameters JSON NOT NULL,
    status TEXT NOT NULL,  -- pending, running, completed, failed
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    error_message TEXT
);

-- 数据处理结果缓存表
CREATE TABLE IF NOT EXISTS processing_results_cache (
    cache_key TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    processing_type TEXT NOT NULL,
    result JSON NOT NULL,
    row_count INTEGER NOT NULL,
    timestamp DATETIME NOT NULL,
    expires_at DATETIME NOT NULL
);

-- 数据画像缓存表
CREATE TABLE IF NOT EXISTS data_profiles_cache (
    cache_key TEXT PRIMARY KEY,
    datasource_luid TEXT NOT NULL,
    profile JSON NOT NULL,
    timestamp DATETIME NOT NULL,
    expires_at DATETIME NOT NULL
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_processing_tasks_status 
ON processing_tasks(status);

CREATE INDEX IF NOT EXISTS idx_processing_tasks_created 
ON processing_tasks(created_at);

CREATE INDEX IF NOT EXISTS idx_processing_results_expires 
ON processing_results_cache(expires_at);
```

### 14.5 启动脚本

**scripts/migrate_to_pandas.py**：

```python
"""
从 Polars 迁移到 pandas 的脚本
"""
import logging
from pathlib import Path
import pandas as pd
import polars as pl

logger = logging.getLogger(__name__)

def migrate_cached_data():
    """迁移缓存的数据"""
    cache_dir = Path("data/cache")
    
    if not cache_dir.exists():
        logger.info("No cache directory found, skipping migration")
        return
    
    # 查找所有 Polars 缓存文件
    polars_files = list(cache_dir.glob("*.parquet"))
    
    logger.info(f"Found {len(polars_files)} cached files to migrate")
    
    for file_path in polars_files:
        try:
            # 读取 Polars 数据
            pl_df = pl.read_parquet(file_path)
            
            # 转换为 pandas
            pd_df = pl_df.to_pandas()
            
            # 保存为新格式
            new_path = file_path.with_suffix('.pkl')
            pd_df.to_pickle(new_path)
            
            logger.info(f"Migrated: {file_path.name}")
            
            # 删除旧文件（可选）
            # file_path.unlink()
            
        except Exception as e:
            logger.error(f"Failed to migrate {file_path}: {e}")
    
    logger.info("Migration completed")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    migrate_cached_data()
```

### 14.6 健康检查

**health_check.py**：

```python
"""
数据处理器健康检查
"""
import pandas as pd
import numpy as np
from tableau_assistant.src.components.data_processor import DataProcessor

def check_data_processor_health():
    """检查数据处理器健康状态"""
    checks = {
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "processor_initialized": False,
        "basic_operations": False,
        "advanced_operations": False
    }
    
    try:
        # 检查处理器初始化
        processor = DataProcessor()
        checks["processor_initialized"] = True
        
        # 检查基础操作
        test_df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=10),
            'value': np.random.randn(10)
        })
        
        # 测试移动平均
        result = test_df['value'].rolling(window=3).mean()
        checks["basic_operations"] = not result.isna().all()
        
        # 检查高级操作（可选）
        try:
            from prophet import Prophet
            from sklearn.cluster import KMeans
            checks["advanced_operations"] = True
        except ImportError:
            checks["advanced_operations"] = False
        
    except Exception as e:
        checks["error"] = str(e)
    
    return checks

if __name__ == "__main__":
    import json
    health = check_data_processor_health()
    print(json.dumps(health, indent=2))
```

### 14.7 监控和日志

**logging_config.yaml**：

```yaml
version: 1
disable_existing_loggers: false

formatters:
  standard:
    format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
  detailed:
    format: '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'

handlers:
  console:
    class: logging.StreamHandler
    level: INFO
    formatter: standard
    stream: ext://sys.stdout
  
  file:
    class: logging.handlers.RotatingFileHandler
    level: DEBUG
    formatter: detailed
    filename: logs/data_processor.log
    maxBytes: 10485760  # 10MB
    backupCount: 5
  
  error_file:
    class: logging.handlers.RotatingFileHandler
    level: ERROR
    formatter: detailed
    filename: logs/data_processor_errors.log
    maxBytes: 10485760
    backupCount: 5

loggers:
  tableau_assistant.src.components.data_processor:
    level: DEBUG
    handlers: [console, file, error_file]
    propagate: false

root:
  level: INFO
  handlers: [console, file]
```

---

## 15. 总结

### 15.1 设计文档完整性检查

本设计文档已完整覆盖：

✅ **系统架构**
- 当前架构分析
- 增强后的架构
- 核心设计原则

✅ **核心组件设计**
- 任务调度器
- 查询结果缓存
- 增强数据处理器（7个功能模块）
- 查询验证和错误修正
- 上下文智能管理
- 错误修正器

✅ **数据处理器详细设计**
- 从 Polars 到 pandas 的迁移
- 派生指标计算
- 数据画像
- 统计分析
- 时间序列分析
- 机器学习分析
- 智能分析建议

✅ **接口设计**
- 所有处理器的接口定义
- 数据模型定义
- 与现有系统的集成点

✅ **正确性属性**
- 26个可测试的属性
- 覆盖所有需求验收标准

✅ **错误处理**
- 错误分类
- 错误处理策略
- 错误恢复流程

✅ **测试策略**
- 单元测试
- 属性测试
- 集成测试
- 测试覆盖目标

✅ **性能考虑**
- 性能目标
- 优化策略
- 监控指标

✅ **部署指南**
- 配置管理
- 数据库迁移
- 监控和告警
- 健康检查

✅ **累积洞察和重规划**
- Insight Agent
- Insight Coordinator
- Replan Agent
- 工作流集成

### 15.2 下一步行动

现在设计文档已经完善，建议的下一步：

1. **审查设计文档**
   - 请用户审查设计文档
   - 确认技术方案
   - 讨论实施优先级

2. **更新任务列表**
   - 根据设计文档更新 tasks.md
   - 添加数据处理器相关任务
   - 细化实施步骤

3. **开始实施**
   - Phase 1: 基础迁移（Polars → pandas）
   - Phase 2: 派生指标和数据画像
   - Phase 3: 统计和时间序列
   - Phase 4: 机器学习和智能建议

---

**文档版本**: 1.1  
**最后更新**: 2025-11-20  
**作者**: Kiro AI Assistant  
**状态**: 完成，待审核
