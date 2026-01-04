#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
One-click startup script for Tableau Assistant (Backend + Frontend).

This script automates the setup and launch process:
1. Checks Python version (>= 3.12)
2. Creates virtual environment if needed
3. Installs Python dependencies
4. Validates environment configuration
5. Checks Node.js and npm
6. Installs frontend dependencies
7. Starts FastAPI server (production: serves static files, dev: starts Vue dev server)

Usage:
  python start.py                     # Development mode (hot reload, single worker)
  python start.py --prod              # Production mode (multi-worker, auto-build frontend if needed)
  python start.py --prod --rebuild    # Production mode + force rebuild frontend
  python start.py --install-service   # Install systemd service (Linux only)
  python start.py --uninstall-service # Uninstall systemd service (Linux only)
"""

import os
import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # Set console to UTF-8 mode
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except:
        pass
import subprocess
import platform
import time
import signal
import argparse
import getpass
from pathlib import Path
from threading import Thread

# Parse command line arguments
parser = argparse.ArgumentParser(description='Start Tableau Assistant')
parser.add_argument('--prod', action='store_true', help='Production mode (multi-worker, no hot reload)')
parser.add_argument('--rebuild', action='store_true', help='Force rebuild frontend (use with --prod)')
parser.add_argument('--backend-only', action='store_true', help='Start backend only (no frontend)')
parser.add_argument('--install-service', action='store_true', help='Install systemd service (Linux only)')
parser.add_argument('--uninstall-service', action='store_true', help='Uninstall systemd service (Linux only)')
parser.add_argument('--workers', type=int, default=4, help='Number of uvicorn workers in prod mode (default: 4)')
args, _ = parser.parse_known_args()

PRODUCTION_MODE = args.prod
REBUILD_FRONTEND = args.rebuild
BACKEND_ONLY = args.backend_only
INSTALL_SERVICE = args.install_service
UNINSTALL_SERVICE = args.uninstall_service
WORKERS = args.workers


def print_header(message):
    """Print a formatted header message."""
    print(f"\n{'='*60}")
    print(f"  {message}")
    print(f"{'='*60}\n")


def print_success(message):
    """Print a success message."""
    print(f"✓ {message}")


def print_error(message):
    """Print an error message."""
    print(f"✗ {message}")


def print_info(message):
    """Print an info message."""
    print(f"ℹ {message}")


def check_python_version():
    """Check if Python version is >= 3.12."""
    print_header("Checking Python Version")
    
    version = sys.version_info
    current_version = f"{version.major}.{version.minor}.{version.micro}"
    
    print_info(f"Current Python version: {current_version}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 12):
        print_error(f"Python 3.12 or higher is required")
        print_error(f"Current version: {current_version}")
        print_info("Please upgrade Python and try again")
        sys.exit(1)
    
    print_success(f"Python version {current_version} is compatible")
    return True


def check_venv():
    """Check if virtual environment exists."""
    print_header("Checking Virtual Environment")
    
    venv_path = Path("venv")
    
    if venv_path.exists():
        print_success("Virtual environment found")
        return True
    else:
        print_info("Virtual environment not found")
        return False


def create_venv():
    """Create a virtual environment."""
    print_header("Creating Virtual Environment")
    
    try:
        print_info("Creating virtual environment...")
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print_success("Virtual environment created successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create virtual environment: {e}")
        print_info("Please create it manually: python -m venv venv")
        sys.exit(1)


def get_venv_python():
    """Get the path to the Python executable in the virtual environment."""
    system = platform.system()
    
    if system == "Windows":
        return Path("venv") / "Scripts" / "python.exe"
    else:
        return Path("venv") / "bin" / "python"


def get_venv_pip():
    """Get the path to the pip executable in the virtual environment."""
    system = platform.system()
    
    if system == "Windows":
        return Path("venv") / "Scripts" / "pip.exe"
    else:
        return Path("venv") / "bin" / "pip"


def get_installed_packages():
    """Get dict of installed packages and their versions."""
    pip_path = get_venv_pip()
    
    try:
        result = subprocess.run(
            [str(pip_path), "list", "--format=freeze"],
            capture_output=True,
            text=True,
            check=True
        )
        installed = {}
        for line in result.stdout.strip().split('\n'):
            if '==' in line:
                name, version = line.split('==', 1)
                installed[name.lower().replace('-', '_')] = version
        return installed
    except:
        return {}


def parse_requirements(requirements_path):
    """Parse requirements.txt and return list of package names."""
    packages = []
    try:
        with open(requirements_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Extract package name (remove version specifiers)
                for sep in ['>=', '<=', '==', '!=', '~=', '>', '<', '[']:
                    if sep in line:
                        line = line.split(sep)[0]
                        break
                packages.append(line.lower().replace('-', '_'))
    except:
        pass
    return packages


def install_dependencies():
    """Install dependencies from requirements.txt (only missing ones)."""
    print_header("Checking Dependencies")
    
    pip_path = get_venv_pip()
    requirements_path = Path("tableau_assistant") / "requirements.txt"
    
    if not pip_path.exists():
        print_error(f"Pip not found at {pip_path}")
        sys.exit(1)
    
    if not requirements_path.exists():
        print_error(f"Requirements file not found at {requirements_path}")
        sys.exit(1)
    
    # Get installed packages and required packages
    installed = get_installed_packages()
    required = parse_requirements(requirements_path)
    
    # Find missing packages
    missing = [pkg for pkg in required if pkg not in installed]
    
    if not missing:
        print_success(f"All {len(required)} dependencies already installed")
        return True
    
    print_info(f"Found {len(missing)} missing packages: {', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}")
    print_info("Installing missing dependencies...")
    
    try:
        # Use pip install -r to install only missing (pip handles this efficiently)
        result = subprocess.run(
            [str(pip_path), "install", "-r", str(requirements_path)],
            check=True,
            capture_output=True,
            text=True
        )
        
        print_success("Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install dependencies")
        print_error(f"Exit code: {e.returncode}")
        if e.stdout:
            print_info(f"Output: {e.stdout[:500]}")
        if e.stderr:
            print_error(f"Error: {e.stderr[:500]}")
        print_info("\nPlease try manually:")
        print_info(f"  {pip_path} install -r {requirements_path}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)


def check_env_file():
    """Check if .env file exists."""
    print_header("Checking Environment Configuration")
    
    env_path = Path(".env")
    
    if not env_path.exists():
        print_error(".env file not found in project root")
        print_info("Please create a .env file in the project root directory")
        print_info("You can copy from .env.example if available")
        sys.exit(1)
    
    print_success(".env file found")
    return True


def load_env_vars():
    """Load environment variables from .env file."""
    env_path = Path(".env")
    env_vars = {}
    
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip().strip("'\"")
    except Exception as e:
        print_error(f"Failed to read .env file: {e}")
        sys.exit(1)
    
    return env_vars


def validate_env_vars():
    """Validate critical environment variables."""
    print_header("Validating Environment Variables")
    
    # Load .env file
    env_vars = load_env_vars()
    
    # Check for Tableau config
    has_tableau = env_vars.get('TABLEAU_DOMAIN', '')
    
    # Tableau environment must be configured
    if not has_tableau:
        print_error("No Tableau environment configured!")
        print_info("Please configure TABLEAU_DOMAIN and authentication variables")
        sys.exit(1)
    
    # Validate authentication
    auth_jwt = all([
        env_vars.get("TABLEAU_JWT_CLIENT_ID"),
        env_vars.get("TABLEAU_JWT_SECRET_ID"),
        env_vars.get("TABLEAU_JWT_SECRET"),
    ])
    auth_pat = all([
        env_vars.get("TABLEAU_PAT_NAME"),
        env_vars.get("TABLEAU_PAT_SECRET"),
    ])
    if not auth_jwt and not auth_pat:
        print_error("Tableau: Missing authentication (need JWT or PAT)")
        sys.exit(1)
    
    # Check LLM config
    if not env_vars.get('LLM_API_BASE'):
        print_error("Missing LLM_API_BASE")
        sys.exit(1)
    
    print_success("All critical environment variables are set")
    
    # Display configuration summary
    print_info("\nConfiguration Summary:")
    print(f"  Backend Host: {env_vars.get('HOST', '127.0.0.1')}")
    print(f"  Backend Port: {env_vars.get('PORT', '8000')}")
    print(f"  Frontend Host: {env_vars.get('VITE_APP_HOST', '127.0.0.1')}")
    print(f"  Frontend Port: {env_vars.get('VITE_APP_PORT', '5173')}")
    
    # Show Tableau environment
    print_info("\nTableau Environment:")
    print(f"  Domain: {env_vars.get('TABLEAU_DOMAIN')}")
    
    print(f"\n  LLM API Base: {env_vars.get('LLM_API_BASE', 'Not set')}")
    
    return True


def verify_env_config():
    """Verify environment configuration using certificate manager."""
    print_header("Verifying SSL Certificates")
    
    root_env = Path(".env")
    
    if not root_env.exists():
        print_error("Root .env file not found!")
        return False
    
    print_success("Root .env file found")
    
    # 使用证书管理器初始化证书
    try:
        # 添加项目路径到 sys.path
        import sys
        project_root = Path(__file__).parent
        if str(project_root) not in sys.path:
            sys.path.insert(0, str(project_root))
        
        from tableau_assistant.src.infra.certs import get_certificate_manager
        
        print_info("初始化证书管理器...")
        manager = get_certificate_manager()
        
        if not manager.initialize():
            print_error("❌ 证书初始化失败!")
            return False
        
        # 获取 SSL 配置
        ssl_config = manager.get_app_ssl_config()
        ssl_cert = ssl_config.get("ssl_certfile", "")
        ssl_key = ssl_config.get("ssl_keyfile", "")
        
        # 获取证书状态
        status = manager.get_status()
        source = status.get("source", "unknown")
        
        print_success(f"✓ 证书来源: {source}")
        print_success(f"✓ 证书文件: {ssl_cert}")
        print_success(f"✓ 私钥文件: {ssl_key}")
        
        # 显示过期信息
        app_status = status.get("application", {})
        if app_status:
            days_left = app_status.get("days_until_expiry", 0)
            expires = app_status.get("expires", "")
            if app_status.get("warning"):
                print_error(f"⚠️ 证书即将过期! 剩余 {days_left} 天")
            else:
                print_info(f"证书有效期: 剩余 {days_left} 天")
        
        # 导出环境变量供后续使用
        env_exports = manager.export_to_env()
        for key, value in env_exports.items():
            os.environ[key] = value
        
        # 显示 HTTPS 配置
        env_vars = load_env_vars()
        host = env_vars.get('HOST', '127.0.0.1')
        port = env_vars.get('PORT', '8000')
        api_base_url = f"https://{host}:{port}"
        print_info(f"API URL: {api_base_url}")
        print_success("🔒 HTTPS 已启用")
        
        return True
        
    except ImportError as e:
        print_error(f"❌ 无法导入证书管理器: {e}")
        print_info("请确保已安装所有依赖: pip install -r tableau_assistant/requirements.txt")
        return False
    except Exception as e:
        print_error(f"❌ 证书验证失败: {e}")
        return False


# ============================================
# Systemd Service Management
# ============================================

SERVICE_NAME = "tableau-assistant"
SERVICE_FILE = f"/etc/systemd/system/{SERVICE_NAME}.service"


def generate_service_file():
    """Generate systemd service file content."""
    project_dir = Path.cwd().resolve()
    env_vars = load_env_vars()
    
    host = env_vars.get('HOST', '0.0.0.0')
    port = env_vars.get('PORT', '8000')
    ssl_cert = env_vars.get('SSL_CERT_FILE', '')
    ssl_key = env_vars.get('SSL_KEY_FILE', '')
    
    # Resolve SSL paths
    if ssl_cert and not Path(ssl_cert).is_absolute():
        ssl_cert = str((project_dir / ssl_cert).resolve())
    if ssl_key and not Path(ssl_key).is_absolute():
        ssl_key = str((project_dir / ssl_key).resolve())
    
    # Get current user
    current_user = getpass.getuser()
    
    # Build ExecStart command
    exec_start = f"{project_dir}/venv/bin/uvicorn tableau_assistant.src.main:app --host {host} --port {port} --workers {WORKERS}"
    
    if ssl_cert and ssl_key:
        exec_start += f" --ssl-certfile {ssl_cert} --ssl-keyfile {ssl_key}"
    
    service_content = f"""[Unit]
