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
from tableau_assistant.src.bi_platforms.tableau.vizql_data_service import query_vds

logger = logging.getLogger(__name__)


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
    
    Args:
        max_retries: 最大重试次数（默认3次）
        retry_delay: 重试延迟（秒，默认1秒）
        timeout: 查询超时时间（秒，默认30秒）
        metadata: 元数据对象（可选，用于QueryBuilder集成）
        anchor_date: 锚点日期（可选，用于日期筛选器）
        week_start_day: 周开始日（可选，0=周一，6=周日）
    
    Examples:
        # 基本使用（仅执行VizQLQuery）
        executor = QueryExecutor()
        result = executor.execute_query(vizql_query, datasource_luid, tableau_config)
        
        # 带QueryBuilder支持（可执行QuerySubTask）
        executor = QueryExecutor(metadata=metadata)
        result = executor.execute_subtask(subtask, datasource_luid, tableau_config)
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
        """
        初始化查询执行器
        
        Args:
            max_retries: 最大重试次数（默认3次）
            retry_delay: 重试延迟（秒，默认1秒）
            timeout: 查询超时时间（秒，默认30秒）
            metadata: 元数据对象（可选，提供后可执行QuerySubTask）
            anchor_date: 锚点日期（可选，用于日期筛选器，默认使用metadata.valid_max_date）
            week_start_day: 周开始日（可选，0=周一，6=周日）
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.metadata = metadata
        self.anchor_date = anchor_date
        self.week_start_day = week_start_day
        
        # 如果提供了metadata，自动创建QueryBuilder
        self.query_builder = None
        if metadata:
            from tableau_assistant.src.capabilities.query.builder import QueryBuilder
            self.query_builder = QueryBuilder(
                metadata=metadata,
                anchor_date=anchor_date,
                week_start_day=week_start_day
            )
            logger.info(
                f"QueryExecutor初始化完成，已集成QueryBuilder "
                f"(datasource={metadata.datasource_name})"
            )
        else:
            logger.info("QueryExecutor初始化完成（未集成QueryBuilder）")
    
    @classmethod
    async def create_with_metadata(
        cls,
        metadata_manager,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ) -> 'QueryExecutor':
        """
        创建带有元数据的QueryExecutor实例（工厂方法）
        
        此方法从MetadataManager异步获取Metadata，然后创建配置完整的QueryExecutor实例。
        创建的实例将自动集成QueryBuilder，可以执行QuerySubTask。
        
        Args:
            metadata_manager: 元数据管理器实例
            max_retries: 最大重试次数（默认3次）
            retry_delay: 重试延迟（秒，默认1秒）
            timeout: 查询超时时间（秒，默认30秒）
            anchor_date: 锚点日期（可选，用于日期筛选器）
            week_start_day: 周开始日（可选，0=周一，6=周日）
        
        Returns:
            配置完整的QueryExecutor实例（已集成QueryBuilder）
        
        Examples:
            # 使用MetadataManager创建
            from tableau_assistant.src.capabilities.metadata.manager import MetadataManager
            
            metadata_manager = MetadataManager(...)
            executor = await QueryExecutor.create_with_metadata(metadata_manager)
            
            # 现在可以执行QuerySubTask
            result = executor.execute_subtask(subtask, datasource_luid, tableau_config)
        """
        # 异步获取metadata
        metadata = await metadata_manager.get_metadata_async()
        
        logger.info(
            f"通过工厂方法创建QueryExecutor "
            f"(datasource={metadata.datasource_name}, fields={metadata.field_count})"
        )
        
        # 创建并返回QueryExecutor实例
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
        """
        执行VizQL查询（带重试机制）
        
        Args:
            query: VizQL查询对象
            datasource_luid: 数据源LUID
            tableau_config: Tableau配置 {
                "tableau_token": str,
                "tableau_site": str,
                "tableau_domain": str
            }
            enable_retry: 是否启用重试（默认True）
        
        Returns:
            查询结果字典 {
                "data": List[Dict],  # 数据行
                "row_count": int,    # 行数
                "columns": List[str], # 列名
                "query_time_ms": int,  # 查询时间（毫秒）
                "execution_time_ms": int,  # 总执行时间（毫秒，包含重试）
                "retry_count": int,  # 重试次数
                "performance": {  # 性能指标
                    "execution_time": float,  # 执行时间（秒）
                    "execution_time_ms": int,  # 执行时间（毫秒）
                    "row_count": int,  # 返回行数
                    "fields_count": int,  # 字段数量
                    "filters_count": int,  # 筛选器数量
                    "retry_count": int  # 重试次数
                }
            }
        
        Raises:
            QueryExecutionError: 查询执行失败
        """
        start_time = time.time()
        retry_count = 0
        last_error = None
        
        # 1. 验证所有输入参数
        self._validate_inputs(query, datasource_luid, tableau_config)
        
        # 2. 准备查询参数
        url = self._build_url(tableau_config)
        query_dict = query.model_dump(exclude_none=True)
        
        # 3. 收集查询元信息用于性能监控
        fields_count = len(query.fields)
        filters_count = len(query.filters) if query.filters else 0
        
        logger.info(
            f"开始执行VizQL查询: datasource={datasource_luid}, "
            f"fields={fields_count}, filters={filters_count}"
        )
        logger.debug(f"查询URL: {url}")
        logger.debug(f"查询对象: {query_dict}")
        
        # 4. 执行查询（带重试）
        max_attempts = self.max_retries + 1 if enable_retry else 1
        
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    retry_count += 1
                    logger.info(f"重试查询 (第{attempt}/{self.max_retries}次)")
                    time.sleep(self.retry_delay * attempt)  # 指数退避
                
                # 执行查询
                result = query_vds(
                    api_key=tableau_config["tableau_token"],
                    datasource_luid=datasource_luid,
                    url=url,
                    query=query_dict,
                    site=tableau_config.get("tableau_site")
                )
                
                # 解析结果
                parsed_result = self._parse_result(result)
                
                # 添加执行信息和性能指标
                execution_time_ms = int((time.time() - start_time) * 1000)
                execution_time_sec = round(time.time() - start_time, 3)
                row_count = parsed_result['row_count']
                
                # 添加详细的性能指标
                parsed_result["execution_time_ms"] = execution_time_ms
                parsed_result["retry_count"] = retry_count
                parsed_result["performance"] = {
                    "execution_time": execution_time_sec,  # 秒
                    "execution_time_ms": execution_time_ms,  # 毫秒（保持兼容）
                    "row_count": row_count,
                    "fields_count": fields_count,
                    "filters_count": filters_count,
                    "retry_count": retry_count
                }
                
                logger.info(
                    f"VizQL查询执行成功 (耗时: {execution_time_sec}秒, "
                    f"返回: {row_count} 行数据, 重试: {retry_count}次)"
                )
                
                return parsed_result
            
            except Exception as e:
                last_error = e
                error_type = self._classify_error(e)
                
                # 判断是否应该重试
                if not enable_retry or not self._should_retry(error_type, attempt, max_attempts):
                    break
                
                logger.warning(f"查询失败 ({error_type.value}), 将重试: {str(e)}")
        
        # 所有重试都失败
        error_type = self._classify_error(last_error)
        execution_time_ms = int((time.time() - start_time) * 1000)
        execution_time_sec = round(time.time() - start_time, 3)
        
        logger.error(
            f"VizQL查询执行失败 (耗时: {execution_time_sec}秒, "
            f"重试: {retry_count}次): {last_error}"
        )
        
        raise QueryExecutionError(
            f"查询执行失败 (重试{retry_count}次后): {str(last_error)}",
            error_type,
            last_error
        )
    
    def execute_subtask(
        self,
        subtask: QuerySubTask,
        datasource_luid: str,
        tableau_config: Dict[str, str],
        enable_retry: bool = True
    ) -> Dict[str, Any]:
        """
        执行QuerySubTask（从Intent构建查询并执行）
        
        此方法使用QueryBuilder将QuerySubTask转换为VizQLQuery，然后执行查询。
        需要在初始化时提供metadata参数才能使用此方法。
        
        Args:
            subtask: 查询子任务对象
            datasource_luid: 数据源LUID
            tableau_config: Tableau配置
            enable_retry: 是否启用重试（默认True）
        
        Returns:
            查询结果字典 {
                "data": List[Dict],  # 数据行
                "row_count": int,    # 行数
                "columns": List[str], # 列名
                "query_time_ms": int,  # 查询时间（毫秒）
                "execution_time_ms": int,  # 总执行时间（毫秒）
                "retry_count": int,  # 重试次数
                "performance": {  # 性能指标
                    "execution_time": float,  # 执行时间（秒）
                    "execution_time_ms": int,  # 执行时间（毫秒）
                    "row_count": int,  # 返回行数
                    "fields_count": int,  # 字段数量
                    "filters_count": int,  # 筛选器数量
                    "retry_count": int,  # 重试次数
                    "build_time": float,  # 查询构建时间（秒）
                    "total_time": float  # 总时间（构建+执行）
                },
                "subtask_info": {  # 子任务信息
                    "question_id": str,  # 问题ID
                    "question_text": str,  # 问题文本
                    "task_type": str  # 任务类型
                }
            }
        
        Raises:
            ValueError: QueryBuilder未初始化（未提供metadata参数）
            QueryExecutionError: 查询构建或执行失败
        
        Examples:
            executor = QueryExecutor(metadata=metadata)
            result = executor.execute_subtask(subtask, datasource_luid, tableau_config)
            print(f"构建时间: {result['performance']['build_time']}秒")
            print(f"执行时间: {result['performance']['execution_time']}秒")
        """
        if not self.query_builder:
            raise ValueError(
                "QueryBuilder未初始化，需要在创建QueryExecutor时提供metadata参数。"
                "示例: QueryExecutor(metadata=metadata)"
            )
        
        start_time = time.time()
        
        try:
            logger.info(
                f"开始执行子任务: {subtask.question_id} - {subtask.question_text}"
            )
            
            # 使用QueryBuilder构建VizQL查询
            build_start = time.time()
            vizql_query = self.query_builder.build_query(subtask)
            build_time = time.time() - build_start
            
            logger.info(f"查询构建完成 (耗时: {build_time:.3f}秒)")
            
            # 执行VizQL查询
            result = self.execute_query(
                query=vizql_query,
                datasource_luid=datasource_luid,
                tableau_config=tableau_config,
                enable_retry=enable_retry
            )
            
            # 添加构建时间到性能信息
            if 'performance' in result:
                result['performance']['build_time'] = round(build_time, 3)
                result['performance']['total_time'] = round(
                    time.time() - start_time, 3
                )
            
            # 添加子任务信息
            result['subtask_info'] = {
                'question_id': subtask.question_id,
                'question_text': subtask.question_text,
                'task_type': subtask.task_type
            }
            
            logger.info(
                f"子任务执行成功: {subtask.question_id} "
                f"(总耗时: {result['performance']['total_time']}秒)"
            )
            
            return result
            
        except ValueError as e:
            # ValueError是输入验证错误，直接抛出
            raise
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"子任务执行失败: {subtask.question_id} "
                f"(耗时: {execution_time:.3f}秒) - {e}"
            )
            raise
    
    def _validate_inputs(
        self,
        query: VizQLQuery,
        datasource_luid: str,
        tableau_config: Dict[str, str]
    ):
        """
        验证所有输入参数
        
        Args:
            query: VizQL查询对象
            datasource_luid: 数据源LUID
            tableau_config: Tableau配置
        
        Raises:
            QueryExecutionError: 验证失败
        """
        # 验证query对象
        if query is None:
            raise QueryExecutionError(
                "查询对象不能为None",
                QueryErrorType.VALIDATION_ERROR
            )
        
        if not hasattr(query, 'fields'):
            raise QueryExecutionError(
                "查询对象必须包含fields属性",
                QueryErrorType.VALIDATION_ERROR
            )
        
        if not query.fields or len(query.fields) == 0:
            raise QueryExecutionError(
                "查询必须包含至少一个字段",
                QueryErrorType.VALIDATION_ERROR
            )
        
        # 验证字段
        for field in query.fields:
            field_dict = field.model_dump(exclude_none=True) if hasattr(field, 'model_dump') else field
            if not field_dict.get('fieldCaption') and not field_dict.get('calculation'):
                raise QueryExecutionError(
                    "字段必须包含 fieldCaption 或 calculation",
                    QueryErrorType.VALIDATION_ERROR
                )
        
        # 验证datasource_luid
        if not datasource_luid or not datasource_luid.strip():
            raise QueryExecutionError(
                "数据源LUID不能为空",
                QueryErrorType.VALIDATION_ERROR
            )
        
        # 验证tableau_config
        if not tableau_config:
            raise QueryExecutionError(
                "Tableau配置不能为空",
                QueryErrorType.VALIDATION_ERROR
            )
        
        if not tableau_config.get("tableau_token") or not tableau_config["tableau_token"].strip():
            raise QueryExecutionError(
                "Tableau API Token不能为空",
                QueryErrorType.VALIDATION_ERROR
            )
        
        if not tableau_config.get("tableau_domain") or not tableau_config["tableau_domain"].strip():
            raise QueryExecutionError(
                "Tableau域名不能为空",
                QueryErrorType.VALIDATION_ERROR
            )
    
    def _build_url(self, tableau_config: Dict[str, str]) -> str:
        """
        构建Tableau URL
        
        注意：VizQL Data Service API不需要在URL中包含/t/{site}
        站点信息通过X-Tableau-Site请求头传递
        
        Args:
            tableau_config: Tableau配置
        
        Returns:
            完整的URL（不包含站点路径）
        """
        tableau_domain = tableau_config.get("tableau_domain", "")
        
        # 移除尾部斜杠
        tableau_domain = tableau_domain.rstrip("/")
        
        # VizQL Data Service API使用基础域名，站点通过请求头指定
        return tableau_domain
    
    def _classify_error(self, error: Exception) -> QueryErrorType:
        """
        分类错误类型
        
        Args:
            error: 异常对象
        
        Returns:
            错误类型
        """
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
        else:
            return QueryErrorType.UNKNOWN_ERROR
    
    def _should_retry(self, error_type: QueryErrorType, attempt: int, max_attempts: int) -> bool:
        """
        判断是否应该重试
        
        Args:
            error_type: 错误类型
            attempt: 当前尝试次数
            max_attempts: 最大尝试次数
        
        Returns:
            是否应该重试
        """
        # 已达到最大尝试次数
        if attempt >= max_attempts - 1:
            return False
        
        # 某些错误类型不应该重试
        non_retryable_errors = {
            QueryErrorType.AUTH_ERROR,  # 认证错误
            QueryErrorType.VALIDATION_ERROR,  # 验证错误
        }
        
        return error_type not in non_retryable_errors
    
    def _build_query_request(
        self,
        query: VizQLQuery,
        datasource_luid: str
    ) -> QueryRequest:
        """
        构建查询请求对象
        
        Args:
            query: VizQL查询对象
            datasource_luid: 数据源LUID
        
        Returns:
            QueryRequest对象
        """
        return QueryRequest(
            datasource=Datasource(datasourceLuid=datasource_luid),
            query=query
        )
    
    def _parse_result(self, result: Dict) -> Dict[str, Any]:
        """
        解析查询结果
        
        Args:
            result: VDS API返回的原始结果
        
        Returns:
            标准化的结果字典
        """
        # 提取数据
        data = result.get("data", [])
        
        # 提取列名
        columns = []
        if data and len(data) > 0:
            columns = list(data[0].keys())
        
        # 构建标准化结果
        parsed = {
            "data": data,
            "row_count": len(data),
            "columns": columns,
            "query_time_ms": result.get("query_time_ms", 0),
            "raw_result": result  # 保留原始结果用于调试
        }
        
        return parsed
    
    def execute_multiple_queries(
        self,
        queries: List[Dict[str, Any]],
        datasource_luid: str,
        tableau_config: Dict[str, str],
        fail_fast: bool = False
    ) -> List[Dict[str, Any]]:
        """
        执行多个查询（串行）
        
        Args:
            queries: 查询列表，每个包含 {
                "query_id": str,
                "query": VizQLQuery
            }
            datasource_luid: 数据源LUID
            tableau_config: Tableau配置
            fail_fast: 是否在第一个失败时停止（默认False）
        
        Returns:
            结果列表
        """
        results = []
        start_time = time.time()
        
        logger.info(f"开始执行{len(queries)}个查询")
        
        for idx, query_item in enumerate(queries, 1):
            query_id = query_item.get("query_id")
            query = query_item.get("query")
            
            logger.info(f"执行查询 {idx}/{len(queries)}: {query_id}")
            
            try:
                result = self.execute_query(query, datasource_luid, tableau_config)
                result["query_id"] = query_id
                result["success"] = True
                results.append(result)
            
            except QueryExecutionError as e:
                logger.error(f"查询{query_id}执行失败: {e}")
                
                # 记录失败结果
                results.append({
                    "query_id": query_id,
                    "success": False,
                    "error": str(e),
                    "error_type": e.error_type.value,
                    "data": [],
                    "row_count": 0
                })
                
                # 如果启用fail_fast，立即停止
                if fail_fast:
                    logger.warning(f"fail_fast模式：停止执行剩余{len(queries) - idx}个查询")
                    break
            
            except Exception as e:
                logger.error(f"查询{query_id}执行失败（未知错误）: {e}")
                
                results.append({
                    "query_id": query_id,
                    "success": False,
                    "error": str(e),
                    "error_type": "unknown",
                    "data": [],
                    "row_count": 0
                })
                
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
        """
        批量执行多个QuerySubTask（串行）
        
        此方法按顺序执行多个QuerySubTask，单个任务失败不影响其他任务（除非启用fail_fast）。
        需要在初始化时提供metadata参数才能使用此方法。
        
        Args:
            subtasks: 查询子任务列表
            datasource_luid: 数据源LUID
            tableau_config: Tableau配置
            fail_fast: 是否在第一个失败时停止（默认False）
        
        Returns:
            结果列表，每个元素包含 {
                "success": bool,  # 是否成功
                "result": Dict,  # 查询结果（成功时）
                "error": str,  # 错误信息（失败时）
                "subtask_info": {  # 子任务信息
                    "question_id": str,
                    "question_text": str,
                    "task_type": str
                }
            }
        
        Raises:
            ValueError: QueryBuilder未初始化（未提供metadata参数）
        
        Examples:
            executor = QueryExecutor(metadata=metadata)
            results = executor.execute_multiple_subtasks(
                subtasks, datasource_luid, tableau_config
            )
            
            # 统计成功率
            success_count = sum(1 for r in results if r['success'])
            print(f"成功: {success_count}/{len(results)}")
            
            # 处理失败的任务
            for result in results:
                if not result['success']:
                    print(f"失败: {result['subtask_info']['question_id']}")
                    print(f"错误: {result['error']}")
        """
        if not self.query_builder:
            raise ValueError(
                "QueryBuilder未初始化，需要在创建QueryExecutor时提供metadata参数。"
                "示例: QueryExecutor(metadata=metadata)"
            )
        
        results = []
        total_start = time.time()
        
        logger.info(f"开始批量执行 {len(subtasks)} 个子任务")
        
        for i, subtask in enumerate(subtasks, 1):
            try:
                logger.info(
                    f"执行子任务 {i}/{len(subtasks)}: {subtask.question_id} - {subtask.question_text}"
                )
                
                result = self.execute_subtask(
                    subtask=subtask,
                    datasource_luid=datasource_luid,
                    tableau_config=tableau_config
                )
                
                results.append({
                    'success': True,
                    'result': result,
                    'error': None
                })
            
            except ValueError as e:
                # ValueError是输入验证错误，直接抛出
                raise
            
            except QueryExecutionError as e:
                logger.error(f"子任务 {subtask.question_id} 执行失败: {e}")
                
                results.append({
                    'success': False,
                    'result': None,
                    'error': str(e),
                    'error_type': e.error_type.value,
                    'subtask_info': {
                        'question_id': subtask.question_id,
                        'question_text': subtask.question_text,
                        'task_type': subtask.task_type
                    }
                })
                
                # 如果启用fail_fast，立即停止
                if fail_fast:
                    logger.warning(
                        f"fail_fast模式：停止执行剩余 {len(subtasks) - i} 个子任务"
                    )
                    break
            
            except Exception as e:
                logger.error(f"子任务 {subtask.question_id} 执行失败（未知错误）: {e}")
                
                results.append({
                    'success': False,
                    'result': None,
                    'error': str(e),
                    'error_type': 'unknown',
                    'subtask_info': {
                        'question_id': subtask.question_id,
                        'question_text': subtask.question_text,
                        'task_type': subtask.task_type
                    }
                })
                
                if fail_fast:
                    logger.warning(
                        f"fail_fast模式：停止执行剩余 {len(subtasks) - i} 个子任务"
                    )
                    break
        
        # 统计和日志
        total_time = time.time() - total_start
        success_count = sum(1 for r in results if r['success'])
        
        logger.info(
            f"批量执行完成 (总耗时: {total_time:.3f}秒, "
            f"成功: {success_count}/{len(subtasks)})"
        )
        
        return results


# ============= 导出 =============

__all__ = [
    "QueryExecutor",
    "QueryExecutionError",
    "QueryErrorType",
]
