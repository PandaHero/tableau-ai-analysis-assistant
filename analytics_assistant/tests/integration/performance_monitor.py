"""性能监控器

收集和分析性能指标：
- 收集性能指标（耗时、内存、API 调用次数）
- 存储性能数据到文件
- 分析性能趋势
- 检测性能退化
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import logging


logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """性能指标数据模型"""
    test_name: str
    timestamp: datetime
    elapsed_time: float
    memory_usage_mb: float
    llm_calls: int = 0
    embedding_calls: int = 0
    tableau_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class PerformanceMonitor:
    """性能监控器
    
    职责：
    - 收集性能指标
    - 存储性能数据
    - 分析性能趋势
    - 检测性能退化
    
    使用方式：
        monitor = PerformanceMonitor(output_dir=Path("tests/test_outputs"))
        
        # 记录指标
        metric = PerformanceMetric(
            test_name="test_something",
            timestamp=datetime.now(),
            elapsed_time=1.5,
            memory_usage_mb=100.0,
        )
        monitor.record_metric(metric)
        
        # 保存到文件
        monitor.save_metrics()
        
        # 检查性能退化
        has_regression = monitor.check_regression(metric, threshold=1.2)
    """
    
    def __init__(self, output_dir: Path, baseline_file: Optional[Path] = None):
        """初始化性能监控器
        
        Args:
            output_dir: 性能数据输出目录
            baseline_file: 基线文件路径，默认使用 output_dir/performance_baseline.json
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_file = baseline_file or (self.output_dir / "performance_baseline.json")
        self._metrics: list[PerformanceMetric] = []
        
        logger.info(
            "性能监控器初始化: output_dir=%s baseline_file=%s",
            output_dir,
            self.baseline_file,
        )
    
    def record_metric(self, metric: PerformanceMetric):
        """记录性能指标
        
        Args:
            metric: 性能指标对象
        """
        self._metrics.append(metric)
        logger.debug(
            f"记录性能指标: {metric.test_name}, "
            f"耗时={metric.elapsed_time:.2f}s, "
            f"内存={metric.memory_usage_mb:.1f}MB"
        )
    
    def save_metrics(self) -> Path:
        """保存性能指标到文件
        
        将收集的性能指标保存为 JSON 文件。
        文件名包含时间戳，避免覆盖。
        
        Returns:
            保存的文件路径
        """
        if not self._metrics:
            logger.warning("没有性能指标需要保存")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"performance_{timestamp}.json"
        
        # 转换为可序列化的字典
        data = [
            {
                "test_name": m.test_name,
                "timestamp": m.timestamp.isoformat(),
                "elapsed_time": m.elapsed_time,
                "memory_usage_mb": m.memory_usage_mb,
                "llm_calls": m.llm_calls,
                "embedding_calls": m.embedding_calls,
                "tableau_calls": m.tableau_calls,
                "cache_hits": m.cache_hits,
                "cache_misses": m.cache_misses,
                "metadata": m.metadata,
            }
            for m in self._metrics
        ]
        
        # 保存到文件
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"性能指标已保存: {output_file}, 共 {len(self._metrics)} 条")
        return output_file
    
    def get_baseline(self, test_name: str) -> Optional[PerformanceMetric]:
        """获取性能基线
        
        从基线文件中读取指定测试的基线性能。
        
        Args:
            test_name: 测试名称
        
        Returns:
            基线性能指标，如果不存在返回 None
        """
        if not self.baseline_file.exists():
            logger.debug("基线文件不存在: %s", self.baseline_file)
            return None
        
        try:
            with open(self.baseline_file, "r", encoding="utf-8") as f:
                baselines = json.load(f)
            
            if test_name not in baselines:
                logger.debug(f"测试 {test_name} 没有基线数据")
                return None
            
            baseline_data = baselines[test_name]
            
            # 转换为 PerformanceMetric 对象
            baseline = PerformanceMetric(
                test_name=baseline_data["test_name"],
                timestamp=datetime.fromisoformat(baseline_data["timestamp"]),
                elapsed_time=baseline_data["elapsed_time"],
                memory_usage_mb=baseline_data["memory_usage_mb"],
                llm_calls=baseline_data.get("llm_calls", 0),
                embedding_calls=baseline_data.get("embedding_calls", 0),
                tableau_calls=baseline_data.get("tableau_calls", 0),
                cache_hits=baseline_data.get("cache_hits", 0),
                cache_misses=baseline_data.get("cache_misses", 0),
                metadata=baseline_data.get("metadata", {}),
            )
            
            logger.debug(f"加载基线: {test_name}, 耗时={baseline.elapsed_time:.2f}s")
            return baseline
            
        except Exception as e:
            logger.error(f"加载基线失败: {e}")
            return None
    
    def check_regression(
        self,
        metric: PerformanceMetric,
        threshold: float = 1.2,
    ) -> bool:
        """检查性能退化
        
        对比当前性能与基线性能，判断是否发生退化。
        
        Args:
            metric: 当前性能指标
            threshold: 退化阈值（如 1.2 表示慢 20% 视为退化）
        
        Returns:
            True 如果检测到性能退化
        """
        baseline = self.get_baseline(metric.test_name)
        
        if baseline is None:
            logger.info(f"测试 {metric.test_name} 没有基线，跳过退化检测")
            return False
        
        # 计算性能比率
        time_ratio = metric.elapsed_time / baseline.elapsed_time
        memory_ratio = metric.memory_usage_mb / baseline.memory_usage_mb
        
        # 检查是否超过阈值
        has_time_regression = time_ratio > threshold
        has_memory_regression = memory_ratio > threshold
        
        if has_time_regression:
            regression_pct = (time_ratio - 1) * 100
            logger.warning(
                f"检测到时间性能退化: {metric.test_name}\n"
                f"  当前: {metric.elapsed_time:.2f}s\n"
                f"  基线: {baseline.elapsed_time:.2f}s\n"
                f"  退化: {regression_pct:.1f}%"
            )
        
        if has_memory_regression:
            regression_pct = (memory_ratio - 1) * 100
            logger.warning(
                f"检测到内存性能退化: {metric.test_name}\n"
                f"  当前: {metric.memory_usage_mb:.1f}MB\n"
                f"  基线: {baseline.memory_usage_mb:.1f}MB\n"
                f"  退化: {regression_pct:.1f}%"
            )
        
        return has_time_regression or has_memory_regression
    
    def get_summary(self) -> Dict[str, Any]:
        """获取性能指标摘要
        
        Returns:
            包含统计信息的字典
        """
        if not self._metrics:
            return {
                "total_tests": 0,
                "avg_elapsed_time": 0.0,
                "max_elapsed_time": 0.0,
                "min_elapsed_time": 0.0,
                "total_llm_calls": 0,
                "total_embedding_calls": 0,
                "total_tableau_calls": 0,
            }
        
        elapsed_times = [m.elapsed_time for m in self._metrics]
        
        summary = {
            "total_tests": len(self._metrics),
            "avg_elapsed_time": sum(elapsed_times) / len(elapsed_times),
            "max_elapsed_time": max(elapsed_times),
            "min_elapsed_time": min(elapsed_times),
            "total_llm_calls": sum(m.llm_calls for m in self._metrics),
            "total_embedding_calls": sum(m.embedding_calls for m in self._metrics),
            "total_tableau_calls": sum(m.tableau_calls for m in self._metrics),
            "total_cache_hits": sum(m.cache_hits for m in self._metrics),
            "total_cache_misses": sum(m.cache_misses for m in self._metrics),
        }
        
        logger.info(f"性能摘要: {summary}")
        return summary
    
    def clear_metrics(self):
        """清空已收集的性能指标"""
        self._metrics.clear()
        logger.debug("性能指标已清空")