Description=Tableau AI Analysis Assistant
After=network.target

[Service]
Type=simple
User={current_user}
Group={current_user}
WorkingDirectory={project_dir}
Environment="PATH={project_dir}/venv/bin"
EnvironmentFile={project_dir}/.env
ExecStart={exec_start}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    return service_content


def install_systemd_service():
    """Install systemd service."""
    print_header("Installing Systemd Service")
    
    # Check if running on Linux
    if platform.system() != "Linux":
        print_error("Systemd service installation is only supported on Linux")
        print_info("On Windows, use Task Scheduler or run as a Windows Service")
        return False
    
    # Check if running as root or with sudo
    if os.geteuid() != 0:
        print_error("Root privileges required to install systemd service")
        print_info("Please run with sudo: sudo python start.py --install-service")
        return False
    
    # Verify environment first
    if not check_env_file():
        return False
    
    # Generate service file
    service_content = generate_service_file()
    
    print_info(f"Service file content:\n{'-'*40}")
    print(service_content)
    print('-'*40)
    
    # Write service file
    try:
        with open(SERVICE_FILE, 'w') as f:
            f.write(service_content)
        print_success(f"Service file created: {SERVICE_FILE}")
    except Exception as e:
        print_error(f"Failed to create service file: {e}")
        return False
    
    # Reload systemd
    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        print_success("Systemd daemon reloaded")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to reload systemd: {e}")
        return False
    
    # Enable service
    try:
        subprocess.run(["systemctl", "enable", SERVICE_NAME], check=True)
        print_success(f"Service enabled: {SERVICE_NAME}")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to enable service: {e}")
        return False
    
    print_success("Systemd service installed successfully!")
    print_info("\nUseful commands:")
    print(f"  Start:   sudo systemctl start {SERVICE_NAME}")
    print(f"  Stop:    sudo systemctl stop {SERVICE_NAME}")
    print(f"  Restart: sudo systemctl restart {SERVICE_NAME}")
    print(f"  Status:  sudo systemctl status {SERVICE_NAME}")
    print(f"  Logs:    sudo journalctl -u {SERVICE_NAME} -f")
    
    # Ask if user wants to start the service now
    response = input("\nStart the service now? (y/n): ")
    if response.lower() == 'y':
        try:
            subprocess.run(["systemctl", "start", SERVICE_NAME], check=True)
            print_success(f"Service started: {SERVICE_NAME}")
            subprocess.run(["systemctl", "status", SERVICE_NAME])
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to start service: {e}")
            print_info(f"Check logs: sudo journalctl -u {SERVICE_NAME} -n 50")
    
    return True


