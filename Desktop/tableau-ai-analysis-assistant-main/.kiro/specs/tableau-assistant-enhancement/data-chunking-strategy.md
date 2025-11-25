# 数据分块策略深度分析

## 核心问题

**问题**：如何正确地分块数据进行累积洞察分析？

**关键挑战**：
1. 不同的问题类型需要不同的分块策略
2. 有些问题必须看到全部数据才能回答（排名、最大值、最小值）
3. 有些问题可以分块分析（趋势、分布、异常）

---

## 错误示例

### 示例1：排名问题

**问题**："哪个省份销售额最高？"

**查询结果**：
```
省份    销售额
北京    1000万
上海    900万
广东    800万
浙江    700万
江苏    600万
... (共 34 个省份)
```

**❌ 错误的分块方式**：按省份分块
```
AI宝宝1 分析 [北京: 1000万, 上海: 900万, 广东: 800万]
  → 结论：北京最高

AI宝宝2 分析 [浙江: 700万, 江苏: 600万, 四川: 550万]
  → 结论：浙江最高

AI宝宝3 分析 [湖北: 500万, 湖南: 450万, 河南: 400万]
  → 结论：湖北最高

合成：？？？每个AI都说自己的省份最高！
```

**✅ 正确的方式**：不分块，或者智能分块
```
方案1：不分块（数据量小）
- 直接分析全部 34 个省份
- 得出：北京最高

方案2：智能分块（数据量大）
- 先分析 Top 10 → 北京最高
- 判断：已经足够回答问题
- 早停：不再分析剩余 24 个省份
```

---

## 问题类型分析

### 类型1：排名/最值问题

**特征**：
- 问题包含："最高"、"最低"、"第一"、"排名"、"Top N"
- 必须看到全部数据（或至少 Top N）才能回答

**分块策略**：
- **不分块**：如果数据量小（< 1000 行）
- **Top-K 分块**：如果数据量大
  - 先分析 Top 100
  - 判断是否足够
  - 如果需要，继续分析

**示例**：
```
问题："哪个省份销售额最高？"

策略：
1. 数据已按销售额降序排序（VizQL 查询结果）
2. 分析 Top 10 → 北京最高（1000万）
3. 判断：已经足够
4. 早停：不分析剩余数据
```

### 类型2：趋势/分布问题

**特征**：
- 问题包含："趋势"、"变化"、"增长"、"分布"
- 可以分块分析，然后合成

**分块策略**：
- **时间分块**：按时间段分块
- **并行分析**：每个AI分析一个时间段
- **智能合成**：识别整体趋势

**示例**：
```
问题："2016-2020年销售额趋势如何？"

查询结果：60 个月的数据

分块策略：
- AI宝宝1 分析 2016年（12个月）→ 增长趋势
- AI宝宝2 分析 2017年（12个月）→ 增长趋势
- AI宝宝3 分析 2018年（12个月）→ 平稳
- AI宝宝4 分析 2019年（12个月）→ 下降趋势
- AI宝宝5 分析 2020年（12个月）→ 反弹

合成：整体呈现先增长、后平稳、再下降、最后反弹的趋势
```

### 类型3：对比问题

**特征**：
- 问题包含："对比"、"比较"、"差异"
- 需要看到所有对比对象

**分块策略**：
- **不分块**：必须同时看到所有对比对象
- 或者**按对比维度分块**

**示例**：
```
问题："华东、华北、华南三个地区的销售额对比"

查询结果：
地区    销售额
华东    5000万
华北    6000万
华南    4500万

策略：
- 不分块：数据量小，直接分析
- 结论：华北最高，华南最低，华东居中
```

### 类型4：异常检测问题

**特征**：
- 问题包含："异常"、"问题"、"为什么"
- 需要识别异常值

**分块策略**：
- **优先分析异常值**
- **然后分析正常值**

**示例**：
```
问题："哪些省份的销售额异常？"

查询结果：34 个省份

分块策略：
1. 统计分析：识别异常值（IQR、Z-score）
2. 优先分析异常值
   - AI宝宝1 分析异常高值（北京: 1000万）
   - AI宝宝2 分析异常低值（西藏: 10万）
3. 分析正常值（可选）
4. 合成：北京异常高，西藏异常低
```

---

## 分块策略决策树

```
问题类型判断
  ↓
是排名/最值问题？
  ├─ 是 → Top-K 分块（或不分块）
  │       - 先分析 Top K
  │       - 判断是否足够
  │       - 早停
  │
  └─ 否 → 继续判断
          ↓
      是趋势/分布问题？
        ├─ 是 → 时间/维度分块
        │       - 并行分析
        │       - 智能合成
        │
        └─ 否 → 继续判断
                ↓
            是对比问题？
              ├─ 是 → 不分块（或按对比维度）
              │
              └─ 否 → 继续判断
                      ↓
                  是异常检测？
                    ├─ 是 → 异常优先分块
                    │
                    └─ 否 → 默认策略
                            - 数据量小：不分块
                            - 数据量大：Top-K 分块
```

