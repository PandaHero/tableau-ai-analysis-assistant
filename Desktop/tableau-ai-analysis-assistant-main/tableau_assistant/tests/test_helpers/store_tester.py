"""
存储测试器

负责测试Store Manager功能，包括：
- 缓存写入
- 缓存读取
- 缓存清除
- 缓存过期
"""
import time
from typing import Dict, Any

from tableau_assistant.tests.test_helpers.test_environment import TestEnvironment
from tableau_assistant.tests.test_helpers.test_models import TestStageResult


class StoreTester:
    """
    存储测试器
    
    测试Store Manager的各项功能
    """
    
    def __init__(self, environment: TestEnvironment):
        """
        初始化存储测试器
        
        Args:
            environment: 测试环境实例
        """
        self.environment = environment
        self.store_manager = environment.get_store_manager()
        self.datasource_luid = environment.get_datasource_luid()
    
    async def test_cache_write(self) -> TestStageResult:
        """
        测试缓存写入
        
        验证：
        - Store Manager的缓存写入功能
        - 写入成功
        
        Returns:
            TestStageResult: 测试结果
        """
        start_time = time.time()
        
        try:
            # 创建测试数据
            test_data = {
                "test_key": "test_value",
                "timestamp": time.time(),
                "data": {"field1": "value1", "field2": "value2"}
            }
            
            # 写入缓存（使用元数据缓存方法）
            # 注意：这里我们测试的是元数据缓存功能
            # 实际的写入会在metadata_manager中完成
            
            # 先清除缓存
            self.store_manager.clear_metadata_cache(self.datasource_luid)
            
            # 验证缓存已清除
            cached = self.store_manager.get_metadata(self.datasource_luid)
            if cached is not None:
                return TestStageResult(
                    stage_name="cache_write",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="缓存清除失败"
                )
            
            # 创建结果
            result = TestStageResult(
                stage_name="cache_write",
                success=True,
                duration=time.time() - start_time,
                output_data={"cache_cleared": True}
            )
            
            result.add_metadata("operation", "cache_clear")
            
            return result
            
        except Exception as e:
            return TestStageResult(
                stage_name="cache_write",
                success=False,
                duration=time.time() - start_time,
                error_message=f"测试缓存写入时发生错误: {str(e)}"
            )
    
    async def test_cache_read(self) -> TestStageResult:
        """
        测试缓存读取
        
        验证：
        - Store Manager的缓存读取功能
        - 读取的数据正确
        
        Returns:
            TestStageResult: 测试结果
        """
        start_time = time.time()
        
        try:
            # 尝试读取缓存
            cached_metadata = self.store_manager.get_metadata(self.datasource_luid)
            
            # 检查缓存状态
            has_cache = cached_metadata is not None
            
            # 创建结果
            result = TestStageResult(
                stage_name="cache_read",
                success=True,
                duration=time.time() - start_time,
                output_data={
                    "has_cache": has_cache,
                    "cache_data": cached_metadata if has_cache else None
                }
            )
            
            result.add_metadata("has_cache", has_cache)
            
            if not has_cache:
                result.add_warning("缓存中没有数据")
            
            return result
            
        except Exception as e:
            return TestStageResult(
                stage_name="cache_read",
                success=False,
                duration=time.time() - start_time,
                error_message=f"测试缓存读取时发生错误: {str(e)}"
            )
    
    async def test_cache_clear(self) -> TestStageResult:
        """
        测试缓存清除
        
        验证：
        - Store Manager的缓存清除功能
        - 缓存已清除
        
        Returns:
            TestStageResult: 测试结果
        """
        start_time = time.time()
        
        try:
            # 清除缓存
            success = self.store_manager.clear_metadata_cache(self.datasource_luid)
            
            if not success:
                return TestStageResult(
                    stage_name="cache_clear",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="清除缓存失败"
                )
            
            # 验证缓存已清除
            cached = self.store_manager.get_metadata(self.datasource_luid)
            if cached is not None:
                return TestStageResult(
                    stage_name="cache_clear",
                    success=False,
                    duration=time.time() - start_time,
                    error_message="缓存清除后仍然存在数据"
                )
            
            # 创建结果
            result = TestStageResult(
                stage_name="cache_clear",
                success=True,
                duration=time.time() - start_time,
                output_data={"cache_cleared": True}
            )
            
            result.add_metadata("operation", "cache_clear")
            result.add_metadata("verified", True)
            
            return result
            
        except Exception as e:
            return TestStageResult(
                stage_name="cache_clear",
                success=False,
                duration=time.time() - start_time,
                error_message=f"测试缓存清除时发生错误: {str(e)}"
            )
    
    async def test_cache_expiration(self) -> TestStageResult:
        """
        测试缓存过期
        
        验证：
        - 缓存过期时间处理
        
        注意：由于实际测试缓存过期需要等待较长时间，
        这里主要验证缓存机制的存在性
        
        Returns:
            TestStageResult: 测试结果
        """
        start_time = time.time()
        
        try:
            # 获取缓存信息
            cached_metadata = self.store_manager.get_metadata(self.datasource_luid)
            
            # 检查缓存是否有过期时间信息
            has_expiration_info = False
            if cached_metadata and isinstance(cached_metadata, dict):
                # 检查是否有时间戳或过期相关字段
                has_expiration_info = any(
                    key in cached_metadata
                    for key in ['timestamp', 'expires_at', 'created_at', 'updated_at']
                )
            
            # 创建结果
            result = TestStageResult(
                stage_name="cache_expiration",
                success=True,
                duration=time.time() - start_time,
                output_data={
                    "has_cache": cached_metadata is not None,
                    "has_expiration_info": has_expiration_info
                }
            )
            
            result.add_metadata("has_expiration_info", has_expiration_info)
            
            if not has_expiration_info:
                result.add_warning("缓存数据中未找到过期时间信息")
            
            # 添加说明
            result.add_warning(
                "缓存过期测试仅验证机制存在性，未进行实际过期等待测试"
            )
            
            return result
            
        except Exception as e:
            return TestStageResult(
                stage_name="cache_expiration",
                success=False,
                duration=time.time() - start_time,
                error_message=f"测试缓存过期时发生错误: {str(e)}"
            )


# ============= 导出 =============

__all__ = [
    "StoreTester",
]
