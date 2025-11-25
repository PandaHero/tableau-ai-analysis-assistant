# 增强数据处理器详细设计

## 1. 概述

本文档详细描述增强数据处理器的设计，包括从Polars到pandas的迁移策略、新增功能模块的实现方案、以及参考的主流AI数据分析项目。

## 2. 技术栈迁移

### 2.1 从 Polars 到 pandas

**迁移原因**：
- pandas 拥有更丰富的数据科学生态
- 更好的与 scipy、scikit-learn、statsmodels 集成
- 更多的社区支持和文档
- 更成熟的时间序列和统计分析功能

**迁移策略**：
```python
# 旧代码（Polars）
import polars as pl
df = pl.DataFrame(data)
result = df.group_by("category").agg(pl.col("value").sum())

# 新代码（pandas）
import pandas as pd
df = pd.DataFrame(data)
result = df.groupby("category")["value"].sum().reset_index()
```

**性能考虑**：
- pandas 在大数据集上可能比 Polars 慢
- 使用向量化操作优化性能
- 考虑使用 Dask 处理超大数据集（可选）
- 目标：性能不超过 Polars 实现的 2 倍

## 3. 参考项目分析

### 3.1 PandasAI

**核心特点**：
- 使用 LLM 生成 pandas 代码
- 自动数据清洗和预处理
- 智能图表生成
- 支持多种数据源

**借鉴点**：
- 智能分析建议的实现方式
- LLM 驱动的数据分析流程
- 自然语言解释生成

### 3.2 LangChain Data Analysis

**核心特点**：
- 基于 LangChain 的数据分析工具
- 支持 CSV、Excel、SQL 等数据源
- 使用 Agent 执行数据分析任务

**借鉴点**：
- Agent 架构设计
- 工具调用机制
- 错误处理和重试策略

### 3.3 AutoML 项目（Auto-sklearn、TPOT）

**核心特点**：
- 自动特征工程
- 自动模型选择和调参
- 自动评估和比较

**借鉴点**：
- 自动参数选择
- 模型评估指标
- 特征重要性分析

## 4. 派生指标计算器详细设计

### 4.1 移动平均计算器

```python
class MovingAverageCalculator:
    """移动平均计算器"""
    
    def calculate_sma(
        self,
        df: pd.DataFrame,
        value_col: str,
        window: int = 7,
        group_by: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        简单移动平均（Simple Moving Average）
        
        示例：
        输入：
        | date       | product | sales |
        |------------|---------|-------|
        | 2024-01-01 | A       | 100   |
        | 2024-01-02 | A       | 120   |
        | 2024-01-03 | A       | 110   |
        
        输出（window=2）：
        | date       | product | sales | sma_7 |
        |------------|---------|-------|-------|
        | 2024-01-01 | A       | 100   | NaN   |
        | 2024-01-02 | A       | 120   | 110.0 |
        | 2024-01-03 | A       | 110   | 115.0 |
        """
        result = df.copy()
        
        if group_by:
            result[f'sma_{window}'] = (
                df.groupby(group_by)[value_col]
                .rolling(window=window, min_periods=1)
                .mean()
                .reset_index(level=group_by, drop=True)
            )
        else:
            result[f'sma_{window}'] = (
                df[value_col]
                .rolling(window=window, min_periods=1)
                .mean()
            )
        
        return result
    
    def calculate_ema(
        self,
        df: pd.DataFrame,
        value_col: str,
        span: int = 7,
        group_by: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        指数移动平均（Exponential Moving Average）
        
        EMA 对近期数据赋予更高权重
        """
        result = df.copy()
        
        if group_by:
            result[f'ema_{span}'] = (
                df.groupby(group_by)[value_col]
                .ewm(span=span, adjust=False)
                .mean()
                .reset_index(level=group_by, drop=True)
            )
        else:
            result[f'ema_{span}'] = (
                df[value_col]
                .ewm(span=span, adjust=False)
                .mean()
            )
        
        return result
```