def uninstall_systemd_service():
    """Uninstall systemd service."""
    print_header("Uninstalling Systemd Service")
    
    # Check if running on Linux
    if platform.system() != "Linux":
        print_error("Systemd service uninstallation is only supported on Linux")
        return False
    
    # Check if running as root or with sudo
    if os.geteuid() != 0:
        print_error("Root privileges required to uninstall systemd service")
        print_info("Please run with sudo: sudo python start.py --uninstall-service")
        return False
    
    # Stop service if running
    try:
        subprocess.run(["systemctl", "stop", SERVICE_NAME], check=False)
        print_success(f"Service stopped: {SERVICE_NAME}")
    except:
        pass
    
    # Disable service
    try:
        subprocess.run(["systemctl", "disable", SERVICE_NAME], check=False)
        print_success(f"Service disabled: {SERVICE_NAME}")
    except:
        pass
    
    # Remove service file
    if Path(SERVICE_FILE).exists():
        try:
            os.remove(SERVICE_FILE)
            print_success(f"Service file removed: {SERVICE_FILE}")
        except Exception as e:
            print_error(f"Failed to remove service file: {e}")
            return False
    else:
        print_info("Service file not found (already removed)")
    
    # Reload systemd
    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        print_success("Systemd daemon reloaded")
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to reload systemd: {e}")
    
    print_success("Systemd service uninstalled successfully!")
    return True


