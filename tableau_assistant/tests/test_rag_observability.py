"""
RAG 可观测性模块测试

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**
"""
import pytest
import time
from unittest.mock import MagicMock

from tableau_assistant.src.capabilities.rag.observability import (
    RAGStage,
    RetrievalLogEntry,
    RerankLogEntry,
    ErrorLogEntry,
    RAGMetrics,
    RAGObserver,
    get_observer,
    set_verbose,
)


class TestRetrievalLogEntry:
    """检索日志条目测试"""
    
    def test_create_entry(self):
        """测试创建日志条目"""
        entry = RetrievalLogEntry(
            query_text="销售额",
            candidate_count=10,
            top_scores=[0.95, 0.88, 0.75],
            latency_ms=50,
            source="vector"
        )
        
        assert entry.query_text == "销售额"
        assert entry.candidate_count == 10
        assert len(entry.top_scores) == 3
        assert entry.latency_ms == 50
    
    def test_to_dict(self):
        """测试转换为字典"""
        entry = RetrievalLogEntry(
            query_text="销售额",
            candidate_count=10,
            top_scores=[0.95, 0.88, 0.75],
            latency_ms=50,
        )
        
        data = entry.to_dict()
        
        assert data["query_text"] == "销售额"
        assert data["candidate_count"] == 10
        assert "timestamp" in data
    
    def test_str_representation(self):
        """测试字符串表示"""
        entry = RetrievalLogEntry(
            query_text="销售额",
            candidate_count=10,
            top_scores=[0.95, 0.88, 0.75],
            latency_ms=50,
        )
        
        s = str(entry)
        
        assert "销售额" in s
        assert "10" in s
        assert "50ms" in s


class TestRerankLogEntry:
    """Rerank 日志条目测试"""
    
    def test_create_entry(self):
        """测试创建日志条目"""
        entry = RerankLogEntry(
            query_text="销售额",
            before_ranking=["field_a", "field_b", "field_c"],
            after_ranking=["field_b", "field_a", "field_c"],
            score_changes={"field_a": -0.1, "field_b": 0.15, "field_c": 0.0},
            latency_ms=30,
            reranker_type="RRF"
        )
        
        assert entry.query_text == "销售额"
        assert entry.before_ranking[0] == "field_a"
        assert entry.after_ranking[0] == "field_b"
        assert entry.reranker_type == "RRF"
    
    def test_to_dict(self):
        """测试转换为字典"""
        entry = RerankLogEntry(
            query_text="销售额",
            before_ranking=["field_a", "field_b"],
            after_ranking=["field_b", "field_a"],
            score_changes={"field_a": -0.1, "field_b": 0.15},
            latency_ms=30,
        )
        
        data = entry.to_dict()
        
        assert data["query_text"] == "销售额"
        assert "before_ranking" in data
        assert "after_ranking" in data


class TestErrorLogEntry:
    """错误日志条目测试"""
    
    def test_create_entry(self):
        """测试创建日志条目"""
        entry = ErrorLogEntry(
            query_text="销售额",
            stage=RAGStage.RETRIEVAL,
            error_message="Connection timeout",
            stack_trace="Traceback..."
        )
        
        assert entry.query_text == "销售额"
        assert entry.stage == RAGStage.RETRIEVAL
        assert entry.error_message == "Connection timeout"
    
    def test_to_dict(self):
        """测试转换为字典"""
        entry = ErrorLogEntry(
            query_text="销售额",
            stage=RAGStage.EMBEDDING,
            error_message="API error",
            stack_trace="Traceback..."
        )
        
        data = entry.to_dict()
        
        assert data["stage"] == "embedding"
        assert data["error_message"] == "API error"


class TestRAGMetrics:
    """RAG 指标测试"""
    
    def test_initial_metrics(self):
        """测试初始指标"""
        metrics = RAGMetrics()
        
        assert metrics.total_queries == 0
        assert metrics.avg_retrieval_latency == 0.0
        assert metrics.cache_hit_rate == 0.0
        assert metrics.llm_skip_rate == 0.0
    
    def test_avg_retrieval_latency(self):
        """测试平均检索延迟计算"""
        metrics = RAGMetrics()
        metrics.total_queries = 10
        metrics.total_retrieval_latency_ms = 500
        
        assert metrics.avg_retrieval_latency == 50.0
    
    def test_cache_hit_rate(self):
        """测试缓存命中率计算"""
        metrics = RAGMetrics()
        metrics.total_queries = 100
        metrics.cache_hits = 30
        
        assert metrics.cache_hit_rate == 0.3
    
    def test_llm_skip_rate(self):
        """测试 LLM 跳过率计算"""
        metrics = RAGMetrics()
        metrics.total_queries = 100
        metrics.llm_skips = 60
        
        assert metrics.llm_skip_rate == 0.6
    
    def test_reset(self):
        """测试重置指标"""
        metrics = RAGMetrics()
        metrics.total_queries = 100
        metrics.cache_hits = 30
        
        metrics.reset()
        
        assert metrics.total_queries == 0
        assert metrics.cache_hits == 0