### 4.2 RFM 分析计算器

```python
class RFMCalculator:
    """RFM 分析计算器"""
    
    def calculate_rfm(
        self,
        df: pd.DataFrame,
        customer_col: str,
        date_col: str,
        amount_col: str,
        reference_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        计算 RFM 指标
        
        输入：
        | customer_id | order_date | amount |
        |-------------|------------|--------|
        | C001        | 2024-01-01 | 100    |
        | C001        | 2024-01-15 | 200    |
        | C002        | 2024-01-10 | 150    |
        
        输出：
        | customer_id | recency | frequency | monetary | rfm_score |
        |-------------|---------|-----------|----------|-----------|
        | C001        | 5       | 2         | 300      | 523       |
        | C002        | 20      | 1         | 150      | 311       |
        """
        # 确保日期列是 datetime 类型
        df[date_col] = pd.to_datetime(df[date_col])
        
        # 设置参考日期
        if reference_date is None:
            reference_date = df[date_col].max()
        else:
            reference_date = pd.to_datetime(reference_date)
        
        # 计算 RFM
        rfm = df.groupby(customer_col).agg({
            date_col: lambda x: (reference_date - x.max()).days,  # Recency
            customer_col: 'count',  # Frequency
            amount_col: 'sum'  # Monetary
        })
        
        rfm.columns = ['recency', 'frequency', 'monetary']
        
        # 计算 RFM 分数（1-5分）
        rfm['r_score'] = pd.qcut(
            rfm['recency'], 
            q=5, 
            labels=[5, 4, 3, 2, 1],  # 越近越好
            duplicates='drop'
        )
        rfm['f_score'] = pd.qcut(
            rfm['frequency'], 
            q=5, 
            labels=[1, 2, 3, 4, 5],  # 越多越好
            duplicates='drop'
        )
        rfm['m_score'] = pd.qcut(
            rfm['monetary'], 
            q=5, 
            labels=[1, 2, 3, 4, 5],  # 越高越好
            duplicates='drop'
        )
        
        # 组合 RFM 分数
        rfm['rfm_score'] = (
            rfm['r_score'].astype(str) + 
            rfm['f_score'].astype(str) + 
            rfm['m_score'].astype(str)
        )
        
        # 客户分群
        rfm['segment'] = rfm['rfm_score'].apply(self._classify_rfm_segment)
        
        return rfm.reset_index()
    
    def _classify_rfm_segment(self, score: str) -> str:
        """根据 RFM 分数分类客户"""
        r, f, m = int(score[0]), int(score[1]), int(score[2])
        
        if r >= 4 and f >= 4 and m >= 4:
            return "Champions"  # 冠军客户
        elif r >= 3 and f >= 3:
            return "Loyal Customers"  # 忠诚客户
        elif r >= 4:
            return "Potential Loyalists"  # 潜在忠诚客户
        elif f >= 4:
            return "At Risk"  # 流失风险客户
        elif r <= 2:
            return "Lost"  # 已流失客户
        else:
            return "Others"  # 其他客户
```

## 5. 数据画像处理器详细设计

### 5.1 描述性统计

```python
class DescriptiveStatistics:
    """描述性统计"""
    
    def generate_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        生成完整的数据摘要
        
        返回示例：
        {
            "basic_info": {
                "row_count": 1000,
                "column_count": 10,
                "memory_usage_mb": 0.08
            },
            "numeric_fields": {
                "sales": {
                    "count": 1000,
                    "mean": 1250.5,
                    "std": 450.2,
                    "min": 100,
                    "25%": 900,
                    "50%": 1200,
                    "75%": 1500,
                    "max": 3000,
                    "skewness": 0.5,
                    "kurtosis": -0.2,
                    "missing_count": 0,
                    "missing_pct": 0.0
                }
            },
            "categorical_fields": {
                "category": {
                    "unique_count": 5,
                    "top_value": "Electronics",
                    "top_freq": 300,
                    "missing_count": 0
                }
            }
        }
        """
        summary = {
            "basic_info": self._get_basic_info(df),
            "numeric_fields": self._analyze_numeric_fields(df),
            "categorical_fields": self._analyze_categorical_fields(df),
            "datetime_fields": self._analyze_datetime_fields(df)
        }
        
        return summary
    
    def _analyze_numeric_fields(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """分析数值型字段"""
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        result = {}
        
        for col in numeric_cols:
            stats = df[col].describe().to_dict()
            stats.update({
                "skewness": df[col].skew(),
                "kurtosis": df[col].kurtosis(),
                "missing_count": df[col].isna().sum(),
                "missing_pct": df[col].isna().mean() * 100
            })
            result[col] = stats
        
        return result
```