def check_node():
    """Check if Node.js is installed."""
    print_header("Checking Node.js")
    
    try:
        result = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        version = result.stdout.strip()
        print_success(f"Node.js {version} found")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("Node.js not found")
        print_info("Please install Node.js from https://nodejs.org/")
        return False


def get_npm_command():
    """Get the correct npm command for the platform."""
    system = platform.system()
    if system == "Windows":
        return "npm.cmd"
    else:
        return "npm"


def check_npm():
    """Check if npm is installed."""
    print_header("Checking npm")
    
    npm_cmd = get_npm_command()
    
    try:
        result = subprocess.run(
            [npm_cmd, "--version"],
            capture_output=True,
            text=True,
            check=True,
            shell=True,  # Use shell on Windows
            encoding='utf-8',
            errors='replace'
        )
        version = result.stdout.strip()
        print_success(f"npm {version} found")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print_error("npm not found")
        print_info("npm should be installed with Node.js")
        return False


def check_frontend_deps():
    """Check if frontend dependencies are installed."""
    print_header("Checking Frontend Dependencies")
    
    node_modules = Path("tableau_assistant") / "frontend" / "node_modules"
    
    if node_modules.exists():
        print_success("Frontend dependencies found")
        return True
    else:
        print_info("Frontend dependencies not found")
        return False


