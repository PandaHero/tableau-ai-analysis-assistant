# 附件 4：正确性属性详细定义

本文档定义 20 个核心正确性属性，用于 Property-Based Testing。

## 属性测试概述

Property-Based Testing (PBT) 是一种测试方法，通过定义系统应该满足的通用属性，然后自动生成大量测试用例来验证这些属性。

**优势**：
- 发现边界情况和异常输入
- 测试覆盖面广
- 自动生成测试用例
- 验证系统不变量

**使用框架**：Hypothesis (Python)

---

## 1. 预处理属性（4 个）

### P1.1 幂等性（Idempotence）

**定义**：预处理函数执行多次应该得到相同结果

```python
@given(st.text())
def test_preprocess_idempotence(query: str):
    """预处理幂等性"""
    result1 = preprocess(query)
    result2 = preprocess(result1)
    assert result1 == result2
```

### P1.2 可逆性（Reversibility）

**定义**：某些预处理操作应该可逆

```python
@given(st.text())
def test_preprocess_reversibility(query: str):
    """预处理可逆性（针对可逆操作）"""
    # 去除空格是可逆的
    stripped = query.strip()
    # 添加回空格应该能恢复（在某些情况下）
    # 注意：这个属性仅适用于特定的可逆操作
    pass
```

### P1.3 长度约束（Length Constraint）

**定义**：预处理后的文本长度应该在合理范围内

```python
@given(st.text(min_size=1, max_size=1000))
def test_preprocess_length_constraint(query: str):
    """预处理长度约束"""
    result = preprocess(query)
    assert len(result) <= len(query)  # 预处理不应增加长度
    assert len(result) >= 0
```

### P1.4 字符集保持（Character Set Preservation）

**定义**：预处理应该保持有效字符

```python
@given(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd'))))
def test_preprocess_character_preservation(query: str):
    """预处理字符集保持"""
    result = preprocess(query)
    # 所有字母和数字应该被保留
    original_alphanum = set(c for c in query if c.isalnum())
    result_alphanum = set(c for c in result if c.isalnum())
    assert result_alphanum.issubset(original_alphanum)
```

---

## 2. 意图路由属性（3 个）

### P2.1 确定性（Determinism）

**定义**：相同输入应该得到相同输出

```python
@given(st.text())
def test_intent_router_determinism(query: str):
    """意图路由确定性"""
    result1 = intent_router.route(query)
    result2 = intent_router.route(query)
    assert result1.intent == result2.intent
    assert result1.confidence == result2.confidence
```

### P2.2 置信度范围（Confidence Range）

**定义**：置信度应该在 [0, 1] 范围内

```python
@given(st.text())
def test_intent_router_confidence_range(query: str):
    """意图路由置信度范围"""
    result = intent_router.route(query)
    assert 0.0 <= result.confidence <= 1.0
```

### P2.3 覆盖性（Coverage）

**定义**：所有查询都应该被路由到某个意图

```python
@given(st.text(min_size=1))
def test_intent_router_coverage(query: str):
    """意图路由覆盖性"""
    result = intent_router.route(query)
    assert result.intent is not None
    assert result.intent in VALID_INTENTS
```

---

## 3. Schema Linking 属性（4 个）

### P3.1 精确匹配优先（Exact Match Priority）

**定义**：精确匹配的字段应该排在前面

```python
@given(st.text(), st.lists(st.text()))
def test_schema_linking_exact_match_priority(query: str, field_names: List[str]):
    """Schema Linking 精确匹配优先"""
    # 如果查询包含某个字段名，该字段应该排在前面
    if any(name in query for name in field_names):
        results = schema_linker.link(query, field_names)
        exact_matches = [r for r in results if r.name in query]
        if exact_matches:
            assert results[0] in exact_matches
```

### P3.2 同义词对称性（Synonym Symmetry）

**定义**：同义词应该映射到相同字段

```python
@given(st.text())
def test_schema_linking_synonym_symmetry(query: str):
    """Schema Linking 同义词对称性"""
    # 如果 A 是 B 的同义词，那么查询 A 和查询 B 应该得到相同结果
    synonyms = {"销售额": "revenue", "收入": "revenue"}
    for syn1, target in synonyms.items():
        for syn2, target2 in synonyms.items():
            if target == target2:
                result1 = schema_linker.link(syn1, field_names)
                result2 = schema_linker.link(syn2, field_names)
                assert result1[0].id == result2[0].id
```

### P3.3 分数单调性（Score Monotonicity）

**定义**：检索结果应该按分数降序排列

```python
@given(st.text())
def test_schema_linking_score_monotonicity(query: str):
    """Schema Linking 分数单调性"""
    results = schema_linker.link(query, field_names)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
```

### P3.4 Top-K 一致性（Top-K Consistency）

**定义**：Top-K 结果应该是 Top-(K+1) 的子集

