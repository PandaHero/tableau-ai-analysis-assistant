"""集成测试套件

完整的端到端集成测试，使用真实服务：
- DeepSeek LLM
- Zhipu Embedding
- Tableau Cloud

测试组织：
- base.py: 测试基类
- test_e2e_*.py: 端到端测试
- test_api_*.py: API 测试
- test_performance_*.py: 性能测试
- test_pbt_*.py: 属性测试
- test_cross_module_*.py: 跨模块测试
"""

from .base import BaseIntegrationTest

__all__ = ["BaseIntegrationTest"]
