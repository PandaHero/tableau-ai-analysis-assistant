"""
Pytest 配置文件

自动加载 .env 文件中的环境变量，确保测试可以访问 API keys 等配置。
"""
import os
from pathlib import Path


def pytest_configure(config):
    """
    Pytest 配置钩子
    
    在测试开始前加载 .env 文件中的环境变量。
    """
    # 查找项目根目录的 .env 文件
    root_dir = Path(__file__).parent
    env_file = root_dir / ".env"
    
    if env_file.exists():
        print(f"\n[conftest] 加载环境变量: {env_file}")
        load_dotenv(env_file)
    else:
        print(f"\n[conftest] 未找到 .env 文件: {env_file}")


def load_dotenv(env_file: Path):
    """
    简单的 .env 文件加载器
    
    解析 .env 文件并设置环境变量。
    支持：
    - KEY=value 格式
    - # 注释行
    - 空行
    - 带引号的值
    
    Args:
        env_file: .env 文件路径
    """
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue
            
            # 解析 KEY=value
            if '=' in line:
                key, _, value = line.partition('=')
                key = key.strip()
                value = value.strip()
                
                # 移除引号
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                
                # 只设置未定义的环境变量（不覆盖已有的）
                if key and key not in os.environ:
                    os.environ[key] = value