```python
@given(st.text(), st.integers(min_value=1, max_value=20))
def test_schema_linking_topk_consistency(query: str, k: int):
    """Schema Linking Top-K 一致性"""
    results_k = schema_linker.link(query, field_names, top_k=k)
    results_k_plus_1 = schema_linker.link(query, field_names, top_k=k+1)
    
    # Top-K 应该是 Top-(K+1) 的前 K 个
    assert results_k == results_k_plus_1[:k]
```

---

## 4. 缓存属性（3 个）

### P4.1 幂等性（Idempotence）

**定义**：多次缓存相同数据应该得到相同结果

```python
@given(st.text(), st.text())
def test_cache_idempotence(key: str, value: str):
    """缓存幂等性"""
    cache.set(key, value)
    result1 = cache.get(key)
    cache.set(key, value)
    result2 = cache.get(key)
    assert result1 == result2 == value
```

### P4.2 一致性（Consistency）

**定义**：缓存的值应该与设置的值一致

```python
@given(st.text(), st.text())
def test_cache_consistency(key: str, value: str):
    """缓存一致性"""
    cache.set(key, value)
    result = cache.get(key)
    assert result == value
```

### P4.3 过期时间（Expiration）

**定义**：缓存应该在 TTL 后过期

```python
@given(st.text(), st.text(), st.integers(min_value=1, max_value=10))
def test_cache_expiration(key: str, value: str, ttl: int):
    """缓存过期时间"""
    cache.set(key, value, ttl=ttl)
    time.sleep(ttl + 1)
    result = cache.get(key)
    assert result is None
```

---

## 5. 配置属性（3 个）

### P5.1 验证完整性（Validation Completeness）

**定义**：所有必需配置项都应该被验证

```python
@given(st.dictionaries(st.text(), st.text()))
def test_config_validation_completeness(config_dict: Dict[str, str]):
    """配置验证完整性"""
    try:
        config = Settings(**config_dict)
    except ValidationError as e:
        # 应该明确指出缺失的字段
        assert "field required" in str(e).lower()
```

### P5.2 默认值（Default Values）

**定义**：未提供的配置项应该使用默认值

```python
def test_config_default_values():
    """配置默认值"""
    config = Settings()
    assert config.api_port == 8000  # 默认端口
    assert config.log_level == "INFO"  # 默认日志级别
```

### P5.3 环境隔离（Environment Isolation）

**定义**：不同环境的配置应该隔离

```python
@given(st.sampled_from(["development", "staging", "production"]))
def test_config_environment_isolation(env: str):
    """配置环境隔离"""
    config = load_config(env)
    assert config.environment == env
    # 生产环境应该有更严格的配置
    if env == "production":
        assert config.log_level in ["WARNING", "ERROR"]
```

---

## 6. 序列化属性（3 个）

### P6.1 Round-trip 属性

**定义**：序列化后反序列化应该得到原始对象

```python
@given(st.builds(SemanticQuery))
def test_serialization_roundtrip(query: SemanticQuery):
    """序列化 Round-trip"""
    # 序列化
    serialized = query.model_dump()
    # 反序列化
    deserialized = SemanticQuery.model_validate(serialized)
    # 应该相等
    assert deserialized == query
```

### P6.2 类型保持（Type Preservation）

**定义**：序列化应该保持数据类型

```python
@given(st.builds(SemanticQuery))
def test_serialization_type_preservation(query: SemanticQuery):
    """序列化类型保持"""
    serialized = query.model_dump()
    deserialized = SemanticQuery.model_validate(serialized)
    
    # 检查类型
    assert type(deserialized.intent) == type(query.intent)
    assert type(deserialized.entities) == type(query.entities)
```

### P6.3 向后兼容（Backward Compatibility）

**定义**：新版本应该能反序列化旧版本的数据

```python
def test_serialization_backward_compatibility():
    """序列化向后兼容"""
    # 旧版本数据（缺少新字段）
    old_data = {
        "raw_query": "test",
        "normalized_query": "test",
        "intent": "COMPARISON"
    }
    
    # 应该能成功反序列化
    query = SemanticQuery.model_validate(old_data)
    assert query.raw_query == "test"
    # 新字段应该使用默认值
    assert query.entities == []
```

---

## 测试策略

### 测试执行

```bash
# 运行所有属性测试
pytest tests/property/ -v

# 运行特定类别
pytest tests/property/test_preprocess_properties.py -v

# 增加测试用例数量
pytest tests/property/ --hypothesis-max-examples=1000
```

### 失败处理

当属性测试失败时，Hypothesis 会提供最小化的反例：

```python
# 示例失败输出
"""
Falsifying example: test_preprocess_idempotence(
    query='  \n\t  '
)
"""
```

### 覆盖率目标

- **属性测试覆盖率**：20 个属性全覆盖
- **每个属性测试用例数**：≥ 100
- **失败率**：0%（所有属性都应该通过）

---

## 总结

通过定义和验证这 20 个核心正确性属性，我们可以：

✅ **发现边界情况**：自动生成大量测试用例  
✅ **验证系统不变量**：确保核心属性始终成立  
✅ **提高代码质量**：在开发早期发现问题  
✅ **增强信心**：全面的测试覆盖  

这些属性测试与单元测试和集成测试互补，共同构成完整的测试体系。
