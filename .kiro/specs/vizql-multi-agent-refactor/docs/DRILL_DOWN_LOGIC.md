# 下钻逻辑实现（基于维度层级）

## 维度层级数据结构

```python
dimension_hierarchy = {
    "产品一级分类": {
        "category": "产品",
        "category_detail": "产品-一级分类",
        "level": 1,  # 最粗粒度
        "granularity": "最粗粒度",
        "unique_count": 14,
        "parent_dimension": None,  # 没有父维度
        "child_dimension": "产品二级分类",  # 子维度
        "sample_values": ["FRESH", "食品", "日用品"],
        "level_confidence": 0.95,
        "reasoning": "产品分类的最高层级"
    },
    "产品二级分类": {
        "category": "产品",
        "category_detail": "产品-二级分类",
        "level": 2,  # 粗粒度
        "granularity": "粗粒度",
        "unique_count": 86,
        "parent_dimension": "产品一级分类",  # 父维度
        "child_dimension": "产品三级分类",  # 子维度
        "sample_values": ["FRESH B 肉禽蛋", "FRESH A 水果"],
        "level_confidence": 0.95,
        "reasoning": "产品分类的第二层级"
    },
    "产品三级分类": {
        "category": "产品",
        "category_detail": "产品-三级分类",
        "level": 3,  # 中粒度
        "granularity": "中粒度",
        "unique_count": 174,
        "parent_dimension": "产品二级分类",
        "child_dimension": "产品四级分类",
        "sample_values": ["新鲜猪肉", "水果"],
        "level_confidence": 0.95,
        "reasoning": "产品分类的第三层级"
    }
}
```

## 下钻逻辑实现

### 方法1：使用 child_dimension（最直接）

```python
def drill_down_by_child(current_dimension, dimension_hierarchy):
    """
    使用child_dimension字段直接找到下一级维度
    
    这是最简单、最可靠的方法
    
    Args:
        current_dimension: 当前维度名称
        dimension_hierarchy: 维度层级字典
    
    Returns:
        下一级维度名称，如果没有则返回None
    """
    if current_dimension not in dimension_hierarchy:
        return None
    
    # 直接读取child_dimension字段
    child_dimension = dimension_hierarchy[current_dimension].get("child_dimension")
    
    return child_dimension

# 示例
current_dim = "产品一级分类"
next_dim = drill_down_by_child(current_dim, dimension_hierarchy)
# 返回: "产品二级分类"
```

### 方法2：使用 category + level（备用方案）

```python
def drill_down_by_category_level(current_dimension, dimension_hierarchy):
    """
    使用category和level字段查找下一级维度
    
    适用于child_dimension为空的情况
    
    Args:
        current_dimension: 当前维度名称
        dimension_hierarchy: 维度层级字典
    
    Returns:
        下一级维度名称，如果没有则返回None
    """
    if current_dimension not in dimension_hierarchy:
        return None
    
    current_info = dimension_hierarchy[current_dimension]
    current_category = current_info["category"]
    current_level = current_info["level"]
    
    # 查找同类别的下一级维度
    for dim_name, dim_info in dimension_hierarchy.items():
        if (dim_info["category"] == current_category and 
            dim_info["level"] == current_level + 1):
            return dim_name
    
    return None

# 示例
current_dim = "产品一级分类"
next_dim = drill_down_by_category_level(current_dim, dimension_hierarchy)
# 返回: "产品二级分类"
```

### 方法3：综合方法（推荐）

