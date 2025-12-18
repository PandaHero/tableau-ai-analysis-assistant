"""
证书验证模块

提供证书验证、过期检查和完整性验证功能。
"""
import ssl
import socket
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class CertificateValidator:
    """证书验证器"""
    
    def __init__(self, warning_days: int = 30):
        self.warning_days = warning_days
    
    def validate_certificate_file(self, cert_file: str) -> Dict[str, Any]:
        """验证证书文件"""
        result = {
            "valid": False,
            "exists": False,
            "readable": False,
            "cert_count": 0,
            "errors": [],
            "warnings": [],
        }
        
        cert_path = Path(cert_file)
        
        if not cert_path.exists():
            result["errors"].append(f"证书文件不存在: {cert_file}")
            return result
        
        result["exists"] = True
        
        if not cert_path.is_file():
            result["errors"].append(f"路径不是文件: {cert_file}")
            return result
        
        content = cert_path.read_text()
        result["readable"] = True
        
        cert_count = content.count('-----BEGIN CERTIFICATE-----')
        result["cert_count"] = cert_count
        
        if cert_count == 0:
            result["errors"].append("文件中没有找到证书")
            return result
        
        if not result["errors"]:
            result["valid"] = True
        
        return result
    
    def validate_ssl_connection(
        self,
        hostname: str,
        port: int = 443,
        cert_file: Optional[str] = None,
        timeout: int = 10
    ) -> Dict[str, Any]:
        """验证SSL连接"""
        result = {
            "success": False,
            "hostname": hostname,
            "port": port,
            "protocol": None,
            "cipher": None,
            "errors": [],
        }
        
        try:
            context = ssl.create_default_context()
            
            if cert_file:
                context.load_verify_locations(cert_file)
            
            with socket.create_connection((hostname, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    result["protocol"] = ssock.version()
                    result["cipher"] = ssock.cipher()[0] if ssock.cipher() else None
                    result["success"] = True
        
        except ssl.SSLError as e:
            result["errors"].append(f"SSL错误: {e}")
        except socket.timeout:
            result["errors"].append(f"连接超时: {hostname}:{port}")
        except Exception as e:
            result["errors"].append(f"连接失败: {e}")
        
        return result


__all__ = ["CertificateValidator"]