---

## 并行 vs 串行

### 并行分析适用场景

**适用**：
- 趋势/分布问题
- 每个分块独立
- 不需要全局视角

**示例**：
```
问题："各地区的销售趋势"

并行分析：
- AI宝宝1 分析华东 → 增长趋势
- AI宝宝2 分析华北 → 平稳
- AI宝宝3 分析华南 → 下降趋势

合成：各地区趋势不同
```

### 串行分析适用场景

**适用**：
- 排名/最值问题
- 需要全局视角
- 后续分析依赖前面的结果

**示例**：
```
问题："哪个省份销售额最高？为什么？"

串行分析：
1. 分析 Top 10 → 北京最高
2. 深入分析北京 → 一线城市、人口多
3. 对比其他省份 → 确认原因

不能并行：必须先知道"谁最高"，才能分析"为什么"
```

---

## 实现建议

### 1. 问题类型识别

```python
class QuestionTypeClassifier:
    """问题类型分类器"""
    
    def classify(self, question: str, intents: List[Intent]) -> QuestionType:
        """
        分类问题类型
        
        Returns:
            RANKING: 排名/最值问题
            TREND: 趋势/分布问题
            COMPARISON: 对比问题
            ANOMALY: 异常检测问题
            GENERAL: 一般问题
        """
        # 基于关键词和 Intent 判断
        if any(word in question for word in ['最高', '最低', '第一', '排名', 'top']):
            return QuestionType.RANKING
        
        if any(word in question for word in ['趋势', '变化', '增长', '分布']):
            return QuestionType.TREND
        
        if any(word in question for word in ['对比', '比较', '差异']):
            return QuestionType.COMPARISON
        
        if any(word in question for word in ['异常', '问题', '为什么']):
            return QuestionType.ANOMALY
        
        return QuestionType.GENERAL
```

### 2. 分块策略选择

```python
class ChunkingStrategySelector:
    """分块策略选择器"""
    
    def select(
        self,
        question_type: QuestionType,
        data_size: int,
        query_result: DataFrame
    ) -> ChunkingStrategy:
        """
        选择分块策略
        
        Returns:
            NO_CHUNK: 不分块
            TOP_K_CHUNK: Top-K 分块
            TIME_CHUNK: 时间分块
            DIMENSION_CHUNK: 维度分块
            ANOMALY_FIRST_CHUNK: 异常优先分块
        """
        # 数据量小：不分块
        if data_size < 1000:
            return ChunkingStrategy.NO_CHUNK
        
        # 根据问题类型选择
        if question_type == QuestionType.RANKING:
            return ChunkingStrategy.TOP_K_CHUNK
        
        elif question_type == QuestionType.TREND:
            # 检查是否有时间字段
            if self._has_time_field(query_result):
                return ChunkingStrategy.TIME_CHUNK
            else:
                return ChunkingStrategy.DIMENSION_CHUNK
        
        elif question_type == QuestionType.COMPARISON:
            return ChunkingStrategy.NO_CHUNK  # 必须看到全部
        
        elif question_type == QuestionType.ANOMALY:
            return ChunkingStrategy.ANOMALY_FIRST_CHUNK
        
        else:
            return ChunkingStrategy.TOP_K_CHUNK  # 默认
```

### 3. 并行/串行决策

```python
class AnalysisModeSelector:
    """分析模式选择器"""
    
    def select(
        self,
        question_type: QuestionType,
        chunking_strategy: ChunkingStrategy
    ) -> AnalysisMode:
        """
        选择分析模式
        
        Returns:
            PARALLEL: 并行分析
            SERIAL: 串行分析
        """
        # 排名问题：串行（需要全局视角）
        if question_type == QuestionType.RANKING:
            return AnalysisMode.SERIAL
        
        # 对比问题：串行（需要同时看到所有对比对象）
        if question_type == QuestionType.COMPARISON:
            return AnalysisMode.SERIAL
        
        # 趋势问题：并行（每个时间段独立）
        if question_type == QuestionType.TREND:
            return AnalysisMode.PARALLEL
        
        # 异常检测：串行（先异常后正常）
        if question_type == QuestionType.ANOMALY:
            return AnalysisMode.SERIAL
        
        # 默认：并行
        return AnalysisMode.PARALLEL
```

---

## 总结

### 关键原则

1. **问题类型决定分块策略**
   - 排名/最值 → Top-K 或不分块
   - 趋势/分布 → 时间/维度分块
   - 对比 → 不分块
   - 异常 → 异常优先

2. **数据量决定是否分块**
   - < 1000 行 → 不分块
   - >= 1000 行 → 根据问题类型分块

3. **问题类型决定并行/串行**
   - 需要全局视角 → 串行
   - 独立分析 → 并行

4. **早停机制**
   - 排名问题：分析 Top K 后判断是否足够
   - 趋势问题：识别模式后判断是否足够

---

**文档版本**: v1.0  
**创建时间**: 2025-11-20  
**作者**: Kiro AI Assistant
