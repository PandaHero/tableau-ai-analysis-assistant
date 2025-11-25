"""
证书验证模块

提供证书验证、过期检查和完整性验证功能
"""
import ssl
import socket
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class CertificateValidator:
    """
    证书验证器
    
    验证证书的有效性、过期时间和完整性
    """
    
    def __init__(self, warning_days: int = 30):
        """
        初始化证书验证器
        
        Args:
            warning_days: 证书过期前多少天开始警告
        """
        self.warning_days = warning_days
    
    def validate_certificate_file(self, cert_file: str) -> Dict[str, Any]:
        """
        验证证书文件
        
        Args:
            cert_file: 证书文件路径
        
        Returns:
            验证结果字典
        """
        logger.info(f"正在验证证书文件: {cert_file}")
        
        result = {
            "valid": False,
            "exists": False,
            "readable": False,
            "cert_count": 0,
            "errors": [],
            "warnings": [],
        }
        
        try:
            cert_path = Path(cert_file)
            
            # 检查文件是否存在
            if not cert_path.exists():
                result["errors"].append(f"证书文件不存在: {cert_file}")
                return result
            
            result["exists"] = True
            
            # 检查文件是否可读
            if not cert_path.is_file():
                result["errors"].append(f"路径不是文件: {cert_file}")
                return result
            
            content = cert_path.read_text()
            result["readable"] = True
            
            # 统计证书数量
            cert_count = content.count('-----BEGIN CERTIFICATE-----')
            result["cert_count"] = cert_count
            
            if cert_count == 0:
                result["errors"].append("文件中没有找到证书")
                return result
            
            # 验证证书格式
            if not self._validate_pem_format(content):
                result["errors"].append("证书格式无效")
                return result
            
            # 检查证书过期时间
            expiry_info = self._check_certificate_expiry(cert_file)
            if expiry_info:
                result.update(expiry_info)
                
                if expiry_info.get("expired"):
                    result["errors"].append(f"证书已过期: {expiry_info.get('not_after')}")
                elif expiry_info.get("expiring_soon"):
                    result["warnings"].append(
                        f"证书即将过期: {expiry_info.get('not_after')} "
                        f"(剩余{expiry_info.get('days_remaining')}天)"
                    )
            
            # 如果没有错误,标记为有效
            if not result["errors"]:
                result["valid"] = True
                logger.info(f"证书文件验证通过: {cert_file}")
            else:
                logger.error(f"证书文件验证失败: {', '.join(result['errors'])}")
            
            return result
        
        except Exception as e:
            logger.error(f"验证证书文件时出错: {e}")
            result["errors"].append(str(e))
            return result
    
    def _validate_pem_format(self, content: str) -> bool:
        """验证PEM格式"""
        begin_count = content.count('-----BEGIN CERTIFICATE-----')
        end_count = content.count('-----END CERTIFICATE-----')
        
        return begin_count > 0 and begin_count == end_count
    
    def _check_certificate_expiry(self, cert_file: str) -> Optional[Dict[str, Any]]:
        """
        检查证书过期时间
        
        Args:
            cert_file: 证书文件路径
        
        Returns:
            过期信息字典
        """
        try:
            import OpenSSL.crypto as crypto
            
            cert_path = Path(cert_file)
            content = cert_path.read_text()
            
            # 提取第一个证书
            begin_marker = '-----BEGIN CERTIFICATE-----'
            end_marker = '-----END CERTIFICATE-----'
            
            begin_idx = content.find(begin_marker)
            end_idx = content.find(end_marker, begin_idx)
            
            if begin_idx == -1 or end_idx == -1:
                return None
            
            first_cert_pem = content[begin_idx:end_idx + len(end_marker)]
            
            # 解析证书
            cert = crypto.load_certificate(crypto.FILETYPE_PEM, first_cert_pem)
            
            # 获取过期时间
            not_after_bytes = cert.get_notAfter()
            not_after_str = not_after_bytes.decode('ascii')
            
            # 解析时间 (格式: YYYYMMDDHHmmssZ)
            not_after = datetime.strptime(not_after_str, '%Y%m%d%H%M%SZ')
            
            # 获取生效时间
            not_before_bytes = cert.get_notBefore()
            not_before_str = not_before_bytes.decode('ascii')
            not_before = datetime.strptime(not_before_str, '%Y%m%d%H%M%SZ')
            
            # 计算剩余天数
            now = datetime.utcnow()
            days_remaining = (not_after - now).days
            
            return {
                "not_before": not_before.isoformat(),
                "not_after": not_after.isoformat(),
                "days_remaining": days_remaining,
                "expired": days_remaining < 0,
                "expiring_soon": 0 <= days_remaining < self.warning_days,
            }
        
        except ImportError:
            logger.warning("pyOpenSSL未安装,跳过证书过期检查")
            return None
        except Exception as e:
            logger.warning(f"检查证书过期时间失败: {e}")
            return None
    
    def validate_ssl_connection(
        self,
        hostname: str,
        port: int = 443,
        cert_file: Optional[str] = None,
        timeout: int = 10
    ) -> Dict[str, Any]:
        """
        验证SSL连接
        
        Args:
            hostname: 主机名
            port: 端口号
            cert_file: 证书文件路径(可选)
            timeout: 超时时间
        
        Returns:
            验证结果字典
        """
        logger.info(f"正在验证SSL连接: {hostname}:{port}")
        
        result = {
            "success": False,
            "hostname": hostname,
            "port": port,
            "protocol": None,
            "cipher": None,
            "cert_info": {},
            "errors": [],
        }
        
        try:
            # 创建SSL上下文
            context = ssl.create_default_context()
            
            if cert_file:
                context.load_verify_locations(cert_file)
                logger.debug(f"使用证书文件: {cert_file}")
            
            # 连接服务器
            with socket.create_connection((hostname, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    # 获取连接信息
                    result["protocol"] = ssock.version()
                    result["cipher"] = ssock.cipher()[0] if ssock.cipher() else None
                    
                    # 获取证书信息
                    cert = ssock.getpeercert()
                    result["cert_info"] = {
                        "subject": dict(x[0] for x in cert.get('subject', [])),
                        "issuer": dict(x[0] for x in cert.get('issuer', [])),
                        "version": cert.get('version'),
                        "serial_number": cert.get('serialNumber'),
                        "not_before": cert.get('notBefore'),
                        "not_after": cert.get('notAfter'),
                    }
                    
                    result["success"] = True
                    logger.info(f"SSL连接验证成功: {hostname}:{port}")
        
        except ssl.SSLError as e:
            error_msg = f"SSL错误: {e}"
            result["errors"].append(error_msg)
            logger.error(error_msg)
        except socket.timeout:
            error_msg = f"连接超时: {hostname}:{port}"
            result["errors"].append(error_msg)
            logger.error(error_msg)
        except Exception as e:
            error_msg = f"连接失败: {e}"
            result["errors"].append(error_msg)
            logger.error(error_msg)
        
        return result
    
    def validate_certificate_chain(
        self,
        cert_file: str
    ) -> Dict[str, Any]:
        """
        验证证书链完整性
        
        Args:
            cert_file: 证书链文件路径
        
        Returns:
            验证结果字典
        """
        logger.info(f"正在验证证书链: {cert_file}")
        
        result = {
            "valid": False,
            "cert_count": 0,
            "certificates": [],
            "errors": [],
            "warnings": [],
        }
        
        try:
            import OpenSSL.crypto as crypto
            
            cert_path = Path(cert_file)
            content = cert_path.read_text()
            
            # 分割证书
            certs = []
            current_cert = []
            in_cert = False
            
            for line in content.split('\n'):
                if '-----BEGIN CERTIFICATE-----' in line:
                    in_cert = True
                    current_cert = [line]
                elif '-----END CERTIFICATE-----' in line:
                    current_cert.append(line)
                    certs.append('\n'.join(current_cert))
                    in_cert = False
                    current_cert = []
                elif in_cert:
                    current_cert.append(line)
            
            result["cert_count"] = len(certs)
            
            if len(certs) == 0:
                result["errors"].append("证书链中没有找到证书")
                return result
            
            # 验证每个证书
            for i, cert_pem in enumerate(certs, 1):
                try:
                    cert = crypto.load_certificate(crypto.FILETYPE_PEM, cert_pem)
                    subject = cert.get_subject()
                    issuer = cert.get_issuer()
                    
                    cert_info = {
                        "index": i,
                        "subject_cn": subject.CN,
                        "issuer_cn": issuer.CN,
                        "not_before": cert.get_notBefore().decode('ascii'),
                        "not_after": cert.get_notAfter().decode('ascii'),
                    }
                    
                    result["certificates"].append(cert_info)
                    logger.debug(f"证书 {i}: {subject.CN} (颁发者: {issuer.CN})")
                
                except Exception as e:
                    result["errors"].append(f"证书 {i} 解析失败: {e}")
            
            # 验证证书链顺序
            if len(result["certificates"]) > 1:
                for i in range(len(result["certificates"]) - 1):
                    current = result["certificates"][i]
                    next_cert = result["certificates"][i + 1]
                    
                    # 检查当前证书的颁发者是否是下一个证书的主题
                    if current["issuer_cn"] != next_cert["subject_cn"]:
                        result["warnings"].append(
                            f"证书链可能不完整: 证书{i+1}的颁发者({current['issuer_cn']}) "
                            f"与证书{i+2}的主题({next_cert['subject_cn']})不匹配"
                        )
            
            # 如果没有错误,标记为有效
            if not result["errors"]:
                result["valid"] = True
                logger.info(f"证书链验证通过: {cert_file}")
            else:
                logger.error(f"证书链验证失败: {', '.join(result['errors'])}")
            
            return result
        
        except ImportError:
            logger.warning("pyOpenSSL未安装,跳过证书链验证")
            result["errors"].append("pyOpenSSL未安装")
            return result
        except Exception as e:
            logger.error(f"验证证书链时出错: {e}")
            result["errors"].append(str(e))
            return result
