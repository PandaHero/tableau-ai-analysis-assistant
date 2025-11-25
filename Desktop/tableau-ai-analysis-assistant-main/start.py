#!/usr/bin/env python
"""
One-click startup script for Tableau Assistant (Backend + Frontend).

This script automates the setup and launch process:
1. Checks Python version (>= 3.12)
2. Creates virtual environment if needed
3. Installs Python dependencies
4. Validates environment configuration
5. Checks Node.js and npm
6. Installs frontend dependencies
7. Starts both FastAPI server and Vue dev server
"""

import os
import sys
import subprocess
import platform
import time
import signal
from pathlib import Path
from threading import Thread


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


def install_dependencies():
    """Install dependencies from requirements.txt."""
    print_header("Installing Dependencies")
    
    pip_path = get_venv_pip()
    requirements_path = Path("tableau_assistant") / "requirements.txt"
    
    if not pip_path.exists():
        print_error(f"Pip not found at {pip_path}")
        sys.exit(1)
    
    if not requirements_path.exists():
        print_error(f"Requirements file not found at {requirements_path}")
        sys.exit(1)
    
    try:
        print_info("Installing dependencies from requirements.txt...")
        print_info("This may take a few minutes...")
        
        # Use absolute path to requirements.txt to avoid directory change issues
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
            print_info(f"Output: {e.stdout[:500]}")  # Show first 500 chars
        if e.stderr:
            print_error(f"Error: {e.stderr[:500]}")  # Show first 500 chars
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
    
    # Critical variables that must be set
    critical_vars = [
        "TABLEAU_DOMAIN",
        "TABLEAU_JWT_CLIENT_ID",
        "TABLEAU_JWT_SECRET_ID",
        "TABLEAU_JWT_SECRET",
        "TABLEAU_USER",
        "LLM_API_BASE"
    ]
    
    missing_vars = []
    placeholder_vars = []
    
    for var in critical_vars:
        if var not in env_vars or not env_vars[var]:
            missing_vars.append(var)
        elif env_vars[var].startswith('your-') or env_vars[var] == 'http://localhost:8000/v1':
            # Check for placeholder values
            if var != "LLM_API_BASE":  # LLM_API_BASE default is acceptable
                placeholder_vars.append(var)
    
    if missing_vars:
        print_error("Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print_info("\nPlease edit tableau_assistant/.env and set these variables")
        sys.exit(1)
    
    if placeholder_vars:
        print_error("Found placeholder values in environment variables:")
        for var in placeholder_vars:
            print(f"  - {var} = {env_vars[var]}")
        print_info("\nPlease edit tableau_assistant/.env and replace placeholder values")
        sys.exit(1)
    
    print_success("All critical environment variables are set")
    
    # Display configuration summary
    print_info("\nConfiguration Summary:")
    print(f"  Backend Host: {env_vars.get('HOST', '127.0.0.1')}")
    print(f"  Backend Port: {env_vars.get('PORT', '8000')}")
    print(f"  Frontend Host: {env_vars.get('VITE_APP_HOST', '127.0.0.1')}")
    print(f"  Frontend Port: {env_vars.get('VITE_APP_PORT', '5173')}")
    print(f"  Tableau Domain: {env_vars.get('TABLEAU_DOMAIN', 'Not set')}")
    print(f"  Tableau Site: {env_vars.get('TABLEAU_SITE', 'Not set')}")
    print(f"  Tableau User: {env_vars.get('TABLEAU_USER', 'Not set')}")
    print(f"  LLM API Base: {env_vars.get('LLM_API_BASE', 'Not set')}")
    
    return True


def verify_env_config():
    """Verify environment configuration and enforce HTTPS."""
    print_header("Verifying Environment Configuration")
    
    root_env = Path(".env")
    
    if not root_env.exists():
        print_error("Root .env file not found!")
        return False
    
    print_success("Root .env file found")
    
    # Load and verify SSL configuration
    env_vars = load_env_vars()
    host = env_vars.get('HOST', '127.0.0.1')
    port = env_vars.get('PORT', '8000')
    ssl_cert = env_vars.get('SSL_CERT_FILE', '')
    ssl_key = env_vars.get('SSL_KEY_FILE', '')
    frontend_ssl_cert = env_vars.get('FRONTEND_SSL_CERT_FILE', '')
    frontend_ssl_key = env_vars.get('FRONTEND_SSL_KEY_FILE', '')
    
    # 强制检查后端SSL配置
    if not ssl_cert or not ssl_key:
        print_error("❌ Backend SSL certificates are required!")
        print_error("   Please configure SSL_CERT_FILE and SSL_KEY_FILE in .env")
        return False
    
    if not Path(ssl_cert).exists():
        print_error(f"❌ Backend SSL certificate not found: {ssl_cert}")
        return False
    
    if not Path(ssl_key).exists():
        print_error(f"❌ Backend SSL key not found: {ssl_key}")
        return False
    
    print_success(f"✓ Backend SSL configured: {ssl_cert}")
    
    # 强制检查前端SSL配置
    if not frontend_ssl_cert or not frontend_ssl_key:
        print_error("❌ Frontend SSL certificates are required!")
        print_error("   Please configure FRONTEND_SSL_CERT_FILE and FRONTEND_SSL_KEY_FILE in .env")
        return False
    
    print_success(f"✓ Frontend SSL configured: {frontend_ssl_cert}")
    
    # 显示HTTPS配置
    api_base_url = f"https://{host}:{port}"
    print_info(f"API URL: {api_base_url}")
    print_success("🔒 HTTPS enforced for production")
    
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
            shell=True  # Use shell on Windows
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
    
    node_modules = Path("tableau_extension") / "node_modules"
    
    if node_modules.exists():
        print_success("Frontend dependencies found")
        return True
    else:
        print_info("Frontend dependencies not found")
        return False


def install_frontend_deps():
    """Install frontend dependencies."""
    print_header("Installing Frontend Dependencies")
    
    frontend_path = Path("tableau_extension")
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
            shell=True  # Use shell on Windows
        )
        
        print_success("Frontend dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install frontend dependencies")
        print_error(f"Exit code: {e.returncode}")
        if e.stderr:
            print_error(f"Error: {e.stderr[:500]}")
        print_info("\nPlease try manually:")
        print_info(f"  cd tableau_extension")
        print_info(f"  npm install")
        return False


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
    
    # Check if SSL is configured
    ssl_cert = env_vars.get('SSL_CERT_FILE', '')
    ssl_key = env_vars.get('SSL_KEY_FILE', '')
    
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
        "--reload"
    ]
    
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
            universal_newlines=True
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
    
    frontend_path = Path("tableau_extension")
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
            shell=True  # Use shell on Windows
        )
        
        # Determine frontend protocol based on SSL configuration
        env_vars = load_env_vars()
        frontend_ssl_cert = env_vars.get('FRONTEND_SSL_CERT_FILE', '')
        frontend_ssl_key = env_vars.get('FRONTEND_SSL_KEY_FILE', '')
        frontend_host = env_vars.get('VITE_APP_HOST', '127.0.0.1')
        frontend_port = env_vars.get('VITE_APP_PORT', '5173')
        
        # Check if frontend SSL is configured
        if frontend_ssl_cert and frontend_ssl_key:
            frontend_protocol = "https"
            print_success("✓ Frontend server started (HTTPS enabled)")
        else:
            frontend_protocol = "http"
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
    
    # Backend protocol
    ssl_cert = env_vars.get('SSL_CERT_FILE', '')
    ssl_key = env_vars.get('SSL_KEY_FILE', '')
    backend_protocol = "https" if (ssl_cert and ssl_key and Path(ssl_cert).exists() and Path(ssl_key).exists()) else "http"
    
    # Frontend protocol
    frontend_ssl_cert = env_vars.get('FRONTEND_SSL_CERT_FILE', '')
    frontend_ssl_key = env_vars.get('FRONTEND_SSL_KEY_FILE', '')
    frontend_protocol = "https" if (frontend_ssl_cert and frontend_ssl_key) else "http"
    
    # Get host and port from env
    backend_host = env_vars.get('HOST', '127.0.0.1')
    backend_port = env_vars.get('PORT', '8000')
    frontend_host = env_vars.get('VITE_APP_HOST', '127.0.0.1')
    frontend_port = env_vars.get('VITE_APP_PORT', '5173')
    
    print_header("Servers Running")
    print_success("Both servers are running!")
    print_info("\nAccess URLs:")
    print(f"  Frontend:  {frontend_protocol}://{frontend_host}:{frontend_port}")
    print(f"  Demo Page: {frontend_protocol}://{frontend_host}:{frontend_port}/streaming-demo")
    print(f"  Backend:   {backend_protocol}://{backend_host}:{backend_port}")
    print(f"  API Docs:  {backend_protocol}://{backend_host}:{backend_port}/docs")
    print_info("\nPress Ctrl+C to stop all servers")
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
    print_header("Tableau Assistant - One-Click Startup")
    print_info("Starting Backend + Frontend servers...\n")
    
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
    # Step 8: Check Node.js
    if not check_node():
        print_error("Node.js is required for frontend")
        print_info("Please install Node.js and try again")
        sys.exit(1)
    
    # Step 9: Check npm
    if not check_npm():
        print_error("npm is required for frontend")
        sys.exit(1)
    
    # Step 10: Install frontend dependencies
    if not check_frontend_deps():
        if not install_frontend_deps():
            print_error("Failed to install frontend dependencies")
            print_info("You can still run backend only")
            response = input("Continue with backend only? (y/n): ")
            if response.lower() != 'y':
                sys.exit(1)
    
    # ========== Start Servers ==========
    print("\n")
    
    # Start backend
    backend = start_backend()
    if not backend:
        print_error("Failed to start backend server")
        sys.exit(1)
    
    # Wait a bit for backend to start
    time.sleep(2)
    
    # Start frontend
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
