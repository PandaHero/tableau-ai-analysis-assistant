#!/usr/bin/env python3
"""
LLM 切换工具

快速切换 DeepSeek 和 Qwen3 大模型配置

使用方法:
    python switch_llm.py deepseek    # 切换到 DeepSeek
    python switch_llm.py qwen3       # 切换到 Qwen3
    python switch_llm.py status      # 查看当前配置
"""
import sys
import re
from pathlib import Path


# LLM 配置映射
LLM_CONFIGS = {
    "deepseek": {
        "LLM_API_BASE": "https://api.deepseek.com",
        "LLM_MODEL_PROVIDER": "openai",
        "TOOLING_LLM_MODEL": "deepseek-chat",
        "LLM_API_KEY": "sk-f02e477c366f44f692b11450abb514f6",
    },
    "qwen3": {
        "LLM_API_BASE": "http://36.212.5.18:9997/v1",
        "LLM_MODEL_PROVIDER": "local",
        "TOOLING_LLM_MODEL": "qwen3",
        "LLM_API_KEY": "dummy-key",
    }
}


def read_env_file(env_path: Path) -> str:
    """读取 .env 文件内容"""
    if not env_path.exists():
        print(f"❌ 错误: .env 文件不存在于 {env_path}")
        sys.exit(1)
    
    return env_path.read_text(encoding='utf-8')


def write_env_file(env_path: Path, content: str):
    """写入 .env 文件"""
    env_path.write_text(content, encoding='utf-8')


def get_current_llm(content: str) -> str:
    """获取当前激活的 LLM"""
    match = re.search(r'^ACTIVE_LLM=(\w+)', content, re.MULTILINE)
    if match:
        return match.group(1)
    return "unknown"


def update_active_llm(content: str, target_llm: str) -> str:
    """更新 ACTIVE_LLM 配置"""
    # 更新 ACTIVE_LLM
    content = re.sub(
        r'^ACTIVE_LLM=\w+',
        f'ACTIVE_LLM={target_llm}',
        content,
        flags=re.MULTILINE
    )
    
    # 获取目标配置
    config = LLM_CONFIGS[target_llm]
    
    # 更新实际使用的配置
    for key, value in config.items():
        pattern = f'^{key}=.*$'
        replacement = f'{key}={value}'
        
        # 查找并替换最后一次出现的配置（实际使用的配置在文件末尾）
        lines = content.split('\n')
        last_index = -1
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith(f'{key}='):
                last_index = i
                break
        
        if last_index != -1:
            lines[last_index] = replacement
            content = '\n'.join(lines)
    
    return content


def show_status(content: str):
    """显示当前 LLM 配置状态"""
    current_llm = get_current_llm(content)
    
    print("\n" + "="*60)
    print("📊 当前 LLM 配置状态")
    print("="*60)
    
    # 提取当前配置
    api_base = re.search(r'^LLM_API_BASE=(.+)$', content, re.MULTILINE)
    provider = re.search(r'^LLM_MODEL_PROVIDER=(.+)$', content, re.MULTILINE)
    model = re.search(r'^TOOLING_LLM_MODEL=(.+)$', content, re.MULTILINE)
    
    print(f"\n🎯 激活的 LLM: {current_llm.upper()}")
    print(f"\n当前配置:")
    print(f"  - API Base: {api_base.group(1) if api_base else 'N/A'}")
    print(f"  - Provider: {provider.group(1) if provider else 'N/A'}")
    print(f"  - Model: {model.group(1) if model else 'N/A'}")
    
    print(f"\n可用的 LLM:")
    for llm_name in LLM_CONFIGS.keys():
        status = "✅ (当前)" if llm_name == current_llm else "⚪"
        print(f"  {status} {llm_name}")
    
    print("\n" + "="*60 + "\n")


def switch_llm(target_llm: str):
    """切换到指定的 LLM"""
    if target_llm not in LLM_CONFIGS:
        print(f"❌ 错误: 不支持的 LLM '{target_llm}'")
        print(f"   支持的选项: {', '.join(LLM_CONFIGS.keys())}")
        sys.exit(1)
    
    # 读取 .env 文件
    env_path = Path(__file__).parent / ".env"
    content = read_env_file(env_path)
    
    # 检查当前 LLM
    current_llm = get_current_llm(content)
    if current_llm == target_llm:
        print(f"ℹ️  当前已经是 {target_llm.upper()}，无需切换")
        show_status(content)
        return
    
    # 更新配置
    print(f"\n🔄 正在切换 LLM: {current_llm.upper()} → {target_llm.upper()}")
    new_content = update_active_llm(content, target_llm)
    
    # 写入文件
    write_env_file(env_path, new_content)
    
    print(f"✅ 成功切换到 {target_llm.upper()}")
    
    # 显示新配置
    show_status(new_content)
    
    print("💡 提示: 请重启应用以使配置生效")


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python switch_llm.py deepseek    # 切换到 DeepSeek")
        print("  python switch_llm.py qwen3       # 切换到 Qwen3")
        print("  python switch_llm.py status      # 查看当前配置")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "status":
        env_path = Path(__file__).parent / ".env"
        content = read_env_file(env_path)
        show_status(content)
    else:
        switch_llm(command)


if __name__ == "__main__":
    main()
