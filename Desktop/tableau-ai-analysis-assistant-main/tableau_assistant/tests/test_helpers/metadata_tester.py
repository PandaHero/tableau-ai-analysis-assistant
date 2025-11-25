"""
元数据测试器

负责测试元数据管理功能，包括：
- 元数据获取
- 元数据缓存
- 增强元数据
- 维度层级
"""
import time
from typing import Tuple

from tableau_assistant.tests.test_helpers.test_environment import TestEnvironment
from tableau_assistant.tests.test_helpers.test_models import TestStageResult


class MetadataTester:
    """
    元数据测试器
    
    测试Metadata Manager的各项功能
    """
    
    def __init__(self, environment: TestEnvironment):
        """
        初始化元数据测试器
        
        Args:
            environment: 测试环境实例
        """
        self.environment = environment
        self.metadata_manager = environment.get_metadata_manager()
        self.store_manager = environment.get_store_manager()
        self.datasource_luid = environment.get_datasource_luid()
    
    async def test_metadata_fetch(self) -> TestStageResult:
        """
        测试元数据获取
        
        验证：
        - 成功获取元数据
        - 元数据包含必要字段
        - 显示统计信息
        
        Returns:
            TestStageResult: 测试结果
        """
        start_time = time.time()
        
        try:
            # 获取元数据
            metadata = await self.metadata_manager.get_metadata_async(
                use_cache=True,
                enhance=False
            )
            
            # 验证元数据
            if not metadata:
                return TestStageResult(
                    stage_name="metadata_fetch",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="未能获取元数据"
                )
            
            # 验证必要字段
            if not metadata.datasource_name:
                return TestStageResult(
                    stage_name="metadata_fetch",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="元数据缺少数据源名称"
                )
            
            if not metadata.fields:
                return TestStageResult(
                    stage_name="metadata_fetch",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="元数据缺少字段列表"
                )
            
            # 统计信息
            dimensions = metadata.get_dimensions()
            measures = metadata.get_measures()
            
            # 创建成功结果
            result = TestStageResult(
                stage_name="metadata_fetch",
                success=True,
                duration=time.time() - start_time,
                output_data={
                    "datasource_name": metadata.datasource_name,
                    "field_count": metadata.field_count,
                    "dimension_count": len(dimensions),
                    "measure_count": len(measures)
                }
            )
            
            # 添加元数据
            result.add_metadata("datasource_name", metadata.datasource_name)
            result.add_metadata("field_count", metadata.field_count)
            result.add_metadata("dimension_count", len(dimensions))
            result.add_metadata("measure_count", len(measures))
            
            return result
            
        except Exception as e:
            return TestStageResult(
                stage_name="metadata_fetch",
                success=False,
                duration=time.time() - start_time,
                error_message=f"获取元数据时发生错误: {str(e)}"
            )
    
    async def test_metadata_cache(self) -> TestStageResult:
        """
        测试元数据缓存
        
        验证：
        - 首次获取（无缓存）
        - 第二次获取（从缓存）
        - 缓存读写功能
        
        Returns:
            TestStageResult: 测试结果
        """
        start_time = time.time()
        
        try:
            # 清除缓存
            self.store_manager.clear_metadata_cache(self.datasource_luid)
            
            # 首次获取（无缓存）
            fetch_start = time.time()
            metadata1 = await self.metadata_manager.get_metadata_async(
                use_cache=True,
                enhance=False
            )
            fetch_duration = time.time() - fetch_start
            
            if not metadata1:
                return TestStageResult(
                    stage_name="metadata_cache",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="首次获取元数据失败"
                )
            
            # 第二次获取（从缓存）
            cache_start = time.time()
            metadata2 = await self.metadata_manager.get_metadata_async(
                use_cache=True,
                enhance=False
            )
            cache_duration = time.time() - cache_start
            
            if not metadata2:
                return TestStageResult(
                    stage_name="metadata_cache",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="从缓存获取元数据失败"
                )
            
            # 验证缓存加速效果
            if cache_duration >= fetch_duration:
                result = TestStageResult(
                    stage_name="metadata_cache",
                    success=True,
                    duration=time.time() - start_time,
                    output_data={
                        "fetch_duration": fetch_duration,
                        "cache_duration": cache_duration
                    }
                )
                result.add_warning(
                    f"缓存读取时间({cache_duration:.3f}s)未明显快于首次获取({fetch_duration:.3f}s)"
                )
            else:
                result = TestStageResult(
                    stage_name="metadata_cache",
                    success=True,
                    duration=time.time() - start_time,
                    output_data={
                        "fetch_duration": fetch_duration,
                        "cache_duration": cache_duration,
                        "speedup": fetch_duration / cache_duration
                    }
                )
            
            result.add_metadata("fetch_duration_ms", int(fetch_duration * 1000))
            result.add_metadata("cache_duration_ms", int(cache_duration * 1000))
            
            return result
            
        except Exception as e:
            return TestStageResult(
                stage_name="metadata_cache",
                success=False,
                duration=time.time() - start_time,
                error_message=f"测试缓存时发生错误: {str(e)}"
            )
    
    async def test_enhanced_metadata(self) -> TestStageResult:
        """
        测试增强元数据
        
        验证：
        - 获取增强元数据
        - 维度层级信息
        - 最大日期信息
        
        Returns:
            TestStageResult: 测试结果
        """
        start_time = time.time()
        
        try:
            # 获取增强元数据
            metadata = await self.metadata_manager.get_metadata_async(
                use_cache=False,
                enhance=True
            )
            
            if not metadata:
                return TestStageResult(
                    stage_name="enhanced_metadata",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="未能获取增强元数据"
                )
            
            # 检查维度层级
            has_hierarchy = metadata.dimension_hierarchy is not None
            hierarchy_count = len(metadata.dimension_hierarchy) if has_hierarchy else 0
            
            # 检查日期字段的valid_max_date
            date_fields_with_max_date = []
            for field in metadata.fields:
                if field.role.upper() == "DIMENSION" and field.valid_max_date:
                    date_fields_with_max_date.append({
                        'name': field.name,
                        'dataType': field.dataType,
                        'valid_max_date': field.valid_max_date
                    })
            
            # 创建结果
            result = TestStageResult(
                stage_name="enhanced_metadata",
                success=True,
                duration=time.time() - start_time,
                output_data={
                    "has_hierarchy": has_hierarchy,
                    "hierarchy_count": hierarchy_count,
                    "date_fields_count": len(date_fields_with_max_date)
                }
            )
            
            result.add_metadata("has_hierarchy", has_hierarchy)
            result.add_metadata("hierarchy_count", hierarchy_count)
            result.add_metadata("date_fields_with_max_date", len(date_fields_with_max_date))
            
            if not has_hierarchy:
                result.add_warning("未找到维度层级信息")
            
            if not date_fields_with_max_date:
                result.add_warning("未找到带有valid_max_date的日期字段")
            
            return result
            
        except Exception as e:
            return TestStageResult(
                stage_name="enhanced_metadata",
                success=False,
                duration=time.time() - start_time,
                error_message=f"获取增强元数据时发生错误: {str(e)}"
            )
    
    async def test_dimension_hierarchy(self) -> TestStageResult:
        """
        测试维度层级
        
        验证：
        - 维度层级的完整性
        - 层级数量和结构
        
        Returns:
            TestStageResult: 测试结果
        """
        start_time = time.time()
        
        try:
            # 获取增强元数据（包含维度层级）
            metadata = await self.metadata_manager.get_metadata_async(
                use_cache=True,
                enhance=True
            )
            
            if not metadata:
                return TestStageResult(
                    stage_name="dimension_hierarchy",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="未能获取元数据"
                )
            
            # 检查维度层级
            if not metadata.dimension_hierarchy:
                return TestStageResult(
                    stage_name="dimension_hierarchy",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="未找到维度层级信息"
                )
            
            # 统计层级信息
            hierarchy_count = len(metadata.dimension_hierarchy)
            total_levels = sum(
                len(hierarchy.get("levels", []))
                for hierarchy in metadata.dimension_hierarchy
                if isinstance(hierarchy, dict)
            )
            
            # 创建结果
            result = TestStageResult(
                stage_name="dimension_hierarchy",
                success=True,
                duration=time.time() - start_time,
                output_data={
                    "hierarchy_count": hierarchy_count,
                    "total_levels": total_levels,
                    "hierarchies": metadata.dimension_hierarchy
                }
            )
            
            result.add_metadata("hierarchy_count", hierarchy_count)
            result.add_metadata("total_levels", total_levels)
            
            return result
            
        except Exception as e:
            return TestStageResult(
                stage_name="dimension_hierarchy",
                success=False,
                duration=time.time() - start_time,
                error_message=f"测试维度层级时发生错误: {str(e)}"
            )


# ============= 导出 =============

__all__ = [
    "MetadataTester",
]