def install_frontend_deps():
    """Install frontend dependencies."""
    print_header("Installing Frontend Dependencies")
    
    frontend_path = Path("tableau_assistant") / "frontend"
    npm_cmd = get_npm_command()
    
    if not frontend_path.exists():
        print_error(f"Frontend directory not found at {frontend_path}")
        return False
    
    try:
        print_info("Installing frontend dependencies...")
        print_info("This may take a few minutes...")
        
        result = subprocess.run(
            [npm_cmd, "install"],
            cwd=str(frontend_path),
            check=True,
            capture_output=True,
            text=True,
            shell=True,  # Use shell on Windows
            encoding='utf-8',
            errors='replace'
        )
        
        print_success("Frontend dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install frontend dependencies")
        print_error(f"Exit code: {e.returncode}")
        if e.stderr:
            print_error(f"Error: {e.stderr[:500]}")
        print_info("\nPlease try manually:")
        print_info(f"  cd tableau_assistant/frontend")
        print_info(f"  npm install")
        return False


def build_frontend():
    """Build frontend for production."""
    print_header("Building Frontend for Production")
    
    frontend_path = Path("tableau_assistant") / "frontend"
    npm_cmd = get_npm_command()
    
    if not frontend_path.exists():
        print_error(f"Frontend directory not found at {frontend_path}")
        return False
    
    try:
        print_info("Building frontend...")
        print_info("This may take a minute...")
        
        result = subprocess.run(
            [npm_cmd, "run", "build"],
            cwd=str(frontend_path),
            check=True,
            capture_output=True,
            text=True,
            shell=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # Check if dist folder exists
        dist_path = frontend_path / "dist"
        if dist_path.exists():
            print_success("Frontend built successfully")
            print_info(f"Build output: {dist_path}")
            return True
        else:
            print_error("Build completed but dist folder not found")
            return False
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to build frontend")
        print_error(f"Exit code: {e.returncode}")
        if e.stderr:
            print_error(f"Error: {e.stderr[:1000]}")
        if e.stdout:
            print_info(f"Output: {e.stdout[:1000]}")
        return False


def check_frontend_build():
    """Check if frontend is already built."""
    dist_path = Path("tableau_assistant") / "frontend" / "dist" / "index.html"
    return dist_path.exists()


# Global process references
backend_process = None
frontend_process = None


def start_backend():
    """Start the FastAPI server in a subprocess."""
    global backend_process
    
    print_header("Starting Backend Server")
    
    python_path = get_venv_python()
    
    if not python_path.exists():
        print_error(f"Python not found at {python_path}")
        return None
    
    # Load environment variables from root .env
    env_vars = load_env_vars()
    
    host = env_vars.get('HOST', '127.0.0.1')
    port = env_vars.get('PORT', '8000')
    
    # 从环境变量获取 SSL 配置（由证书管理器设置）
    ssl_cert = os.environ.get('SSL_CERT_FILE', '')
    ssl_key = os.environ.get('SSL_KEY_FILE', '')
    
    # Resolve relative paths from project root
    if ssl_cert and not Path(ssl_cert).is_absolute():
        ssl_cert = str(Path(ssl_cert).resolve())
    if ssl_key and not Path(ssl_key).is_absolute():
        ssl_key = str(Path(ssl_key).resolve())
    
    # Determine protocol
    protocol = "https" if (ssl_cert and ssl_key and Path(ssl_cert).exists() and Path(ssl_key).exists()) else "http"
    
    print_info(f"Starting backend on {host}:{port}")
    if protocol == "https":
        print_success("🔒 HTTPS enabled")
    else:
        print_info("Using HTTP mode")
    
    # Display access URLs
    print_success("Backend starting...")
    print(f"  API:      {protocol}://{host}:{port}")
    print(f"  Docs:     {protocol}://{host}:{port}/docs")
    print(f"  Health:   {protocol}://{host}:{port}/health")
    
    # Get uvicorn path
    system = platform.system()
    if system == "Windows":
        uvicorn_path = Path("venv") / "Scripts" / "uvicorn.exe"
    else:
        uvicorn_path = Path("venv") / "bin" / "uvicorn"
    
    if not uvicorn_path.exists():
        print_error(f"Uvicorn not found at {uvicorn_path}")
        print_info("Trying to use python -m uvicorn instead...")
        uvicorn_cmd = [str(python_path), "-m", "uvicorn"]
    else:
        uvicorn_cmd = [str(uvicorn_path)]
    
    # Build uvicorn command
    cmd = uvicorn_cmd + [
        "tableau_assistant.src.main:app",
        "--host", host,
        "--port", port,
    ]
    
    # Production mode: use workers, no reload
    # Development mode: use reload, single worker
    if PRODUCTION_MODE:
        cmd.extend(["--workers", str(WORKERS)])
        print_info(f"Workers: {WORKERS}")
    else:
        cmd.append("--reload")
        print_info("Hot reload enabled")
    
    # Add SSL if configured
    if protocol == "https":
        cmd.extend(["--ssl-certfile", ssl_cert, "--ssl-keyfile", ssl_key])
    
    try:
        # Start backend process
        backend_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stderr with stdout
            text=True,
            bufsize=1,  # Line buffered
            encoding='utf-8',  # Fix Windows GBK encoding issue
            errors='replace'  # Replace invalid characters
        )
        
        print_success("✓ Backend server started")
        return backend_process
    except Exception as e:
        print_error(f"Failed to start backend: {e}")
        return None


