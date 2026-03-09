#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tableau AI Assistant 启动脚本

功能:
1. 检查 Python 版本和虚拟环境
2. 安装依赖
3. 从 app.yaml 加载配置
4. 启动后端服务器 (FastAPI)
5. 启动前端服务器 (Vue/Vite) - 可选

使用方法:
  python start.py                  # 开发模式 (后端+前端)
  python start.py --backend-only   # 仅启动后端
  python start.py --prod           # 生产模式
"""

import os
import sys
import subprocess
import platform
import signal
import argparse
from pathlib import Path
from threading import Thread

# ============================================
# 命令行参数
# ============================================
parser = argparse.ArgumentParser(description='启动 Tableau Assistant')
parser.add_argument('--prod', action='store_true', help='生产模式')
parser.add_argument('--backend-only', action='store_true', help='仅启动后端')
parser.add_argument('--workers', type=int, default=4, help='生产模式的 worker 数量')
args, _ = parser.parse_known_args()

PRODUCTION_MODE = args.prod
BACKEND_ONLY = args.backend_only
WORKERS = args.workers

# ============================================
# 全局变量
# ============================================
backend_process = None
frontend_process = None

# ============================================
# 工具函数
# ============================================

def print_header(message):
    """打印标题"""
    print(f"\n{'='*60}")
    print(f"  {message}")
    print(f"{'='*60}\n")

def print_success(message):
    """打印成功消息"""
    print(f"[SUCCESS] {message}")

def print_error(message):
    """打印错误消息"""
    print(f"[ERROR] {message}")

def print_info(message):
    """打印信息"""
    print(f"[INFO] {message}")

# ============================================
# Python 和虚拟环境检查
# ============================================

def check_python_version():
    """检查 Python 版本 >= 3.12"""
    print_header("检查 Python 版本")
    
    version = sys.version_info
    current_version = f"{version.major}.{version.minor}.{version.micro}"
    
    print_info(f"当前 Python 版本: {current_version}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 12):
        print_error(f"需要 Python 3.12 或更高版本")
        print_error(f"当前版本: {current_version}")
        sys.exit(1)
    
    print_success(f"Python 版本 {current_version} 符合要求")
    return True

def get_venv_python():
    """获取虚拟环境中的 Python 路径"""
    system = platform.system()
    if system == "Windows":
        return Path("venv") / "Scripts" / "python.exe"
    else:
        return Path("venv") / "bin" / "python"

def get_venv_pip():
    """获取虚拟环境中的 pip 路径"""
    system = platform.system()
    if system == "Windows":
        return Path("venv") / "Scripts" / "pip.exe"
    else:
        return Path("venv") / "bin" / "pip"

def check_venv():
    """检查虚拟环境是否存在"""
    print_header("检查虚拟环境")
    
    venv_path = Path("venv")
    python_path = get_venv_python()
    
    if not venv_path.exists() or not python_path.exists():
        print_error("虚拟环境不存在")
        print_info("请先创建虚拟环境:")
        print_info("  python -m venv venv")
        print_info("然后安装依赖:")
        if platform.system() == "Windows":
            print_info("  venv\\Scripts\\pip install -r analytics_assistant\\requirements.txt")
        else:
            print_info("  venv/bin/pip install -r analytics_assistant/requirements.txt")
        sys.exit(1)
    
    print_success("虚拟环境已找到")
    return True

# ============================================
# 依赖检查和安装
# ============================================

def install_dependencies():
    """安装 Python 依赖"""
    print_header("检查依赖")
    
    pip_path = get_venv_pip()
    requirements_path = Path("requirements.txt")
    
    if not pip_path.exists():
        print_error(f"pip 未找到: {pip_path}")
        sys.exit(1)
    
    if not requirements_path.exists():
        print_error(f"requirements.txt 未找到: {requirements_path}")
        sys.exit(1)
    
    print_info("安装依赖...")
    
    try:
        subprocess.run(
            [str(pip_path), "install", "-q", "-r", str(requirements_path)],
            check=True
        )
        print_success("依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"依赖安装失败: {e}")
        print_info("请手动安装:")
        print_info(f"  {pip_path} install -r {requirements_path}")
        sys.exit(1)

# ============================================
# 配置加载和验证
# ============================================

def load_config():
    """从 app.yaml 加载配置"""
    import yaml
    
    print_header("加载配置")
    
    config_path = Path("analytics_assistant") / "config" / "app.yaml"
    
    if not config_path.exists():
        print_error(f"配置文件不存在: {config_path}")
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print_success("配置文件加载成功")
        return config
    except Exception as e:
        print_error(f"加载配置文件失败: {e}")
        sys.exit(1)

def validate_config(config):
    """验证配置"""
    print_header("验证配置")
    
    # 检查 Tableau 配置
    tableau = config.get('tableau', {})
    if not tableau.get('domain'):
        print_error("Tableau 域名未配置")
        print_info("请在 analytics_assistant/config/app.yaml 中配置 tableau.domain")
        sys.exit(1)
    
    # 检查认证配置
    jwt = tableau.get('jwt', {})
    pat = tableau.get('pat', {})
    
    has_jwt = all([jwt.get('client_id'), jwt.get('secret_id'), jwt.get('secret')])
    has_pat = all([pat.get('name'), pat.get('secret')])
    
    if not has_jwt and not has_pat:
        print_error("Tableau 认证未配置")
        print_info("请配置 JWT 或 PAT 认证")
        sys.exit(1)
    
    print_success("配置验证通过")
    print_info(f"Tableau 域名: {tableau.get('domain')}")
    print_info(f"Tableau 站点: {tableau.get('site', 'default')}")
    
    return True

# ============================================
# 后端服务器
# ============================================

def start_backend(config, host='127.0.0.1', port=5000):
    """启动后端服务器"""
    global backend_process
    
    print_header("启动后端服务器")
    
    python_path = get_venv_python()
    
    # 从配置读取证书路径（统一证书管理）
    ssl_config = config.get('ssl', {})
    active_cert = ssl_config.get('active_cert', 'localhost')
    certificates = ssl_config.get('certificates', {})
    
    if active_cert not in certificates:
        print_error(f"未找到证书配置: {active_cert}")
        sys.exit(1)
    
    cert_config = certificates[active_cert]
    cert_file = Path(cert_config.get('cert_file'))
    key_file = Path(cert_config.get('key_file'))
    
    # 从配置读取后端地址
    api_config = config.get('api', {})
    host = api_config.get('host', host)
    port = api_config.get('port', port)
    
    # 检查证书文件是否存在
    if not cert_file.exists() or not key_file.exists():
        print_error(f"HTTPS 证书文件不存在")
        print_info(f"证书文件: {cert_file}")
        print_info(f"密钥文件: {key_file}")
        sys.exit(1)
    
    # 构建命令
    cmd = [
        str(python_path),
        "-m", "uvicorn",
        "analytics_assistant.src.api.main:app",
        "--host", host,
        "--port", str(port),
        "--ssl-keyfile", str(key_file),
        "--ssl-certfile", str(cert_file),
    ]
    
    if PRODUCTION_MODE:
        cmd.extend(["--workers", str(WORKERS)])
        print_info(f"生产模式: {WORKERS} workers")
    else:
        cmd.append("--reload")
        print_info("开发模式: 自动重载已启用")
    
    print_info(f"后端地址: https://{host}:{port}")
    print_info(f"API 文档: https://{host}:{port}/docs")
    
    try:
        backend_process = subprocess.Popen(cmd)
        print_success("后端服务器已启动")
        return backend_process
    except Exception as e:
        print_error(f"启动后端失败: {e}")
        sys.exit(1)

# ============================================
# 前端服务器
# ============================================

def get_npm_command():
    """获取 npm 命令"""
    return "npm.cmd" if platform.system() == "Windows" else "npm"

def check_node():
    """检查 Node.js"""
    print_header("检查 Node.js")
    
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        print_success(f"Node.js {version} 已找到")
        return True
    except:
        print_error("Node.js 未安装")
        print_info("请从 https://nodejs.org/ 安装 Node.js")
        return False

def install_frontend_deps():
    """安装前端依赖"""
    print_header("安装前端依赖")
    
    frontend_path = Path("analytics_assistant") / "frontend"
    npm_cmd = get_npm_command()
    
    if not frontend_path.exists():
        print_error(f"前端目录不存在: {frontend_path}")
        return False
    
    node_modules = frontend_path / "node_modules"
    if node_modules.exists():
        print_success("前端依赖已安装")
        return True
    
    print_info("安装前端依赖...")
    
    try:
        subprocess.run(
            [npm_cmd, "install"],
            cwd=str(frontend_path),
            check=True,
            shell=True
        )
        print_success("前端依赖安装完成")
        return True
    except:
        print_error("前端依赖安装失败")
        return False

def build_frontend():
    """构建前端静态文件（供 FastAPI serve，不启动 dev server）"""
    global frontend_process
    
    print_header("构建前端")
    
    frontend_path = Path("analytics_assistant") / "frontend"
    npm_cmd = get_npm_command()
    
    if not frontend_path.exists():
        print_error(f"前端目录不存在: {frontend_path}")
        return False
    
    dist_path = frontend_path / "dist"
    
    # 生产模式下检查是否需要重新构建，开发模式下总是重新构建
    if PRODUCTION_MODE:
        # 检查 dist 是否已存在且新于源码（跳过重复构建）
        index_html = dist_path / "index.html"
        src_path = frontend_path / "src"
        if index_html.exists() and src_path.exists():
            dist_mtime = index_html.stat().st_mtime
            # 检查 src 目录下是否有比 dist 更新的文件
            need_rebuild = False
            for f in src_path.rglob("*"):
                if f.is_file() and f.stat().st_mtime > dist_mtime:
                    need_rebuild = True
                    break
            if not need_rebuild:
                print_success(f"前端已是最新构建，跳过重新构建")
                print_info(f"前端地址: https://localhost:{_get_api_port()}")
                return True
    else:
        print_info("开发模式: 强制重新构建前端")
    
    print_info("构建前端静态文件（这需要约 30-60 秒）...")
    
    try:
        result = subprocess.run(
            [npm_cmd, "run", "build"],
            cwd=str(frontend_path),
            check=True,
            shell=(platform.system() == "Windows")
        )
        print_success("前端构建完成")
        print_info(f"前端地址: https://localhost:{_get_api_port()}")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"前端构建失败: {e}")
        print_info("请手动执行: cd analytics_assistant/frontend && npm run build")
        return False


def _get_api_port():
    """获取后端端口（用于日志显示）"""
    try:
        import yaml
        config_path = Path("analytics_assistant") / "config" / "app.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config.get('api', {}).get('port', 5000)
    except Exception:
        return 5000

# ============================================
# 进程管理
# ============================================

def cleanup_processes():
    """清理所有进程"""
    global backend_process, frontend_process
    
    print_info("\n正在停止服务器...")
    
    if backend_process:
        backend_process.terminate()
        backend_process.wait()
        print_info("后端服务器已停止")
    
    if frontend_process:
        frontend_process.terminate()
        frontend_process.wait()
        print_info("前端服务器已停止")

def signal_handler(sig, frame):
    """处理 Ctrl+C 信号"""
    cleanup_processes()
    sys.exit(0)

# ============================================
# 主函数
# ============================================

def main():
    """主启动流程"""
    print("=" * 60)
    print("  Tableau AI Assistant - 启动")
    print("=" * 60)
    
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    
    # 1. 检查 Python 版本
    check_python_version()
    
    # 2. 检查虚拟环境
    check_venv()
    
    # 3. 安装依赖
    install_dependencies()
    
    # 4. 加载和验证配置
    config = load_config()
    validate_config(config)
    
    # 5. 先构建前端，再启动后端 serve 静态资源
    # FastAPI 只会在启动时检查一次 dist 目录，必须保证后端启动前 dist 已可用。
    if not BACKEND_ONLY:
        if not check_node():
            sys.exit(1)
        if not install_frontend_deps():
            sys.exit(1)
        if not build_frontend():
            sys.exit(1)

    # 6. 启动后端
    start_backend(config)
    
    # 7. 等待进程
    print_info("\n服务器正在运行...")
    print_info("按 Ctrl+C 停止")
    
    try:
        if backend_process:
            backend_process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_processes()

if __name__ == "__main__":
    main()