### 5.2 相关性分析

```python
class CorrelationAnalyzer:
    """相关性分析"""
    
    def analyze_correlation(
        self,
        df: pd.DataFrame,
        method: str = "pearson",  # pearson, spearman, kendall
        threshold: float = 0.7
    ) -> Dict[str, Any]:
        """
        分析字段间的相关性
        
        返回：
        {
            "correlation_matrix": DataFrame,
            "high_correlations": [
                ("sales", "profit", 0.85),
                ("price", "cost", 0.92)
            ],
            "heatmap_data": {...}
        }
        """
        # 只选择数值型字段
        numeric_df = df.select_dtypes(include=[np.number])
        
        # 计算相关系数矩阵
        corr_matrix = numeric_df.corr(method=method)
        
        # 找出高相关性字段对
        high_corr = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                corr_value = corr_matrix.iloc[i, j]
                if abs(corr_value) >= threshold:
                    high_corr.append((
                        corr_matrix.columns[i],
                        corr_matrix.columns[j],
                        corr_value
                    ))
        
        return {
            "correlation_matrix": corr_matrix,
            "high_correlations": high_corr,
            "method": method
        }
```

## 6. 时间序列处理器详细设计

### 6.1 ARIMA 预测

```python
from statsmodels.tsa.arima.model import ARIMA
from pmdarima import auto_arima

class ARIMAForecaster:
    """ARIMA 预测器"""
    
    def forecast(
        self,
        df: pd.DataFrame,
        value_col: str,
        date_col: str,
        periods: int = 30,
        auto_params: bool = True
    ) -> ForecastResult:
        """
        使用 ARIMA 进行时间序列预测
        
        步骤：
        1. 数据预处理（排序、设置索引）
        2. 参数选择（自动或手动）
        3. 模型训练
        4. 预测
        5. 评估
        """
        # 1. 数据预处理
        ts_df = df[[date_col, value_col]].copy()
        ts_df[date_col] = pd.to_datetime(ts_df[date_col])
        ts_df = ts_df.sort_values(date_col)
        ts_df = ts_df.set_index(date_col)
        
        # 2. 参数选择
        if auto_params:
            # 使用 auto_arima 自动选择最优参数
            model = auto_arima(
                ts_df[value_col],
                seasonal=False,
                stepwise=True,
                suppress_warnings=True,
                error_action="ignore"
            )
            order = model.order
        else:
            # 使用默认参数
            order = (1, 1, 1)
        
        # 3. 训练模型
        model = ARIMA(ts_df[value_col], order=order)
        fitted_model = model.fit()
        
        # 4. 预测
        forecast = fitted_model.forecast(steps=periods)
        forecast_index = pd.date_range(
            start=ts_df.index[-1] + pd.Timedelta(days=1),
            periods=periods,
            freq='D'
        )
        
        # 5. 计算置信区间
        forecast_df = fitted_model.get_forecast(steps=periods)
        conf_int = forecast_df.conf_int()
        
        # 6. 评估指标
        # 使用最后30%的数据作为测试集
        train_size = int(len(ts_df) * 0.7)
        train = ts_df[:train_size]
        test = ts_df[train_size:]
        
        # 在训练集上训练
        eval_model = ARIMA(train[value_col], order=order).fit()
        predictions = eval_model.forecast(steps=len(test))
        
        mae = np.mean(np.abs(predictions - test[value_col]))
        rmse = np.sqrt(np.mean((predictions - test[value_col])**2))
        
        return ForecastResult(
            forecast=pd.Series(forecast, index=forecast_index),
            lower_bound=pd.Series(conf_int.iloc[:, 0], index=forecast_index),
            upper_bound=pd.Series(conf_int.iloc[:, 1], index=forecast_index),
            model_name="ARIMA",
            metrics={"MAE": mae, "RMSE": rmse},
            model_params={"order": order}
        )
```

