"""测试配置文件路径"""
from pathlib import Path

# 当前文件路径
current_file = Path(__file__).resolve()
print(f"当前文件: {current_file}")

# analytics-assistant 根目录
analytics_root = current_file.parent.parent.parent
print(f"analytics-assistant 根目录: {analytics_root}")

# 配置文件路径
config_path = analytics_root / "config" / "models.yaml"
print(f"配置文件路径: {config_path}")
print(f"配置文件存在: {config_path.exists()}")

if config_path.exists():
    print("\n配置文件内容（前20行）:")
    with open(config_path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if i > 20:
                break
            print(f"{i:2d}: {line}", end='')
