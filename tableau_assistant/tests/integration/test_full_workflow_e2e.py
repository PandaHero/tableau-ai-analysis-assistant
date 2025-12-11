# -*- coding: utf-8 -*-
"""
完整工作流端到端集成测试

使用 WorkflowExecutor 和 Workflo行测试。
验证完整工作流：Understanding → FieldMapper → QueryBuilder → Execute → Insight → Replanner

测试覆
1. 简单聚合 - SUM, AVG, COUNT
2. COUNTD - 去重计数
3. LOD 表达式 - FIXED
4. 表计算 - RUNNING_SUM, RANK
LAST)
6. 多维度分析
7. 非分析类问题
"""

import pytest
import os
from pathlib impoath
from dotenv import d_dotenv

环境变量
PRO
load_dotenv(PROJECT_Rv")

froort (
,
    WorkflowP
    EventType,
)


# ==============
# Fixtures
# =========================================================

@pytest.fixture(scope="module")
def executor():
器"""
    return Worunds=2)


@pytest.fixture(le")
def printer():
    """创建打印器"""
ue)


@pytest.fixture(scope="m)
k_env():
    """检查环境配置"""
    required = ["TABLEAU_DOMAIN", UID"]
nv(k)]
:
        pytest.skip(f"缺少环境配置: {', '.join(missing)}")


=
# 简单聚合测试


class TestSimpleAggregation:
    """简单试"""
    
ncio
    async 
        """SUM 聚合"""
        result少")
        printer.pr
        
        assert result.success, f"失败:"
        assert result.semantic_queryne
        assert result.is
    
    @pytest.mark.asyncio
    async def test_avg(self, exenv):
    
        result = await executor.run("各地区的平均利润是多少")
        assert resul
    
    @pytest.mark.asyncio
    async def test_count(self, executov):
    "
        result = await executor.run(类别的订单数量")
        assert result.t.error}"


===

# ==========

class TestCountD:
    """COUNTD 去重计"""
    
    @pytest.mark.
    async def test_countd_env):
        """COUNTD 去重计数"""
        result = await executor.run("各产品类别有多少个不同客户")
        assert result.succ}"


# ======================================================================
# LOD 表达式测试
# ==========================================

class TestLOD:
    """LOD 表达式测试"""
    

    async def test_lod_fixed(self, executor, check_env):
        "
        result = await executor.run("各子类别销售额及其所属类别的总销售额")



# ==========
# 表计算测试
# ============================

class TestTableCalculation:
    """表计算测试"""
    
    @pytest.mark.asyncio
    async def test_r:
        """累计求和"""
        result = await executor.run("按月累计销售
        assert result.success, f"失败: {resul"
    
    
    async def test_rank(self, executor, check_env):
        """排名"""
        result = await executor.run("销售额排名")
        assert result.success,rror}"


# ====================================
# 日期筛选测试 - 绝对日期
# =====================================

class TestDateFilterAbsolute:
    """绝对日期筛选测试"""
    
    @pytest.mark.asyncio
    async def test_a
        """绝对年份"""
        result = await execut
        assert result.suc
    
    @pytest.mark.asyncio
    async def test_absolute_month(self, executor, check_env):
        "
        result = a类别销售额")
        assert result.success, f"失败: {result.error}"
    
    rk.asyncio
    async def test_absolute_range(self, executornv):
        """绝对日期范围"""
        result = await 销售额")
        assert result.succ"


# =======================================
# 日期相对日期
# ================================================================

class TestDateFilterRelative:
    """相对日期筛选测试"""
    
    @pytest.syncio
    async def test_current_month(self, execuenv):
        """本月"""
        result = await executor.run("本月各产品类别销
        assert result.success, f"失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_last_month(self, execv):
        """上月"""
        result = await executor.run("上月各
        assert result.success, f"失败: {result.err
    
    @pytest.mark.asyncio
    async def test_lastn_monthck_env):
        """最近N个月"""
    )
        assert result.success, f"失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_year_to_date(self, executo):
        """年初至今"""
        resu况")
        assert result.success, f"失败: {resul"


# ======
# 多维度分析测试
# ========

class TestMultiD
    """多维度分析测试"""
    
    @pytest.mark.asyncio
    async def test_two_dimensions(self, executor, check_env):
        """双维度"""
        result =销售额")
        assert result.success, f"失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_multiple_measures(self, executor, check_env):
        """多度量"""
        result = await executor.run("各产品类别的销售额和利润")
    


# =================================================
# 非分析类问题测试
# ==========================================================

class Tesis:
    """非分析类问
    
    @pytest.mark.asyncio
    async denv):
        """问候语"""
        result = await executor.run("你好，请问你是谁？")
        assert result.success, f"失败: {result.error}"
        assert result.is_analysisFalse


# =============================================================
# 流式试
# ====================================================

class TestStreaming:
    """流式执行测试"""
    
    @pytest.mark.ancio
    asynnv):
        """流"""
        events = []
        async for event in executor."):
            printer.print_event(event)
            
        
        # 验证事件序列
        event_types = [e.type for e in events]
        assert EventType.NODE_START in 
        assert EventType.NODE_COMPLETE in event_types
        assert EventTypes


# ======================================================================
# 运行入口
# ===================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v
