#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 VizQL API: read-metadata vs get-datasource-model

对比两个 API 的输出差异
"""
import os
import json
import asyncio
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from tableau_assistant.src.platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.platforms.tableau.metadata import get_data_dictionary
from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth


def test_apis():
    """测试两个 API 的输出"""
    # 从环境变量获取配置
    domain = os.getenv("TABLEAU_CLOUD_DOMAIN", "").rstrip("/")
    site = os.getenv("TABLEAU_CLOUD_SITE", "")
    datasource_luid = os.getenv("DATASOURCE_LUID", "")
    
    if not all([domain, datasource_luid]):
        print("请设置环境变量: TABLEAU_CLOUD_DOMAIN, DATASOURCE_LUID")
        return
    
    # 获取认证 token
    print("正在获取 Tableau 认证 token...")
    try:
        auth_ctx = get_tableau_auth(target_domain=domain)
        if not auth_ctx or not auth_ctx.api_key:
            print("获取 token 失败")
            return
        api_key = auth_ctx.api_key
        print(f"Token 获取成功: {api_key[:20]}...")
    except Exception as e:
        print(f"认证失败: {e}")
        return
    
    print(f"Domain: {domain}")
    print(f"Site: {site}")
    print(f"Datasource LUID: {datasource_luid}")
    print("=" * 80)
    
    config = VizQLClientConfig(base_url=domain, timeout=30, max_retries=3)
    
    with VizQLClient(config=config) as client:
        # 1. 测试 read-metadata
        print("\n[1] /read-metadata API")
        print("-" * 40)
        try:
            metadata_response = client.read_metadata(
                datasource_luid=datasource_luid,
                api_key=api_key,
                site=site
            )
            fields = metadata_response.get("data", [])
            print(f"字段数量: {len(fields)}")
            
            # 显示前 5 个字段
            print("\n前 5 个字段:")
            for i, field in enumerate(fields[:5]):
                print(f"  {i+1}. {field.get('fieldCaption', 'N/A')}")
                print(f"     - fieldName: {field.get('fieldName', 'N/A')}")
                print(f"     - dataType: {field.get('dataType', 'N/A')}")
                print(f"     - fieldRole: {field.get('fieldRole', 'N/A')}")
                print(f"     - logicalTableId: {field.get('logicalTableId', 'N/A')}")
                print(f"     - columnClass: {field.get('columnClass', 'N/A')}")
            
            # 保存完整响应
            with open("metadata_response.json", "w", encoding="utf-8") as f:
                json.dump(metadata_response, f, ensure_ascii=False, indent=2)
            print(f"\n完整响应已保存到: metadata_response.json")
            
        except Exception as e:
            print(f"read-metadata 失败: {e}")
        
        # 2. 测试 get-datasource-model
        print("\n[2] /get-datasource-model API")
        print("-" * 40)
        try:
            model_response = client.get_datasource_model(
                datasource_luid=datasource_luid,
                api_key=api_key,
                site=site
            )
            
            logical_tables = model_response.get("logicalTables", [])
            relationships = model_response.get("logicalTableRelationships", [])
            
            print(f"逻辑表数量: {len(logical_tables)}")
            print(f"表关系数量: {len(relationships)}")
            
            # 显示逻辑表
            if logical_tables:
                print("\n逻辑表:")
                for table in logical_tables:
                    print(f"  - {table.get('caption', 'N/A')} (ID: {table.get('logicalTableId', 'N/A')})")
            
            # 显示表关系
            if relationships:
                print("\n表关系:")
                for rel in relationships:
                    from_table = rel.get("fromLogicalTable", {}).get("logicalTableId", "N/A")
                    to_table = rel.get("toLogicalTable", {}).get("logicalTableId", "N/A")
                    print(f"  - {from_table} -> {to_table}")
            
            # 保存完整响应
            with open("datasource_model_response.json", "w", encoding="utf-8") as f:
                json.dump(model_response, f, ensure_ascii=False, indent=2)
            print(f"\n完整响应已保存到: datasource_model_response.json")
            
        except Exception as e:
            print(f"get-datasource-model 失败: {e}")
    
    # 3. 测试组合后的 get_data_dictionary
    print("\n[3] get_data_dictionary (组合两个 API)")
    print("-" * 40)
    try:
        data_dict = get_data_dictionary(
            api_key=api_key,
            domain=domain,
            datasource_luid=datasource_luid,
            site=site,
            include_samples=False  # 不获取样例数据，加快测试
        )
        
        print(f"字段数量: {data_dict.get('field_count', 0)}")
        
        # 统计维度和度量
        fields = data_dict.get("fields", [])
        dimensions = [f for f in fields if f.get("role", "").upper() == "DIMENSION"]
        measures = [f for f in fields if f.get("role", "").upper() == "MEASURE"]
        print(f"维度数量: {len(dimensions)}")
        print(f"度量数量: {len(measures)}")
        
        # 数据模型
        data_model = data_dict.get("data_model")
        if data_model:
            print(f"逻辑表数量: {len(data_model.get('logicalTables', []))}")
            print(f"表关系数量: {len(data_model.get('logicalTableRelationships', []))}")
        else:
            print("数据模型: 无（单表数据源）")
        
        # 保存完整响应
        with open("data_dictionary_response.json", "w", encoding="utf-8") as f:
            json.dump(data_dict, f, ensure_ascii=False, indent=2)
        print(f"\n完整响应已保存到: data_dictionary_response.json")
        
    except Exception as e:
        print(f"get_data_dictionary 失败: {e}")
    
    print("\n" + "=" * 80)
    print("测试完成！请查看生成的 JSON 文件对比详细内容。")


if __name__ == "__main__":
    test_apis()