```python
def find_drill_down_dimension(current_dimension, dimension_hierarchy):
    """
    综合方法：优先使用child_dimension，备用category+level
    
    这是最健壮的实现
    
    Args:
        current_dimension: 当前维度名称
        dimension_hierarchy: 维度层级字典
    
    Returns:
        {
            "next_dimension": str,  # 下一级维度名称
            "method": str,  # 使用的方法（"child_dimension" 或 "category_level"）
            "can_drill_down": bool,  # 是否可以下钻
            "reason": str  # 原因说明
        }
    """
    if current_dimension not in dimension_hierarchy:
        return {
            "next_dimension": None,
            "method": None,
            "can_drill_down": False,
            "reason": f"维度 {current_dimension} 不在层级信息中"
        }
    
    current_info = dimension_hierarchy[current_dimension]
    
    # 方法1：优先使用child_dimension
    child_dimension = current_info.get("child_dimension")
    if child_dimension:
        # 验证child_dimension是否存在于层级信息中
        if child_dimension in dimension_hierarchy:
            return {
                "next_dimension": child_dimension,
                "method": "child_dimension",
                "can_drill_down": True,
                "reason": f"使用预定义的子维度关系"
            }
    
    # 方法2：使用category + level
    current_category = current_info["category"]
    current_level = current_info["level"]
    
    # 检查是否已经是最细粒度
    if current_level >= 4:
        return {
            "next_dimension": None,
            "method": None,
            "can_drill_down": False,
            "reason": f"当前维度已经是细粒度（level={current_level}），不建议继续下钻"
        }
    
    # 查找同类别的下一级维度
    candidates = []
    for dim_name, dim_info in dimension_hierarchy.items():
        if (dim_info["category"] == current_category and 
            dim_info["level"] == current_level + 1):
            candidates.append({
                "name": dim_name,
                "unique_count": dim_info["unique_count"],
                "confidence": dim_info["level_confidence"]
            })
    
    if not candidates:
        return {
            "next_dimension": None,
            "method": None,
            "can_drill_down": False,
            "reason": f"没有找到同类别（{current_category}）的下一级维度"
        }
    
    # 如果有多个候选，选择置信度最高的
    best_candidate = max(candidates, key=lambda x: x["confidence"])
    
    # 检查unique_count是否过大
    if best_candidate["unique_count"] > 500:
        return {
            "next_dimension": best_candidate["name"],
            "method": "category_level",
            "can_drill_down": False,
            "reason": f"下一级维度值太多（{best_candidate['unique_count']}个），数据会过于分散"
        }
    
    return {
        "next_dimension": best_candidate["name"],
        "method": "category_level",
        "can_drill_down": True,
        "reason": f"使用类别和层级推断"
    }

# 示例
current_dim = "产品一级分类"
result = find_drill_down_dimension(current_dim, dimension_hierarchy)
# 返回:
# {
#   "next_dimension": "产品二级分类",
#   "method": "child_dimension",
#   "can_drill_down": True,
#   "reason": "使用预定义的子维度关系"
# }
```

## 完整的下钻决策流程

```python
def make_drill_down_decision(
    current_dimension,
    current_value,
    contribution_percentage,
    dimension_hierarchy,
    current_level_count=None
):
    """
    完整的下钻决策
    
    综合考虑：
    1. 贡献度（是否值得下钻）
    2. 维度层级（是否可以下钻）
    3. 数据量（下钻后是否会过于分散）
    
    Args:
        current_dimension: 当前维度名称
        current_value: 当前维度值
        contribution_percentage: 贡献度（0-1）
        dimension_hierarchy: 维度层级字典
        current_level_count: 当前级别的维度值数量
    
    Returns:
        下钻决策字典
    """
    # 1. 检查贡献度
    if contribution_percentage < 0.5:
        return {
            "should_drill_down": False,
            "reason": f"贡献度仅{contribution_percentage*100:.1f}%，不够高（需要>50%）",
            "next_dimension": None
        }
    
    # 2. 查找下一级维度
    drill_down_info = find_drill_down_dimension(current_dimension, dimension_hierarchy)
    
    if not drill_down_info["can_drill_down"]:
        return {
            "should_drill_down": False,
            "reason": drill_down_info["reason"],
            "next_dimension": None
        }
    
    next_dimension = drill_down_info["next_dimension"]
    next_dimension_info = dimension_hierarchy[next_dimension]
    
    # 3. 检查下一级的unique_count
    next_unique_count = next_dimension_info["unique_count"]
    if next_unique_count > 100:
        return {
            "should_drill_down": False,
            "reason": f"下一级维度（{next_dimension}）有{next_unique_count}个值，数据会过于分散",
            "next_dimension": next_dimension
        }
    
    # 4. 生成下钻决策
    return {
        "should_drill_down": True,
        "reason": f"{current_dimension}的{current_value}贡献了{contribution_percentage*100:.1f}%，下钻到{next_dimension}进行详细分析",
        "current_dimension": current_dimension,
        "current_value": current_value,
        "next_dimension": next_dimension,
        "next_dimension_info": {
            "level": next_dimension_info["level"],
            "granularity": next_dimension_info["granularity"],
            "unique_count": next_unique_count,
            "category": next_dimension_info["category"]
        },
        "query_spec": {
            "dims": [next_dimension],
            "filters": [
                {
                    "type": "dimension",
                    "field": current_dimension,
                    "values": [current_value]
                }
            ]
        }
    }
```

## 实际应用示例

### 示例1：产品维度下钻