### 6.2 Prophet 预测

```python
from prophet import Prophet

class ProphetForecaster:
    """Prophet 预测器"""
    
    def forecast(
        self,
        df: pd.DataFrame,
        value_col: str,
        date_col: str,
        periods: int = 30,
        include_holidays: bool = False,
        country: str = "CN"
    ) -> ForecastResult:
        """
        使用 Prophet 进行时间序列预测
        
        Prophet 优势：
        - 自动检测趋势和季节性
        - 处理缺失值和异常值
        - 支持节假日效应
        - 提供可解释的组件分解
        """
        # 1. 准备数据（Prophet 要求列名为 ds 和 y）
        prophet_df = df[[date_col, value_col]].copy()
        prophet_df.columns = ['ds', 'y']
        prophet_df['ds'] = pd.to_datetime(prophet_df['ds'])
        
        # 2. 创建模型
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False
        )
        
        # 3. 添加节假日（可选）
        if include_holidays:
            model.add_country_holidays(country_name=country)
        
        # 4. 训练模型
        model.fit(prophet_df)
        
        # 5. 创建未来日期
        future = model.make_future_dataframe(periods=periods)
        
        # 6. 预测
        forecast = model.predict(future)
        
        # 7. 提取预测结果
        forecast_values = forecast.tail(periods)
        
        # 8. 评估指标（使用交叉验证）
        from prophet.diagnostics import cross_validation, performance_metrics
        
        df_cv = cross_validation(
            model, 
            initial='730 days', 
            period='180 days', 
            horizon='30 days'
        )
        df_p = performance_metrics(df_cv)
        
        mae = df_p['mae'].mean()
        rmse = df_p['rmse'].mean()
        
        return ForecastResult(
            forecast=forecast_values['yhat'],
            lower_bound=forecast_values['yhat_lower'],
            upper_bound=forecast_values['yhat_upper'],
            model_name="Prophet",
            metrics={"MAE": mae, "RMSE": rmse},
            model_params={
                "include_holidays": include_holidays,
                "country": country
            }
        )
```

## 7. 机器学习处理器详细设计

### 7.1 聚类分析

