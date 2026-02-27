# -*- coding: utf-8 -*-
"""测试 Tableau Cloud 数据源字段

查看 '销售' 数据源的实际字段名,特别是日期字段。
"""

import asyncio
import logging
import os
import sys

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def main():
    """查看数据源字段"""
    datasource_name = "销售"
    
    print(f"\n{'='*60}")
    print(f"  查看 Tableau Cloud 数据源字段")
    print(f"{'='*60}\n")
    
    # 认证
    print("1. Tableau 认证...")
    auth = await get_tableau_auth_async()
    print(f"   认证方式: {auth.auth_method}")
    print(f"   站点: {auth.site}")
    print(f"   域名: {auth.domain}")
    
    # 加载数据模型
    print(f"\n2. 加载数据源: {datasource_name}")
    async with TableauDataLoader() as loader:
        data_model = await loader.load_data_model(
            datasource_name=datasource_name,
            auth=auth,
        )
    
    print(f"   数据源 LUID: {data_model.datasource_id}")
    print(f"   数据源名称: {data_model.datasource_name}")
    
    # 显示所有字段
    print(f"\n3. 字段列表:")
    print(f"\n   维度字段 ({len([f for f in data_model.fields if f.role == 'DIMENSION'])}):")
    for f in data_model.fields:
        if f.role == "DIMENSION":
            print(f"      - {f.name:30s} [{f.data_type:10s}] caption={f.field_caption or 'N/A':20s} desc={f.description or 'N/A'}")
    
    print(f"\n   度量字段 ({len([f for f in data_model.fields if f.role == 'MEASURE'])}):")
    for f in data_model.fields:
        if f.role == "MEASURE":
            print(f"      - {f.name:30s} [{f.data_type:10s}] caption={f.field_caption or 'N/A':20s} desc={f.description or 'N/A'}")
    
    # 查找日期相关字段
    print(f"\n4. 日期相关字段:")
    time_keywords = {"date", "time", "year", "month", "day", "日期", "时间", "年", "月", "日", "dt", "yyyymm"}
    time_data_types = {"date", "datetime", "timestamp"}
    
    for f in data_model.fields:
        is_time = False
        reason = []
        
        if f.data_type and f.data_type.lower() in time_data_types:
            is_time = True
            reason.append(f"数据类型={f.data_type}")
        
        if any(kw in f.name.lower() for kw in time_keywords):
            is_time = True
            reason.append(f"字段名包含时间关键词")
        
        if f.field_caption and any(kw in f.field_caption.lower() for kw in time_keywords):
            is_time = True
            reason.append(f"标题包含时间关键词")
        
        if is_time:
            print(f"      - {f.name:30s} [{f.data_type:10s}] caption={f.field_caption or 'N/A':20s}")
            print(f"        原因: {', '.join(reason)}")
    
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
