"""
Execute Node - 查询执行节点

纯执行节点（非 Agent），确定性执行，不使用 LLM。

职责：
1. 遍历 query_plan.subtasks
2. 对每个 QuerySubTask 调用 QueryBuilder + QueryExecutor
3. 收集结果到 subtask_results
"""
import logging
import time
from typing import Dict, Any, List, Optional

from tableau_assistant.src.models.state import VizQLState

logger = logging.getLogger(__name__)


def execute_query_node(
    state: VizQLState,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    查询执行节点
    
    确定性执行，不使用 LLM：
    1. 遍历 query_plan.subtasks
    2. 对每个 QuerySubTask 调用 QueryBuilder + QueryExecutor
    3. 收集结果到 subtask_results
    """
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("Execute Node: 开始执行查询")
    logger.info("=" * 60)
    
    query_plan = state.get("query_plan")
    if not query_plan:
        logger.error("Execute Node: 缺少查询计划")
        return {
            "errors": [{"node": "execute", "error": "Missing query_plan", "timestamp": time.time()}],
            "current_stage": "insight",
            "execution_path": ["execute"]
        }
    
    configurable = config.get("configurable", {}) if config else {}
    datasource_luid = configurable.get("datasource_luid")
    
    if not datasource_luid:
        logger.error("Execute Node: 缺少 datasource_luid")
        return {
            "errors": [{"node": "execute", "error": "Missing datasource_luid in config", "timestamp": time.time()}],
            "current_stage": "insight",
            "execution_path": ["execute"]
        }
    
    tableau_config = _get_tableau_config(configurable)
    metadata = state.get("metadata")
    
    subtask_results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    
    subtasks = _get_subtasks(query_plan)
    logger.info(f"Execute Node: 共 {len(subtasks)} 个子任务")
    
    for i, subtask in enumerate(subtasks, 1):
        task_type = _get_attr(subtask, 'task_type', 'query')
        question_id = _get_attr(subtask, 'question_id', f'q{i}')
        question_text = _get_attr(subtask, 'question_text', '')
        
        logger.info(f"Execute Node: 执行子任务 {i}/{len(subtasks)}: {question_id} - {question_text}")
        
        if task_type == "query":
            result = _execute_query_subtask(subtask, datasource_luid, tableau_config, metadata)
        elif task_type == "post_processing":
            result = _execute_processing_subtask(subtask, subtask_results)
        else:
            result = {"question_id": question_id, "success": False, "error": f"Unknown task type: {task_type}"}
        
        if result.get("success", False):
            subtask_results.append(result)
            logger.info(f"Execute Node: 子任务 {question_id} 执行成功")
        else:
            errors.append({"node": "execute", "question_id": question_id, "error": result.get("error", "Unknown error"), "timestamp": time.time()})
            logger.error(f"Execute Node: 子任务 {question_id} 执行失败: {result.get('error')}")
    
    execution_time = time.time() - start_time
    logger.info(f"Execute Node: 执行完成，耗时 {execution_time:.2f} 秒")
    logger.info(f"Execute Node: 成功 {len(subtask_results)}/{len(subtasks)} 个子任务")
    
    return {
        "subtask_results": subtask_results,
        "all_query_results": subtask_results,
        "current_stage": "insight",
        "execution_path": ["execute"],
        "errors": errors if errors else [],
        "performance": {"execute_time": execution_time, "subtask_count": len(subtasks), "success_count": len(subtask_results)}
    }


def _get_tableau_config(configurable: Dict[str, Any]) -> Dict[str, str]:
    """获取 Tableau 配置"""
    store = configurable.get("store")
    if store:
        try:
            from tableau_assistant.src.capabilities.storage import StoreManager
            from tableau_assistant.src.models.context import get_tableau_config
            store_manager = StoreManager(store)
            return get_tableau_config(store_manager)
        except Exception as e:
            logger.warning(f"从 Store 获取配置失败: {e}")
    
    try:
        from tableau_assistant.src.config.settings import settings
        return {
            "tableau_token": getattr(settings, 'tableau_token', ''),
            "tableau_site": settings.tableau_site,
            "tableau_domain": settings.tableau_domain
        }
    except Exception as e:
        logger.warning(f"从环境变量获取配置失败: {e}")
        return {}


def _get_subtasks(query_plan: Any) -> List[Any]:
    """获取子任务列表"""
    if hasattr(query_plan, 'subtasks'):
        return query_plan.subtasks
    elif isinstance(query_plan, dict):
        return query_plan.get('subtasks', [])
    return []


def _get_attr(obj: Any, attr: str, default: Any = None) -> Any:
    """安全获取属性"""
    if hasattr(obj, attr):
        return getattr(obj, attr)
    elif isinstance(obj, dict):
        return obj.get(attr, default)
    return default


def _execute_query_subtask(
    subtask: Any,
    datasource_luid: str,
    tableau_config: Dict[str, str],
    metadata: Optional[Any] = None
) -> Dict[str, Any]:
    """执行单个查询子任务"""
    question_id = _get_attr(subtask, 'question_id', 'unknown')
    question_text = _get_attr(subtask, 'question_text', '')
    
    try:
        from tableau_assistant.src.capabilities.query.executor.query_executor import QueryExecutor
        
        if metadata:
            executor = QueryExecutor(metadata=metadata)
            result = executor.execute_subtask(subtask=subtask, datasource_luid=datasource_luid, tableau_config=tableau_config)
        else:
            logger.warning("Execute Node: 缺少 metadata，使用基础执行模式")
            return {"question_id": question_id, "question_text": question_text, "success": False, "error": "Metadata required for query execution"}
        
        return {
            "question_id": question_id,
            "question_text": question_text,
            "success": True,
            "data": result.get("data", []),
            "row_count": result.get("row_count", 0),
            "columns": result.get("columns", []),
            "performance": result.get("performance", {})
        }
    except Exception as e:
        logger.error(f"Execute Node: 查询执行失败: {e}")
        return {"question_id": question_id, "success": False, "error": str(e)}


def _execute_processing_subtask(
    subtask: Any,
    previous_results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """执行数据处理子任务"""
    question_id = _get_attr(subtask, 'question_id', 'unknown')
    question_text = _get_attr(subtask, 'question_text', '')
    
    try:
        processing_instruction = _get_attr(subtask, 'processing_instruction')
        if not processing_instruction:
            return {"question_id": question_id, "success": False, "error": "Missing processing_instruction"}
        
        source_tasks = _get_attr(processing_instruction, 'source_tasks', [])
        source_data = []
        for task_id in source_tasks:
            for result in previous_results:
                if result.get("question_id") == task_id:
                    source_data.append(result.get("data", []))
                    break
        
        if not source_data:
            return {"question_id": question_id, "success": False, "error": f"Source data not found for tasks: {source_tasks}"}
        
        processing_type = _get_attr(processing_instruction, 'processing_type', 'merge')
        
        if processing_type == 'merge':
            processed_data = []
            for data in source_data:
                if isinstance(data, list):
                    processed_data.extend(data)
                else:
                    processed_data.append(data)
        else:
            processed_data = source_data
        
        return {
            "question_id": question_id,
            "question_text": question_text,
            "success": True,
            "data": processed_data,
            "row_count": len(processed_data) if isinstance(processed_data, list) else 0,
            "processing_type": processing_type
        }
    except Exception as e:
        logger.error(f"Execute Node: 数据处理失败: {e}")
        return {"question_id": question_id, "success": False, "error": str(e)}


__all__ = ["execute_query_node"]