```python
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score

class ClusteringAnalyzer:
    """聚类分析"""
    
    def cluster_kmeans(
        self,
        df: pd.DataFrame,
        features: List[str],
        n_clusters: Optional[int] = None,
        auto_select: bool = True,
        max_clusters: int = 10
    ) -> ClusteringResult:
        """
        K-Means 聚类
        
        步骤：
        1. 数据预处理（标准化）
        2. 确定最优聚类数（肘部法则 + 轮廓系数）
        3. 执行聚类
        4. 评估结果
        """
        # 1. 数据预处理
        X = df[features].copy()
        
        # 处理缺失值
        X = X.fillna(X.mean())
        
        # 标准化
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # 2. 确定最优聚类数
        if auto_select and n_clusters is None:
            n_clusters = self._find_optimal_clusters(
                X_scaled, 
                max_clusters
            )
        elif n_clusters is None:
            n_clusters = 3  # 默认值
        
        # 3. 执行聚类
        kmeans = KMeans(
            n_clusters=n_clusters,
            random_state=42,
            n_init=10
        )
        labels = kmeans.fit_predict(X_scaled)
        
        # 4. 评估
        silhouette = silhouette_score(X_scaled, labels)
        
        # 5. 添加聚类标签到原数据
        result_df = df.copy()
        result_df['cluster'] = labels
        
        # 6. 计算聚类中心（原始尺度）
        centers = scaler.inverse_transform(kmeans.cluster_centers_)
        
        return ClusteringResult(
            labels=pd.Series(labels, index=df.index),
            n_clusters=n_clusters,
            cluster_centers=centers,
            metrics={"silhouette_score": silhouette},
            model=kmeans
        )
    
    def _find_optimal_clusters(
        self,
        X: np.ndarray,
        max_clusters: int
    ) -> int:
        """使用肘部法则和轮廓系数找最优聚类数"""
        inertias = []
        silhouettes = []
        
        for k in range(2, max_clusters + 1):
            kmeans = KMeans(n_clusters=k, random_state=42)
            labels = kmeans.fit_predict(X)
            inertias.append(kmeans.inertia_)
            silhouettes.append(silhouette_score(X, labels))
        
        # 选择轮廓系数最高的 k
        optimal_k = silhouettes.index(max(silhouettes)) + 2
        
        return optimal_k
```

## 8. 智能分析建议详细设计

```python
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
        
        决策树：
        1. 识别数据类型
        2. 评估数据质量
        3. 分析问题意图
        4. 推荐分析方法
        """
        # 1. 识别数据类型
        data_types = self._identify_data_types(df)
        
        # 2. 评估数据质量
        quality = self._assess_data_quality(df)
        
        # 3. 分析问题意图（使用 LLM）
        intent = self._analyze_question_intent(question)
        
        # 4. 推荐分析方法
        recommendations = []
        
        # 时间序列数据 → 时间序列分析
        if data_types['has_datetime'] and intent in ['forecast', 'trend']:
            recommendations.append({
                "method": "time_series_forecast",
                "reason": "检测到时间序列数据，适合进行趋势分析和预测",
                "priority": 5,
                "expected_insight": "未来趋势预测、季节性模式"
            })
        
        # 多个数值字段 → 相关性分析
        if data_types['numeric_count'] >= 2:
            recommendations.append({
                "method": "correlation_analysis",
                "reason": "多个数值字段，可以分析字段间的相关性",
                "priority": 4,
                "expected_insight": "字段间的关联关系"
            })
        
        # 分类字段 + 数值字段 → 分组统计
        if data_types['categorical_count'] >= 1 and data_types['numeric_count'] >= 1:
            recommendations.append({
                "method": "group_statistics",
                "reason": "包含分类和数值字段，适合分组统计分析",
                "priority": 4,
                "expected_insight": "不同类别的统计差异"
            })
        
        # 客户数据 → RFM 分析
        if self._is_customer_data(df, metadata):
            recommendations.append({
                "method": "rfm_analysis",
                "reason": "检测到客户交易数据，适合进行 RFM 分析",
                "priority": 5,
                "expected_insight": "客户价值分群、流失风险识别"
            })
        
        # 多维数据 → 聚类分析
        if data_types['numeric_count'] >= 3:
            recommendations.append({
                "method": "clustering",
                "reason": "多维数值数据，可以进行聚类分析发现模式",
                "priority": 3,
                "expected_insight": "数据分群、模式识别"
            })
        
        # 按优先级排序
        recommendations.sort(key=lambda x: x['priority'], reverse=True)
        
        return AnalysisRecommendation(
            recommended_methods=[r['method'] for r in recommendations],
            reasons={r['method']: r['reason'] for r in recommendations},
            priority={r['method']: r['priority'] for r in recommendations},
            expected_insights={r['method']: r['expected_insight'] for r in recommendations}
        )
    
    def _identify_data_types(self, df: pd.DataFrame) -> Dict[str, Any]:
        """识别数据类型"""
        return {
            "numeric_count": len(df.select_dtypes(include=[np.number]).columns),
            "categorical_count": len(df.select_dtypes(include=['object', 'category']).columns),
            "datetime_count": len(df.select_dtypes(include=['datetime']).columns),
            "has_datetime": len(df.select_dtypes(include=['datetime']).columns) > 0
        }
    
    def _is_customer_data(self, df: pd.DataFrame, metadata: Optional[Dict]) -> bool:
        """判断是否是客户数据"""
        # 检查是否包含客户ID、日期、金额等字段
        columns_lower = [col.lower() for col in df.columns]
        
        has_customer = any(
            keyword in ' '.join(columns_lower) 
            for keyword in ['customer', 'user', 'client', '客户', '用户']
        )
        has_date = any(
            keyword in ' '.join(columns_lower) 
            for keyword in ['date', 'time', '日期', '时间']
        )
        has_amount = any(
            keyword in ' '.join(columns_lower) 
            for keyword in ['amount', 'price', 'sales', '金额', '价格', '销售']
        )
        
        return has_customer and has_date and has_amount
```