```python
# 场景：发现"FRESH"类产品贡献80%利润

dimension_hierarchy = {
    "产品一级分类": {
        "category": "产品",
        "level": 1,
        "unique_count": 14,
        "child_dimension": "产品二级分类"
    },
    "产品二级分类": {
        "category": "产品",
        "level": 2,
        "unique_count": 86,
        "parent_dimension": "产品一级分类",
        "child_dimension": "产品三级分类"
    }
}

# 下钻决策
decision = make_drill_down_decision(
    current_dimension="产品一级分类",
    current_value="FRESH",
    contribution_percentage=0.80,
    dimension_hierarchy=dimension_hierarchy
)

# 结果：
# {
#   "should_drill_down": True,
#   "reason": "产品一级分类的FRESH贡献了80.0%，下钻到产品二级分类进行详细分析",
#   "current_dimension": "产品一级分类",
#   "current_value": "FRESH",
#   "next_dimension": "产品二级分类",
#   "next_dimension_info": {
#     "level": 2,
#     "granularity": "粗粒度",
#     "unique_count": 86,
#     "category": "产品"
#   },
#   "query_spec": {
#     "dims": ["产品二级分类"],
#     "filters": [
#       {"type": "dimension", "field": "产品一级分类", "values": ["FRESH"]}
#     ]
#   }
# }
```

### 示例2：地理维度下钻

```python
# 场景：发现"广东"省贡献60%销售额

dimension_hierarchy = {
    "省份": {
        "category": "地理",
        "level": 2,
        "unique_count": 34,
        "parent_dimension": "国家",
        "child_dimension": "城市"
    },
    "城市": {
        "category": "地理",
        "level": 3,
        "unique_count": 300,
        "parent_dimension": "省份",
        "child_dimension": "区县"
    }
}

decision = make_drill_down_decision(
    current_dimension="省份",
    current_value="广东",
    contribution_percentage=0.60,
    dimension_hierarchy=dimension_hierarchy
)

# 结果：
# {
#   "should_drill_down": False,
#   "reason": "下一级维度（城市）有300个值，数据会过于分散",
#   "next_dimension": "城市"
# }
# 
# 说明：虽然贡献度够高，但下一级维度值太多，不建议下钻
```

### 示例3：时间维度下钻

```python
# 场景：发现"2024年"销售额异常高

dimension_hierarchy = {
    "年": {
        "category": "时间",
        "level": 1,
        "unique_count": 5,
        "child_dimension": "季度"
    },
    "季度": {
        "category": "时间",
        "level": 2,
        "unique_count": 20,
        "parent_dimension": "年",
        "child_dimension": "月"
    },
    "月": {
        "category": "时间",
        "level": 3,
        "unique_count": 60,
        "parent_dimension": "季度",
        "child_dimension": "日"
    }
}

decision = make_drill_down_decision(
    current_dimension="年",
    current_value="2024",
    contribution_percentage=0.70,
    dimension_hierarchy=dimension_hierarchy
)

# 结果：
# {
#   "should_drill_down": True,
#   "reason": "年的2024贡献了70.0%，下钻到季度进行详细分析",
#   "next_dimension": "季度",
#   "query_spec": {
#     "dims": ["季度"],
#     "filters": [
#       {"type": "dimension", "field": "年", "values": ["2024"]}
#     ]
#   }
# }
```

## 集成到重规划Agent

```python
# 在重规划Agent中使用

def replanner_agent_node(state, runtime):
    """重规划Agent节点"""
    
    # 1. 获取前一轮的洞察
    insights = state.get("all_insights", [])
    dimension_hierarchy = state.get("dimension_hierarchy", {})
    replan_count = state.get("replan_count", 0)
    max_replan = runtime.context.max_replan_rounds
    
    # 2. 分析贡献度
    top_contributors = analyze_top_contributors(insights)
    
    # 3. 对每个高贡献者尝试下钻
    for contributor in top_contributors:
        decision = make_drill_down_decision(
            current_dimension=contributor["dimension"],
            current_value=contributor["value"],
            contribution_percentage=contributor["contribution"],
            dimension_hierarchy=dimension_hierarchy
        )
        
        if decision["should_drill_down"]:
            # 生成新问题
            new_question = f"{contributor['value']}的{decision['next_dimension']}分布情况"
            
            return {
                "should_replan": True,
                "replan_type": "drill_down",
                "replan_reason": decision["reason"],
                "new_question": new_question,
                "query_spec": decision["query_spec"],
                "replan_count": replan_count + 1
            }
    
    # 4. 没有需要下钻的维度
    return {
        "should_replan": False,
        "replan_reason": "没有发现需要进一步下钻的维度"
    }
```

## 总结

利用维度层级信息实现下钻的关键：

1. **优先使用 `child_dimension`** - 最直接、最可靠
2. **备用 `category` + `level`** - 当child_dimension为空时
3. **检查 `unique_count`** - 避免下钻到过于分散的维度
4. **考虑 `level`** - 避免下钻到过细的粒度（level >= 4）
5. **结合贡献度** - 只对高贡献度（>50%）的维度下钻

这样就能实现智能、可靠的下钻逻辑了！