def start_frontend():
    """Start the Vue dev server in a subprocess."""
    global frontend_process
    
    print_header("Starting Frontend Server")
    
    frontend_path = Path("tableau_assistant") / "frontend"
    npm_cmd = get_npm_command()
    
    if not frontend_path.exists():
        print_error(f"Frontend directory not found at {frontend_path}")
        return None
    
    print_info("Starting frontend dev server...")
    
    try:
        # Start frontend process
        frontend_process = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=str(frontend_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,  # Use shell on Windows
            encoding='utf-8',  # Fix Windows GBK encoding issue
            errors='replace'  # Replace invalid characters
        )
        
        # Determine frontend protocol based on SSL configuration
        env_vars = load_env_vars()
        # 前端使用与后端相同的证书（从环境变量或 .env 获取）
        frontend_ssl_cert = os.environ.get('SSL_CERT_FILE', '') or env_vars.get('SSL_CERT_FILE', '')
        frontend_ssl_key = os.environ.get('SSL_KEY_FILE', '') or env_vars.get('SSL_KEY_FILE', '')
        frontend_host = env_vars.get('VITE_APP_HOST', '127.0.0.1')
        frontend_port = env_vars.get('VITE_APP_PORT', '5173')
        
        # Check if frontend SSL is configured (Vite requires HTTPS)
        if frontend_ssl_cert and frontend_ssl_key:
            frontend_protocol = "https"
            print_success("✓ Frontend server started (HTTPS enabled)")
        else:
            frontend_protocol = "https"  # Vite 配置要求 HTTPS
            print_success("✓ Frontend server started")
        
        print(f"  Local:    {frontend_protocol}://{frontend_host}:{frontend_port}")
        print(f"  Demo:     {frontend_protocol}://{frontend_host}:{frontend_port}/streaming-demo")
        
        return frontend_process
    except Exception as e:
        print_error(f"Failed to start frontend: {e}")
        return None


