# -*- coding: utf-8 -*-
"""
运行 RAG 模块测试的辅助脚本
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    import pytest
    
    # 运行所有 RAG 测试
    test_dir = Path(__file__).parent
    exit_code = pytest.main([
        str(test_dir),
        "-v",
        "--tb=short",
        "-x",  # 遇到第一个失败就停止
    ])
    
    sys.exit(exit_code)
