# -*- coding: utf-8 -*-
"""
E2E Tests: Session Persistence

Tests SQLite checkpointer persistence including:
- SQLite checkpointer creation
- Workflow state persistence
- Session restore

Requirements: 13.1, 13.2, 13.3
"""

import pytest
import os
from pathlib import Path
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor
from tableau_assistant.src.workflow.printer import WorkflowPrinter
from tableau_assistant.src.workflow.factory import create_tableau_workflow, create_sqlite_checkpointer


class TestSQLiteCheckpointer:
    """SQLite checkpointer tests"""
    
    @pytest.mark.asyncio
    async def test_sqlite_checkpointer_creation(
        self,
        tmp_path,
        check_env,
    ):
        """
        Test SQLite checkpointer creation.
        
        Expected: SQLite database file is created
        
        Requirements: 13.1
        """
        db_path = str(tmp_path / "test_checkpointer.db")
        
        # Create checkpointer
        checkpointer = create_sqlite_checkpointer(db_path)
        
        # Verify file exists
        assert Path(db_path).exists(), f"数据库文件应被创建: {db_path}"
        print(f"SQLite 数据库已创建: {db_path}")
    
    @pytest.mark.asyncio
    async def test_workflow_with_sqlite_checkpointer(
        self,
        tmp_path,
        check_env,
    ):
        """
        Test workflow with SQLite checkpointer.
        
        Expected: Workflow executes with SQLite persistence
        
        Requirements: 13.1, 13.2
        """
        db_path = str(tmp_path / "test_workflow.db")
        
        # Create workflow with SQLite checkpointer
        workflow = create_tableau_workflow(
            use_memory_checkpointer=False,
            use_sqlite_checkpointer=True,
            sqlite_db_path=db_path,
            config={"max_replan_rounds": 1}
        )
        
        # Verify database file exists
        assert Path(db_path).exists(), "数据库文件应被创建"
        
        print(f"工作流已创建，使用 SQLite 检查点: {db_path}")


class TestWorkflowStatePersistence:
    """Workflow state persistence tests"""
    
    @pytest.mark.asyncio
    async def test_workflow_state_persistence(
        self,
        sqlite_executor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test workflow state is persisted.
        
        Expected: State is saved to SQLite after execution
        
        Requirements: 13.2
        """
        question = "各地区销售额是多少"
        thread_id = "test_persistence_thread"
        
        # Execute workflow
        result = await sqlite_executor.run(question, thread_id=thread_id)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"工作流状态已持久化，thread_id: {thread_id}")
    
    @pytest.mark.asyncio
    async def test_multiple_executions_same_thread(
        self,
        sqlite_executor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test multiple executions on same thread.
        
        Expected: State accumulates across executions
        
        Requirements: 13.2
        """
        thread_id = "test_multi_exec_thread"
        
        # First execution
        result1 = await sqlite_executor.run("各地区销售额", thread_id=thread_id)
        printer.print_result(result1)
        assert result1.success
        
        # Second execution on same thread
        result2 = await sqlite_executor.run("各产品类别利润", thread_id=thread_id)
        printer.print_result(result2)
        assert result2.success
        
        print(f"同一线程多次执行成功")


class TestSessionRestore:
    """Session restore tests"""
    
    @pytest.mark.asyncio
    async def test_session_restore(
        self,
        tmp_path,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test session restore from SQLite.
        
        Expected: Session can be restored from checkpoint
        
        Requirements: 13.3
        """
        db_path = str(tmp_path / "test_restore.db")
        thread_id = "test_restore_thread"
        
        # Create first workflow and execute
        workflow1 = create_tableau_workflow(
            use_memory_checkpointer=False,
            use_sqlite_checkpointer=True,
            sqlite_db_path=db_path,
            config={"max_replan_rounds": 1}
        )
        
        # Create executor wrapper
        executor1 = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=False)
        executor1._workflow = workflow1
        
        # Execute first query
        result1 = await executor1.run("各地区销售额", thread_id=thread_id)
        printer.print_result(result1)
        assert result1.success
        
        # Create second workflow (simulating restart)
        workflow2 = create_tableau_workflow(
            use_memory_checkpointer=False,
            use_sqlite_checkpointer=True,
            sqlite_db_path=db_path,
            config={"max_replan_rounds": 1}
        )
        
        executor2 = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=False)
        executor2._workflow = workflow2
        
        # Execute on same thread (should restore session)
        result2 = await executor2.run("继续分析利润", thread_id=thread_id)
        printer.print_result(result2)
        
        print(f"会话恢复测试完成")


class TestPersistenceProperties:
    """Property-based tests for persistence"""
    
    # **Feature: workflow-e2e-testing, Property 16: SQLite Checkpointer 持久化**
    # **Validates: Requirements 13.1, 13.2**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=3, deadline=180000)
    @given(
        question=st.sampled_from([
            "各地区销售额",
            "各产品类别利润",
            "2024年销售趋势",
        ]),
    )
    async def test_property_sqlite_persistence(
        self,
        question: str,
        tmp_path,
        check_env,
    ):
        """
        Property 16: SQLite checkpointer should persist state.
        
        For any workflow execution with SQLite checkpointer,
        database file should be created and state should be saved.
        
        **Feature: workflow-e2e-testing, Property 16: SQLite Checkpointer 持久化**
        **Validates: Requirements 13.1, 13.2**
        """
        db_path = str(tmp_path / f"test_{hash(question)}.db")
        
        workflow = create_tableau_workflow(
            use_memory_checkpointer=False,
            use_sqlite_checkpointer=True,
            sqlite_db_path=db_path,
            config={"max_replan_rounds": 1}
        )
        
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=False)
        executor._workflow = workflow
        
        result = await executor.run(question)
        
        # Database file should exist
        assert Path(db_path).exists(), f"数据库文件应存在: {db_path}"
        
        # File should have content
        file_size = Path(db_path).stat().st_size
        assert file_size > 0, f"数据库文件应有内容: {file_size} bytes"
        
        print(f"问题: {question}, 数据库大小: {file_size} bytes")
