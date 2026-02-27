# -*- coding: utf-8 -*-
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader

async def main():
    auth = await get_tableau_auth_async()
    async with TableauDataLoader() as loader:
        dm = await loader.load_data_model(datasource_name="销售", auth=auth)
    
    print("\n所有维度字段:")
    for f in dm.fields:
        if f.role == "DIMENSION":
            print(f"  {f.name:30s} caption={f.caption or 'N/A':20s} type={f.data_type}")

asyncio.run(main())
