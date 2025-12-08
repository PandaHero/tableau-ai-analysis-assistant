"""
查询执行器（Query Executor）

职责：
1. 调用Tableau VDS API执行查询
2. 解析返回结果
3. 错误处理和重试
4. 性能监控
5. 集成QueryBuilder支持QuerySubTask执行

功能：
- ✅ 自动重试机制（可配置）
- ✅ 超时控制
- ✅ 错误分类和处理
- ✅ 查询验证
- ✅ 性能监控
- ✅ QueryBuilder集成
- ✅ QuerySubTask执行支持
- ⚠️ 暂不支持分页（VDS API限制）
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import time
from enum import Enum

from tableau_assistant.src.models.vizql_types import VizQLQuery, QueryRequest, Datasource
from tableau_assistant.src.models.query_plan import QuerySubTask
from tableau_assistant.src.models.metadata import Metadata
from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.exceptions import VizQLError, VizQLAuthError, VizQLValidationError

logger = logging.getLogger(__name__)

# 全局客户端实例（连接池复用）
_vizql_client: VizQLClient = None


def _get_vizql_client(tableau_config: Dict[str, str]) -> VizQLClient:
    """获取或创建 VizQL 客户端（单例模式，复用连接池）"""
    global _vizql_client
    
    base_url = tableau_config.get("tableau_domain", "").rstrip("/")
    
    if _vizql_client is None or _vizql_client.config.base_url != base_url:
        if _vizql_client is not None:
            _vizql_client.close()
        
        config = VizQLClientConfig(base_url=base_url)
        _vizql_client = VizQLClient(config=config)
    
    return _vizql_client


class QueryErrorType(Enum):
    """查询错误类型"""
    NETWORK_ERROR = "network_error"  # 网络错误
    AUTH_ERROR = "auth_error"  # 认证错误
    VALIDATION_ERROR = "validation_error"  # 验证错误
    TIMEOUT_ERROR = "timeout_error"  # 超时错误
    SERVER_ERROR = "server_error"  # 服务器错误
    UNKNOWN_ERROR = "unknown_error"  # 未知错误


class QueryExecutionError(Exception):
    """查询执行错误"""
    def __init__(self, message: str, error_type: QueryErrorType, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.error_type = error_type
        self.original_error = original_error


class QueryExecutor:
    """
    查询执行器
    
    调用Tableau VDS API执行VizQL查询，支持直接执行VizQLQuery或从QuerySubTask构建并执行。
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
        metadata: Optional[Metadata] = None,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.metadata = metadata
        self.anchor_date = anchor_date
        self.week_start_day = week_start_day
        
        self.query_builder = None
        if metadata:
            from tableau_assistant.src.capabilities.query.builder import QueryBuilder
            self.query_builder = QueryBuilder(
                metadata=metadata,
                anchor_date=anchor_date,
                week_start_day=week_start_day
            )
            logger.info(f"QueryExecutor初始化完成，已集成QueryBuilder (datasource={metadata.datasource_name})")
        else:
            logger.info("QueryExecutor初始化完成（未集成QueryBuilder）")
    
    @classmethod
    async def create_with_data_model(
        cls,
        data_model_manager,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ) -> 'QueryExecutor':
        """创建带有数据模型的QueryExecutor实例（工厂方法）"""
        metadata = await data_model_manager.get_data_model_async()
        logger.info(f"通过工厂方法创建QueryExecutor (datasource={metadata.datasource_name}, fields={metadata.field_count})")
        return cls(
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout=timeout,
            metadata=metadata,
            anchor_date=anchor_date,
            week_start_day=week_start_day
        )
    
    def execute_query(
        self,
        query: VizQLQuery,
        datasource_luid: str,
        tableau_config: Dict[str, str],
        enable_retry: bool = True
    ) -> Dict[str, Any]:
        """执行VizQL查询（带重试机制）"""
        start_time = time.time()
        retry_count = 0
        last_error = None
        
        self._validate_inputs(query, datasource_luid, tableau_config)
        
        url = self._build_url(tableau_config)
        query_dict = query.model_dump(exclude_none=True)
        
        fields_count = len(query.fields)
        filters_count = len(query.filters) if query.filters else 0
        
        logger.info(f"开始执行VizQL查询: datasource={datasource_luid}, fields={fields_count}, filters={filters_count}")
        
        max_attempts = self.max_retries + 1 if enable_retry else 1
        
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    retry_count += 1
                    logger.info(f"重试查询 (第{attempt}/{self.max_retries}次)")
                    time.sleep(self.retry_delay * attempt)
                
                client = _get_vizql_client(tableau_config)
                result = client.query_datasource(
                    datasource_luid=datasource_luid,
                    query=query_dict,
                    api_key=tableau_config["tableau_token"],
                    site=tableau_config.get("tableau_site")
                )
                
                parsed_result = self._parse_result(result)
                
                execution_time_ms = int((time.time() - start_time) * 1000)
                execution_time_sec = round(time.time() - start_time, 3)
                row_count = parsed_result['row_count']
                
                parsed_result["execution_time_ms"] = execution_time_ms
                parsed_result["retry_count"] = retry_count
                parsed_result["performance"] = {
                    "execution_time": execution_time_sec,
                    "execution_time_ms": execution_time_ms,
                    "row_count": row_count,
                    "fields_count": fields_count,
                    "filters_count": filters_count,
                    "retry_count": retry_count
                }
                
                logger.info(f"VizQL查询执行成功 (耗时: {execution_time_sec}秒, 返回: {row_count} 行数据)")
                return parsed_result
            
            except Exception as e:
                last_error = e
                error_type = self._classify_error(e)
                if not enable_retry or not self._should_retry(error_type, attempt, max_attempts):
                    break
                logger.warning(f"查询失败 ({error_type.value}), 将重试: {str(e)}")
        
        error_type = self._classify_error(last_error)
        raise QueryExecutionError(f"查询执行失败 (重试{retry_count}次后): {str(last_error)}", error_type, last_error)

    def execute_subtask(
        self,
        subtask: QuerySubTask,
        datasource_luid: str,
        tableau_config: Dict[str, str],
        enable_retry: bool = True
    ) -> Dict[str, Any]:
        """执行QuerySubTask（从Intent构建查询并执行）"""
        if not self.query_builder:
            raise ValueError("QueryBuilder未初始化，需要在创建QueryExecutor时提供metadata参数。")
        
        start_time = time.time()
        
        try:
            logger.info(f"开始执行子任务: {subtask.question_id} - {subtask.question_text}")
            
            build_start = time.time()
            vizql_query = self.query_builder.build_query(subtask)
            build_time = time.time() - build_start
            
            logger.info(f"查询构建完成 (耗时: {build_time:.3f}秒)")
            
            result = self.execute_query(
                query=vizql_query,
                datasource_luid=datasource_luid,
                tableau_config=tableau_config,
                enable_retry=enable_retry
            )
            
            if 'performance' in result:
                result['performance']['build_time'] = round(build_time, 3)
                result['performance']['total_time'] = round(time.time() - start_time, 3)
            
            result['subtask_info'] = {
                'question_id': subtask.question_id,
                'question_text': subtask.question_text,
                'task_type': subtask.task_type
            }
            
            logger.info(f"子任务执行成功: {subtask.question_id}")
            return result
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"子任务执行失败: {subtask.question_id} - {e}")
            raise
    
    def _validate_inputs(self, query: VizQLQuery, datasource_luid: str, tableau_config: Dict[str, str]):
        """验证所有输入参数"""
        if query is None:
            raise QueryExecutionError("查询对象不能为None", QueryErrorType.VALIDATION_ERROR)
        if not hasattr(query, 'fields'):
            raise QueryExecutionError("查询对象必须包含fields属性", QueryErrorType.VALIDATION_ERROR)
        if not query.fields or len(query.fields) == 0:
            raise QueryExecutionError("查询必须包含至少一个字段", QueryErrorType.VALIDATION_ERROR)
        
        for field in query.fields:
            field_dict = field.model_dump(exclude_none=True) if hasattr(field, 'model_dump') else field
            if not field_dict.get('fieldCaption') and not field_dict.get('calculation'):
                raise QueryExecutionError("字段必须包含 fieldCaption 或 calculation", QueryErrorType.VALIDATION_ERROR)
        
        if not datasource_luid or not datasource_luid.strip():
            raise QueryExecutionError("数据源LUID不能为空", QueryErrorType.VALIDATION_ERROR)
        if not tableau_config:
            raise QueryExecutionError("Tableau配置不能为空", QueryErrorType.VALIDATION_ERROR)
        if not tableau_config.get("tableau_token") or not tableau_config["tableau_token"].strip():
            raise QueryExecutionError("Tableau API Token不能为空", QueryErrorType.VALIDATION_ERROR)
        if not tableau_config.get("tableau_domain") or not tableau_config["tableau_domain"].strip():
            raise QueryExecutionError("Tableau域名不能为空", QueryErrorType.VALIDATION_ERROR)
    
    def _build_url(self, tableau_config: Dict[str, str]) -> str:
        """构建Tableau URL"""
        tableau_domain = tableau_config.get("tableau_domain", "")
        return tableau_domain.rstrip("/")
    
    def _classify_error(self, error: Exception) -> QueryErrorType:
        """分类错误类型"""
        error_str = str(error).lower()
        if "404" in error_str or "not found" in error_str:
            return QueryErrorType.NETWORK_ERROR
        elif "401" in error_str or "403" in error_str or "unauthorized" in error_str:
            return QueryErrorType.AUTH_ERROR
        elif "400" in error_str or "validation" in error_str:
            return QueryErrorType.VALIDATION_ERROR
        elif "timeout" in error_str:
            return QueryErrorType.TIMEOUT_ERROR
        elif "500" in error_str or "502" in error_str or "503" in error_str:
            return QueryErrorType.SERVER_ERROR
        return QueryErrorType.UNKNOWN_ERROR
    
    def _should_retry(self, error_type: QueryErrorType, attempt: int, max_attempts: int) -> bool:
        """判断是否应该重试"""
        if attempt >= max_attempts - 1:
            return False
        non_retryable_errors = {QueryErrorType.AUTH_ERROR, QueryErrorType.VALIDATION_ERROR}
        return error_type not in non_retryable_errors
    
    def _build_query_request(self, query: VizQLQuery, datasource_luid: str) -> QueryRequest:
        """构建查询请求对象"""
        return QueryRequest(datasource=Datasource(datasourceLuid=datasource_luid), query=query)
    
    def _parse_result(self, result: Dict) -> Dict[str, Any]:
        """解析查询结果"""
        data = result.get("data", [])
        columns = list(data[0].keys()) if data else []
        return {
            "data": data,
            "row_count": len(data),
            "columns": columns,
            "query_time_ms": result.get("query_time_ms", 0),
            "raw_result": result
        }
    
    def execute_multiple_queries(
        self,
        queries: List[Dict[str, Any]],
        datasource_luid: str,
        tableau_config: Dict[str, str],
        fail_fast: bool = False
    ) -> List[Dict[str, Any]]:
        """执行多个查询（串行）"""
        results = []
        start_time = time.time()
        logger.info(f"开始执行{len(queries)}个查询")
        
        for idx, query_item in enumerate(queries, 1):
            query_id = query_item.get("query_id")
            query = query_item.get("query")
            
            try:
                result = self.execute_query(query, datasource_luid, tableau_config)
                result["query_id"] = query_id
                result["success"] = True
                results.append(result)
            except QueryExecutionError as e:
                results.append({"query_id": query_id, "success": False, "error": str(e), "error_type": e.error_type.value, "data": [], "row_count": 0})
                if fail_fast:
                    break
            except Exception as e:
                results.append({"query_id": query_id, "success": False, "error": str(e), "error_type": "unknown", "data": [], "row_count": 0})
                if fail_fast:
                    break
        
        total_time = time.time() - start_time
        success_count = sum(1 for r in results if r.get("success", False))
        logger.info(f"批量查询完成: {success_count}/{len(results)}成功, 总耗时{total_time:.2f}秒")
        return results
    
    def execute_multiple_subtasks(
        self,
        subtasks: List[QuerySubTask],
        datasource_luid: str,
        tableau_config: Dict[str, str],
        fail_fast: bool = False
    ) -> List[Dict[str, Any]]:
        """批量执行多个QuerySubTask（串行）"""
        if not self.query_builder:
            raise ValueError("QueryBuilder未初始化，需要在创建QueryExecutor时提供metadata参数。")
        
        results = []
        total_start = time.time()
        logger.info(f"开始批量执行 {len(subtasks)} 个子任务")
        
        for i, subtask in enumerate(subtasks, 1):
            try:
                result = self.execute_subtask(subtask=subtask, datasource_luid=datasource_luid, tableau_config=tableau_config)
                results.append({'success': True, 'result': result, 'error': None})
            except ValueError:
                raise
            except QueryExecutionError as e:
                results.append({'success': False, 'result': None, 'error': str(e), 'error_type': e.error_type.value,
                               'subtask_info': {'question_id': subtask.question_id, 'question_text': subtask.question_text, 'task_type': subtask.task_type}})
                if fail_fast:
                    break
            except Exception as e:
                results.append({'success': False, 'result': None, 'error': str(e), 'error_type': 'unknown',
                               'subtask_info': {'question_id': subtask.question_id, 'question_text': subtask.question_text, 'task_type': subtask.task_type}})
                if fail_fast:
                    break
        
        total_time = time.time() - total_start
        success_count = sum(1 for r in results if r['success'])
        logger.info(f"批量执行完成 (总耗时: {total_time:.3f}秒, 成功: {success_count}/{len(subtasks)})")
        return results


__all__ = ["QueryExecutor", "QueryExecutionError", "QueryErrorType"]
