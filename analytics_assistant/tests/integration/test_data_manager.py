"""测试数据管理器

管理测试数据的加载、验证和查询：
- 从 YAML 文件加载测试问题
- 验证测试数据的完整性
- 提供测试数据查询接口
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import yaml
import logging
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class TestQuestion(BaseModel):
    """测试问题模型
    
    定义标准测试问题的数据结构。
    """
    __test__ = False

    id: str = Field(..., description="问题唯一标识")
    question: str = Field(..., description="用户问题文本")
    category: str = Field(..., description="问题类别: simple, complex, time_series, etc.")
    expected_intent: str = Field(..., description="期望的意图: DATA_QUERY, CLARIFICATION, IRRELEVANT")
    expected_dimensions: list[str] = Field(default_factory=list, description="期望的维度字段")
    expected_measures: list[str] = Field(default_factory=list, description="期望的度量字段")
    expected_filters: Optional[list[Dict[str, Any]]] = Field(None, description="期望的筛选条件")
    expected_confidence_min: float = Field(0.7, description="最低置信度")
    description: str = Field(..., description="测试目的说明")
    tags: list[str] = Field(default_factory=list, description="测试标签: smoke, core, etc.")


class TestDataManager:
    """测试数据管理器
    
    职责：
    - 加载测试问题和预期结果
    - 验证测试数据的完整性
    - 提供测试数据查询接口
    
    使用方式：
        manager = TestDataManager(data_dir=Path("tests/integration/test_data"))
        questions = manager.get_questions_by_category("simple")
    """
    __test__ = False
    
    def __init__(self, data_dir: Path):
        """初始化测试数据管理器
        
        Args:
            data_dir: 测试数据目录路径
        """
        self.data_dir = data_dir
        self._questions: list[TestQuestion] = []
        self._load_test_data()
    
    def _load_test_data(self):
        """加载测试数据
        
        从 questions.yaml 文件加载测试问题。
        
        Raises:
            FileNotFoundError: 如果测试数据文件不存在
            ValueError: 如果测试数据格式不正确
        """
        questions_file = self.data_dir / "questions.yaml"
        
        if not questions_file.exists():
            logger.warning(f"测试数据文件不存在: {questions_file}")
            logger.warning("将使用空的测试数据集")
            return
        
        try:
            with open(questions_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            
            if not data or "questions" not in data:
                logger.warning(f"测试数据文件格式不正确: {questions_file}")
                return
            
            # 解析测试问题
            questions_data = data.get("questions", [])
            self._questions = [TestQuestion(**q) for q in questions_data]
            
            logger.info(f"加载了 {len(self._questions)} 个测试问题")
            
            # 统计各类别的问题数量
            categories = {}
            for q in self._questions:
                categories[q.category] = categories.get(q.category, 0) + 1
            
            logger.info(f"测试问题分类统计: {categories}")
            
        except Exception as e:
            logger.error(f"加载测试数据失败: {e}")
            raise ValueError(f"加载测试数据失败: {e}") from e
    
    def get_questions_by_category(self, category: str) -> list[TestQuestion]:
        """按类别获取测试问题
        
        Args:
            category: 问题类别（如 simple, complex, time_series）
        
        Returns:
            该类别的所有测试问题
        """
        questions = [q for q in self._questions if q.category == category]
        logger.debug(f"类别 '{category}' 有 {len(questions)} 个测试问题")
        return questions
    
    def get_question_by_id(self, question_id: str) -> Optional[TestQuestion]:
        """按 ID 获取测试问题
        
        Args:
            question_id: 问题唯一标识
        
        Returns:
            测试问题，如果不存在返回 None
        """
        for q in self._questions:
            if q.id == question_id:
                logger.debug(f"找到测试问题: {question_id}")
                return q
        
        logger.warning(f"未找到测试问题: {question_id}")
        return None
    
    def get_questions_by_tag(self, tag: str) -> list[TestQuestion]:
        """按标签获取测试问题
        
        Args:
            tag: 测试标签（如 smoke, core）
        
        Returns:
            包含该标签的所有测试问题
        """
        questions = [q for q in self._questions if tag in q.tags]
        logger.debug(f"标签 '{tag}' 有 {len(questions)} 个测试问题")
        return questions
    
    def get_all_questions(self) -> list[TestQuestion]:
        """获取所有测试问题
        
        Returns:
            所有测试问题列表
        """
        return self._questions
    
    def get_categories(self) -> list[str]:
        """获取所有问题类别
        
        Returns:
            所有唯一的问题类别列表
        """
        categories = list(set(q.category for q in self._questions))
        return sorted(categories)
    
    def get_tags(self) -> list[str]:
        """获取所有测试标签
        
        Returns:
            所有唯一的测试标签列表
        """
        tags = set()
        for q in self._questions:
            tags.update(q.tags)
        return sorted(tags)
    
    def validate_test_data(self) -> Dict[str, Any]:
        """验证测试数据的完整性
        
        检查：
        - 是否有重复的 ID
        - 是否所有必填字段都存在
        - 置信度是否在有效范围内
        
        Returns:
            验证结果字典，包含 valid 和 errors
        """
        errors = []
        
        # 检查重复 ID
        ids = [q.id for q in self._questions]
        duplicate_ids = [id for id in ids if ids.count(id) > 1]
        if duplicate_ids:
            errors.append(f"发现重复的问题 ID: {set(duplicate_ids)}")
        
        # 检查每个问题
        for q in self._questions:
            # 检查置信度范围
            if not (0.0 <= q.expected_confidence_min <= 1.0):
                errors.append(
                    f"问题 {q.id} 的置信度超出范围: {q.expected_confidence_min}"
                )
            
            # 检查必填字段
            if not q.question.strip():
                errors.append(f"问题 {q.id} 的问题文本为空")
            
            if not q.expected_intent:
                errors.append(f"问题 {q.id} 缺少 expected_intent")
        
        valid = len(errors) == 0
        
        if valid:
            logger.info("测试数据验证通过")
        else:
            logger.error(f"测试数据验证失败: {errors}")
        
        return {
            "valid": valid,
            "errors": errors,
            "total_questions": len(self._questions),
        }