def cleanup_processes():
    """Clean up all running processes."""
    global backend_process, frontend_process
    
    print_info("\nStopping servers...")
    
    if backend_process:
        try:
            backend_process.terminate()
            backend_process.wait(timeout=5)
            print_success("✓ Backend stopped")
        except Exception as e:
            print_error(f"Error stopping backend: {e}")
            try:
                backend_process.kill()
            except:
                pass
    
    if frontend_process:
        try:
            frontend_process.terminate()
            frontend_process.wait(timeout=5)
            print_success("✓ Frontend stopped")
        except Exception as e:
            print_error(f"Error stopping frontend: {e}")
            try:
                frontend_process.kill()
            except:
                pass


def print_process_output(process, name):
    """Print process output in real-time."""
    if process and process.stdout:
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f"[{name}] {line.rstrip()}")
                if process.poll() is not None:
                    break
        except:
            pass


def monitor_processes():
    """Monitor both processes and restart if needed."""
    global backend_process, frontend_process
    
    # Determine protocols
    env_vars = load_env_vars()
    
    # Backend protocol - 从 os.environ 获取（证书管理器设置的）
    ssl_cert = os.environ.get('SSL_CERT_FILE', '') or env_vars.get('SSL_CERT_FILE', '')
    ssl_key = os.environ.get('SSL_KEY_FILE', '') or env_vars.get('SSL_KEY_FILE', '')
    backend_protocol = "https" if (ssl_cert and ssl_key and Path(ssl_cert).exists() and Path(ssl_key).exists()) else "http"
    
    # Get host and port from env
    backend_host = env_vars.get('HOST', '127.0.0.1')
    backend_port = env_vars.get('PORT', '8000')
    
    print_header("Server Running")
    
    if PRODUCTION_MODE or BACKEND_ONLY:
        # Production mode - backend serves everything
        print_success("Backend server is running!")
        print_info("\nAccess URLs:")
        print(f"  Application: {backend_protocol}://{backend_host}:{backend_port}")
        print(f"  API Docs:    {backend_protocol}://{backend_host}:{backend_port}/docs")
        print(f"  Health:      {backend_protocol}://{backend_host}:{backend_port}/api/health")
        if PRODUCTION_MODE:
            print_info("\n📦 Production mode: Frontend served from backend")
    else:
        # Development mode - separate frontend server
        # 前端使用与后端相同的证书（Vite 配置要求 HTTPS）
        frontend_protocol = "https"
        frontend_host = env_vars.get('VITE_APP_HOST', '127.0.0.1')
        frontend_port = env_vars.get('VITE_APP_PORT', '5173')
        
        print_success("Both servers are running!")
        print_info("\nAccess URLs:")
        print(f"  Frontend:  {frontend_protocol}://{frontend_host}:{frontend_port}")
        print(f"  Backend:   {backend_protocol}://{backend_host}:{backend_port}")
        print(f"  API Docs:  {backend_protocol}://{backend_host}:{backend_port}/docs")
        print_info("\n🔧 Development mode: Hot reload enabled")
    
    print_info("\nPress Ctrl+C to stop")
    print_info("Server logs will appear below:\n")
    print("=" * 60)
    
    # Start threads to print output
    if backend_process:
        backend_thread = Thread(target=print_process_output, args=(backend_process, "Backend"), daemon=True)
        backend_thread.start()
    
    if frontend_process:
        frontend_thread = Thread(target=print_process_output, args=(frontend_process, "Frontend"), daemon=True)
        frontend_thread.start()
    
    try:
        while True:
            time.sleep(1)
            
            # Check if processes are still running
            if backend_process and backend_process.poll() is not None:
                print("\n" + "=" * 60)
                print_error("Backend process stopped unexpectedly")
                print_error(f"Exit code: {backend_process.returncode}")
                break
            
            if frontend_process and frontend_process.poll() is not None:
                print("\n" + "=" * 60)
                print_error("Frontend process stopped unexpectedly")
                print_error(f"Exit code: {frontend_process.returncode}")
                break
    
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print_info("Shutdown signal received")
    finally:
        cleanup_processes()


