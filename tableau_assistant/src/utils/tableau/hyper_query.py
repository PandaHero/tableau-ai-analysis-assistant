"""
Hyper API 查询工具
实现从数据源名称到 Hyper 文件查询的完整流程
"""

import logging
from typing import Dict, List, Any, Optional
from tableauhyperapi import HyperProcess, Connection, Telemetry, TableName
import psycopg2

logger = logging.getLogger(__name__)


class HyperQueryExecutor:
    """
    Hyper 查询执行器
    
    完整流程：
    1. 数据源名称 → 数据源 LUID (通过 REST API)
    2. 数据源 LUID → .hyper 文件路径 (通过 Repository)
    3. 执行 Hyper API 查询
    """
    
    def __init__(
        self,
        tableau_domain: str,
        tableau_site: str,
        repository_host: str,
        repository_port: int,
        repository_user: str,
        repository_password: str,
        repository_database: str = "workgroup"
    ):
        """
        初始化 Hyper 查询执行器
        
        Args:
            tableau_domain: Tableau Server 域名
            tableau_site: Tableau 站点名称
            repository_host: Repository 数据库主机
            repository_port: Repository 数据库端口
            repository_user: Repository 数据库用户
            repository_password: Repository 数据库密码
            repository_database: Repository 数据库名称（默认 workgroup）
        """
        self.tableau_domain = tableau_domain
        self.tableau_site = tableau_site
        self.repository_host = repository_host
        self.repository_port = repository_port
        self.repository_user = repository_user
        self.repository_password = repository_password
        self.repository_database = repository_database
    
    def get_datasource_luid_from_name(
        self,
        datasource_name: str,
        api_key: str
    ) -> Optional[str]:
        """
        通过数据源名称获取 LUID
        
        Args:
            datasource_name: 数据源名称
            api_key: Tableau API 认证 token
            
        Returns:
            数据源 LUID，如果未找到返回 None
        """
        import requests
        
        # 构建 REST API URL
        url = f"{self.tableau_domain}/api/3.19/sites/{self.tableau_site}/datasources"
        
        headers = {
            'X-Tableau-Auth': api_key,
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            datasources = data.get('datasources', {}).get('datasource', [])
            
            # 查找匹配的数据源
            for ds in datasources:
                if ds.get('name') == datasource_name:
                    luid = ds.get('id')
                    logger.info(f"找到数据源 LUID: {luid} for {datasource_name}")
                    return luid
            
            logger.warning(f"未找到数据源: {datasource_name}")
            return None
            
        except Exception as e:
            logger.error(f"获取数据源 LUID 失败: {e}")
            raise
    
    def get_hyper_path_from_luid(self, datasource_luid: str) -> Optional[str]:
        """
        通过数据源 LUID 查询 .hyper 文件路径
        
        Args:
            datasource_luid: 数据源 LUID
            
        Returns:
            .hyper 文件的完整路径，如果未找到返回 None
        """
        try:
            # 连接到 Repository 数据库
            conn = psycopg2.connect(
                host=self.repository_host,
                port=self.repository_port,
                user=self.repository_user,
                password=self.repository_password,
                database=self.repository_database
            )
            
            cursor = conn.cursor()
            
            # 查询 .hyper 文件路径
            query = """
            SELECT 
                ds.name AS datasource_name,
                ds.repository_url,
                de.id AS extract_id,
                de.descriptor
            FROM datasources ds
            JOIN _datasources_extracts dse ON ds.id = dse.datasource_id
            JOIN _extracts de ON dse.extract_id = de.id
            WHERE ds.luid = %s
            """
            
            cursor.execute(query, (datasource_luid,))
            result = cursor.fetchone()
            
            if result:
                datasource_name, repository_url, extract_id, descriptor = result
                
                # 构建 .hyper 文件路径
                # 格式: /var/opt/tableau/tableau_server/data/tabsvc/dataengine/extract/{path}/{luid}/file.hyper
                
                # 从 descriptor 中提取路径信息
                # descriptor 格式类似: {"path": "59/55/{588980BA-8898-48F1-A288-C3E601A4255}"}
                import json
                desc_data = json.loads(descriptor) if descriptor else {}
                
                # 构建完整路径
                base_path = "/var/opt/tableau/tableau_server/data/tabsvc/dataengine/extract"
                extract_path = desc_data.get('path', '')
                
                if extract_path:
                    # 查找 .hyper 文件名
                    hyper_file_query = """
                    SELECT name 
                    FROM _datasources 
                    WHERE luid = %s
                    """
                    cursor.execute(hyper_file_query, (datasource_luid,))
                    name_result = cursor.fetchone()
                    
                    if name_result:
                        datasource_name = name_result[0]
                        hyper_filename = f"{datasource_name}.hyper"
                        full_path = f"{base_path}/{extract_path}/{hyper_filename}"
                        
                        logger.info(f"找到 Hyper 文件路径: {full_path}")
                        
                        cursor.close()
                        conn.close()
                        
                        return full_path
            
            logger.warning(f"未找到数据源 {datasource_luid} 的 Hyper 文件")
            cursor.close()
            conn.close()
            return None
            
        except Exception as e:
            logger.error(f"查询 Hyper 文件路径失败: {e}")
            raise
    
    def execute_hyper_query(
        self,
        hyper_file_path: str,
        sql: str
    ) -> List[Dict[str, Any]]:
        """
        执行 Hyper API 查询
        
        Args:
            hyper_file_path: .hyper 文件的完整路径
            sql: 要执行的 SQL 查询
            
        Returns:
            查询结果列表，每行是一个字典
        """
        try:
            logger.info(f"执行 Hyper 查询: {sql[:100]}...")
            
            with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
                with Connection(hyper.endpoint, hyper_file_path) as connection:
                    
                    # 执行查询
                    result = connection.execute_list_query(sql)
                    
                    # 获取列名
                    # 注意：这里需要解析 SQL 或使用其他方法获取列名
                    # 简化版本：假设查询返回的列按顺序
                    
                    logger.info(f"查询成功，返回 {len(result)} 行")
                    
                    return result
                    
        except Exception as e:
            logger.error(f"Hyper 查询执行失败: {e}")
            raise
    
    def query_by_datasource_name(
        self,
        datasource_name: str,
        sql: str,
        api_key: str
    ) -> List[Dict[str, Any]]:
        """
        完整流程：从数据源名称到查询结果
        
        Args:
            datasource_name: 数据源名称
            sql: SQL 查询语句
            api_key: Tableau API 认证 token
            
        Returns:
            查询结果
        """
        # 步骤 1: 获取数据源 LUID
        logger.info(f"步骤 1: 获取数据源 LUID for {datasource_name}")
        datasource_luid = self.get_datasource_luid_from_name(datasource_name, api_key)
        
        if not datasource_luid:
            raise ValueError(f"未找到数据源: {datasource_name}")
        
        # 步骤 2: 获取 .hyper 文件路径
        logger.info(f"步骤 2: 获取 Hyper 文件路径 for LUID {datasource_luid}")
        hyper_path = self.get_hyper_path_from_luid(datasource_luid)
        
        if not hyper_path:
            raise ValueError(f"未找到数据源 {datasource_name} 的 Hyper 文件")
        
        # 步骤 3: 执行查询
        logger.info(f"步骤 3: 执行 Hyper 查询")
        result = self.execute_hyper_query(hyper_path, sql)
        
        return result
    
    def query_by_luid(
        self,
        datasource_luid: str,
        sql: str
    ) -> List[Dict[str, Any]]:
        """
        从数据源 LUID 开始查询（跳过步骤 1）
        
        Args:
            datasource_luid: 数据源 LUID
            sql: SQL 查询语句
            
        Returns:
            查询结果
        """
        # 步骤 1: 获取 .hyper 文件路径
        logger.info(f"获取 Hyper 文件路径 for LUID {datasource_luid}")
        hyper_path = self.get_hyper_path_from_luid(datasource_luid)
        
        if not hyper_path:
            raise ValueError(f"未找到数据源 LUID {datasource_luid} 的 Hyper 文件")
        
        # 步骤 2: 执行查询
        logger.info(f"执行 Hyper 查询")
        result = self.execute_hyper_query(hyper_path, sql)
        
        return result


def create_hyper_executor_from_env() -> HyperQueryExecutor:
    """
    从环境变量创建 HyperQueryExecutor
    
    需要的环境变量:
    - TABLEAU_DOMAIN
    - TABLEAU_SITE
    - REPOSITORY_HOST
    - REPOSITORY_PORT
    - REPOSITORY_USER
    - REPOSITORY_PASSWORD
    - REPOSITORY_DATABASE (可选，默认 workgroup)
    """
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    return HyperQueryExecutor(
        tableau_domain=os.environ['TABLEAU_DOMAIN'],
        tableau_site=os.environ['TABLEAU_SITE'],
        repository_host=os.environ['REPOSITORY_HOST'],
        repository_port=int(os.environ['REPOSITORY_PORT']),
        repository_user=os.environ['REPOSITORY_USER'],
        repository_password=os.environ['REPOSITORY_PASSWORD'],
        repository_database=os.environ.get('REPOSITORY_DATABASE', 'workgroup')
    )