class TestRAGObserver:
    """RAG 观察器测试"""
    
    @pytest.fixture
    def observer(self):
        """创建观察器实例"""
        return RAGObserver(verbose=False)
    
    def test_log_retrieval(self, observer):
        """
        测试记录检索日志
        
        **Validates: Requirements 8.1**
        """
        entry = observer.log_retrieval(
            query_text="销售额",
            candidate_count=10,
            top_scores=[0.95, 0.88, 0.75],
            latency_ms=50,
        )
        
        assert entry.query_text == "销售额"
        
        # 验证指标更新
        metrics = observer.get_metrics()
        assert metrics["total_queries"] == 1
        assert metrics["avg_retrieval_latency"] == 50.0
    
    def test_log_rerank(self, observer):
        """
        测试记录 Rerank 日志
        
        **Validates: Requirements 8.2**
        """
        entry = observer.log_rerank(
            query_text="销售额",
            before_ranking=["field_a", "field_b"],
            after_ranking=["field_b", "field_a"],
            before_scores={"field_a": 0.9, "field_b": 0.8},
            after_scores={"field_a": 0.85, "field_b": 0.95},
            latency_ms=30,
            reranker_type="RRF"
        )
        
        assert entry.query_text == "销售额"
        assert abs(entry.score_changes["field_b"] - 0.15) < 0.001  # 0.95 - 0.8
    
    def test_log_error(self, observer):
        """
        测试记录错误日志
        
        **Validates: Requirements 8.3**
        """
        try:
            raise ValueError("Test error")
        except Exception as e:
            entry = observer.log_error(
                query_text="销售额",
                stage=RAGStage.RETRIEVAL,
                error=e
            )
        
        assert entry.error_message == "Test error"
        assert entry.stage == RAGStage.RETRIEVAL
        
        # 验证指标更新
        metrics = observer.get_metrics()
        assert metrics["errors"] == 1
    
    def test_verbose_mode(self, observer):
        """
        测试 verbose 模式
        
        **Validates: Requirements 8.4**
        """
        observer.set_verbose(True)
        assert observer.verbose is True
        
        observer.set_verbose(False)
        assert observer.verbose is False
    
    def test_trace_context_manager(self, observer):
        """
        测试跟踪上下文管理器
        
        **Validates: Requirements 8.4**
        """
        observer.set_verbose(True)
        
        with observer.trace(RAGStage.RETRIEVAL, "test query") as start_time:
            time.sleep(0.01)  # 模拟处理
        
        # 应该没有抛出异常
        assert True
    
    def test_trace_with_error(self, observer):
        """测试跟踪上下文管理器处理错误"""
        with pytest.raises(ValueError):
            with observer.trace(RAGStage.EMBEDDING, "test query"):
                raise ValueError("Test error")
        
        # 验证错误被记录
        errors = observer.get_error_logs()
        assert len(errors) == 1
        assert errors[0]["stage"] == "embedding"
    
    def test_get_metrics(self, observer):
        """
        测试获取指标
        
        **Validates: Requirements 8.5**
        """
        # 记录一些操作
        observer.log_retrieval("q1", 10, [0.9], 50)
        observer.log_retrieval("q2", 8, [0.85], 60)
        observer.log_cache_hit()
        observer.log_llm_skip()
        
        metrics = observer.get_metrics()
        
        assert metrics["total_queries"] == 2
        assert metrics["avg_retrieval_latency"] == 55.0  # (50+60)/2
        assert metrics["cache_hit_rate"] == 0.5  # 1/2
        assert metrics["llm_skip_rate"] == 0.5  # 1/2
    
    def test_callback(self, observer):
        """测试回调函数"""
        callback_called = []
        
        def on_retrieval(entry):
            callback_called.append(entry)
        
        observer.on_retrieval(on_retrieval)
        observer.log_retrieval("test", 5, [0.9], 30)
        
        assert len(callback_called) == 1
        assert callback_called[0].query_text == "test"
    
    def test_reset(self, observer):
        """测试重置"""
        observer.log_retrieval("q1", 10, [0.9], 50)
        observer.log_cache_hit()
        
        observer.reset()
        
        metrics = observer.get_metrics()
        assert metrics["total_queries"] == 0
        assert len(observer.get_retrieval_logs()) == 0
    
    def test_max_log_entries(self):
        """测试最大日志条目限制"""
        observer = RAGObserver(max_log_entries=5)
        
        for i in range(10):
            observer.log_retrieval(f"query_{i}", 5, [0.9], 30)
        
        logs = observer.get_retrieval_logs()
        assert len(logs) == 5
        # 应该保留最新的 5 条
        assert logs[0]["query_text"] == "query_5"


class TestGlobalObserver:
    """全局观察器测试"""
    
    def test_get_observer(self):
        """测试获取全局观察器"""
        observer1 = get_observer()
        observer2 = get_observer()
        
        # 应该是同一个实例
        assert observer1 is observer2
    
    def test_set_verbose(self):
        """测试设置全局 verbose 模式"""
        set_verbose(True)
        assert get_observer().verbose is True
        
        set_verbose(False)
        assert get_observer().verbose is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