def main():
    """Main startup sequence."""
    
    global BACKEND_ONLY  # Allow modification in this function
    
    # Handle systemd service installation/uninstallation
    if INSTALL_SERVICE:
        install_systemd_service()
        return
    
    if UNINSTALL_SERVICE:
        uninstall_systemd_service()
        return
    
    mode_str = "Production" if PRODUCTION_MODE else "Development"
    print_header(f"Tableau Assistant - One-Click Startup ({mode_str} Mode)")
    
    if PRODUCTION_MODE:
        print_info("Running in PRODUCTION mode - backend serves static files\n")
    else:
        print_info("Running in DEVELOPMENT mode - backend + frontend dev server\n")
    
    # ========== Backend Setup ==========
    # Step 1: Check Python version
    check_python_version()
    
    # Step 2: Check/create virtual environment
    if not check_venv():
        create_venv()
    
    # Step 3: Install Python dependencies
    install_dependencies()
    
    # Step 4: Check .env file
    check_env_file()
    
    # Step 5: Validate environment variables
    validate_env_vars()
    
    # Step 6: Verify environment configuration
    if not verify_env_config():
        print_error("Environment configuration verification failed")
        sys.exit(1)
    
    # ========== Frontend Setup ==========
    if not BACKEND_ONLY:
        # Check Node.js
        if not check_node():
            print_error("Node.js is required for frontend")
            print_info("Please install Node.js and try again")
            sys.exit(1)
        
        # Check npm
        if not check_npm():
            print_error("npm is required for frontend")
            sys.exit(1)
        
        # Install frontend dependencies
        if not check_frontend_deps():
            if not install_frontend_deps():
                print_error("Failed to install frontend dependencies")
                print_info("You can still run backend only with --backend-only")
                response = input("Continue with backend only? (y/n): ")
                if response.lower() != 'y':
                    sys.exit(1)
                BACKEND_ONLY = True
        
        # Build frontend for production mode
        if PRODUCTION_MODE and not BACKEND_ONLY:
            if REBUILD_FRONTEND or not check_frontend_build():
                if not build_frontend():
                    print_error("Failed to build frontend")
                    sys.exit(1)
            else:
                print_success("Frontend already built (use --rebuild to force rebuild)")
    
    # ========== Start Servers ==========
    print("\n")
    
    # Start backend
    backend = start_backend()
    if not backend:
        print_error("Failed to start backend server")
        sys.exit(1)
    
    # Wait a bit for backend to start
    time.sleep(2)
    
    # Start frontend dev server (only in development mode)
    if not PRODUCTION_MODE and not BACKEND_ONLY:
        frontend = start_frontend()
        if not frontend:
            print_error("Failed to start frontend server")
            print_info("Backend is still running")
            cleanup_processes()
            sys.exit(1)
        
        # Wait a bit for frontend to start
        time.sleep(3)
    
    # Monitor processes
    monitor_processes()


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        print("\n")
        print_info("Shutdown signal received")
        cleanup_processes()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    if platform.system() != "Windows":
        signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        print_info("Startup cancelled by user")
        cleanup_processes()
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        cleanup_processes()
        sys.exit(1)