## 9. 实现优先级和里程碑

### Phase 1: 基础迁移（1周）
- [ ] 将所有 Polars 代码迁移到 pandas
- [ ] 更新数据模型（QueryResult, ProcessingResult）
- [ ] 更新所有现有处理器（YoY, MoM, Percentage, Custom）
- [ ] 更新测试用例
- [ ] 性能基准测试

### Phase 2: 派生指标和数据画像（1周）
- [ ] 实现 MovingAverageCalculator
- [ ] 实现 CumulativeCalculator
- [ ] 实现 RankingCalculator
- [ ] 实现 RFMCalculator
- [ ] 实现 DescriptiveStatistics
- [ ] 实现 CorrelationAnalyzer
- [ ] 实现 OutlierDetector
- [ ] 添加单元测试

### Phase 3: 统计和时间序列（1周）
- [ ] 实现 HypothesisTest
- [ ] 实现 RegressionAnalyzer
- [ ] 实现 TimeSeriesDecomposer
- [ ] 实现 ARIMAForecaster
- [ ] 实现 ProphetForecaster
- [ ] 实现 AnomalyDetector
- [ ] 集成测试

### Phase 4: 机器学习和智能建议（1周）
- [ ] 实现 ClusteringAnalyzer
- [ ] 实现 ClassificationAnalyzer
- [ ] 实现 FeatureEngineer
- [ ] 实现 IntelligentAdvisor
- [ ] 端到端测试
- [ ] 性能优化
- [ ] 文档完善

## 10. 性能优化策略

### 10.1 向量化操作
```python
# 避免循环
# 慢
for i in range(len(df)):
    df.loc[i, 'result'] = df.loc[i, 'a'] + df.loc[i, 'b']

# 快
df['result'] = df['a'] + df['b']
```

### 10.2 分块处理
```python
def process_large_dataframe(df: pd.DataFrame, chunk_size: int = 10000):
    """分块处理大数据集"""
    results = []
    for i in range(0, len(df), chunk_size):
        chunk = df.iloc[i:i+chunk_size]
        result = process_chunk(chunk)
        results.append(result)
    return pd.concat(results)
```

### 10.3 使用 Numba 加速
```python
from numba import jit

@jit(nopython=True)
def fast_calculation(arr):
    """使用 Numba 加速数值计算"""
    result = np.zeros_like(arr)
    for i in range(len(arr)):
        result[i] = arr[i] ** 2 + arr[i] * 2
    return result
```

## 11. 测试策略

### 11.1 单元测试
- 每个处理器都有独立的测试文件
- 测试正常情况和边缘情况
- 测试错误处理

### 11.2 集成测试
- 测试完整的数据处理流程
- 测试不同处理器的组合
- 测试性能

### 11.3 性能测试
- 与 Polars 实现对比
- 大数据集测试（100万行）
- 内存使用测试

---

**文档版本**: 1.0  
**创建时间**: 2025-11-20  
**作者**: Kiro AI Assistant
