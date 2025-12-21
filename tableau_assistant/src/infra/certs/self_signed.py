"""
自签名证书生成器

用于开发环境自动生成 SSL 证书。
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import ipaddress

logger = logging.getLogger(__name__)


class SelfSignedGenerator:
    """
    自签名证书生成器
    
    生成用于开发环境的自签名 SSL 证书，包括：
    - CA 证书
    - 服务器证书
    - 私钥
    
    使用示例:
        generator = SelfSignedGenerator("tableau_assistant/certs")
        paths = generator.generate()
        # paths = {"ca_cert": "...", "server_cert": "...", "server_key": "..."}
    """
    
    DEFAULT_HOSTNAMES = ["localhost", "127.0.0.1", "0.0.0.0"]
    
    def __init__(
        self,
        cert_dir: str,
        validity_days: int = 365,
        key_size: int = 2048
    ):
        """
        初始化生成器
        
        Args:
            cert_dir: 证书存储目录
            validity_days: 证书有效期（天）
            key_size: RSA 密钥长度
        """
        self.cert_dir = Path(cert_dir)
        self.validity_days = validity_days
        self.key_size = key_size
        
        # 证书文件名
        self.ca_cert_file = "app_ca.pem"
        self.server_cert_file = "app_server.pem"
        self.server_key_file = "app_server_key.pem"
    
    def generate(
        self,
        hostnames: Optional[List[str]] = None,
        force: bool = False
    ) -> Dict[str, str]:
        """
        生成自签名证书
        
        Args:
            hostnames: 额外的主机名列表
            force: 是否强制重新生成
            
        Returns:
            证书文件路径字典
        """
        # 确保目录存在
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查现有证书
        if not force:
            existing = self.check_existing()
            if existing:
                logger.info("使用现有的有效自签名证书")
                return existing
        
        logger.info("生成新的自签名证书...")
        
        # 合并主机名
        all_hostnames = list(self.DEFAULT_HOSTNAMES)
        if hostnames:
            all_hostnames.extend(hostnames)
        all_hostnames = list(set(all_hostnames))  # 去重
        
        # 生成 CA
        ca_cert, ca_key = self._generate_ca()
        
        # 生成服务器证书
        server_cert, server_key = self._generate_server_cert(
            ca_cert, ca_key, all_hostnames
        )
        
        # 保存证书
        paths = self._save_certificates(ca_cert, ca_key, server_cert, server_key)
        
        logger.info(f"自签名证书已生成: {self.cert_dir}")
        return paths
    
    def check_existing(self) -> Optional[Dict[str, str]]:
        """
        检查现有证书是否有效
        
        Returns:
            如果有效返回路径字典，否则返回 None
        """
        ca_path = self.cert_dir / self.ca_cert_file
        cert_path = self.cert_dir / self.server_cert_file
        key_path = self.cert_dir / self.server_key_file
        
        # 检查文件是否存在
        if not all(p.exists() for p in [ca_path, cert_path, key_path]):
            return None
        
        # 检查证书是否过期
        try:
            cert_pem = cert_path.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            
            now = datetime.now(timezone.utc)
            if cert.not_valid_after_utc < now:
                logger.info("自签名证书已过期，需要重新生成")
                return None
            
            # 检查是否即将过期（7天内）
            if cert.not_valid_after_utc < now + timedelta(days=7):
                logger.warning("自签名证书即将过期，重新生成")
                return None
            
            return {
                "ca_cert": str(ca_path),
                "server_cert": str(cert_path),
                "server_key": str(key_path),
            }
        except Exception as e:
            logger.warning(f"检查现有证书失败: {e}")
            return None
    
    def _generate_ca(self) -> Tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """生成 CA 证书"""
        # 生成 CA 私钥
        ca_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.key_size,
            backend=default_backend()
        )
        
        # CA 主题
        ca_name = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Shanghai"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Shanghai"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Tableau Assistant"),
            x509.NameAttribute(NameOID.COMMON_NAME, "Tableau Assistant CA"),
        ])
        
        # 构建 CA 证书
        now = datetime.now(timezone.utc)
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(ca_name)
            .issuer_name(ca_name)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=self.validity_days * 2))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    key_encipherment=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True
            )
            .sign(ca_key, hashes.SHA256(), default_backend())
        )
        
        return ca_cert, ca_key
    
    def _generate_server_cert(
        self,
        ca_cert: x509.Certificate,
        ca_key: rsa.RSAPrivateKey,
        hostnames: List[str]
    ) -> Tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """生成服务器证书"""
        # 生成服务器私钥
        server_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.key_size,
            backend=default_backend()
        )
        
        # 服务器主题
        server_name = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Shanghai"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Shanghai"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Tableau Assistant"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        
        # 构建 SAN (Subject Alternative Names)
        san_list = []
        for hostname in hostnames:
            try:
                # 尝试解析为 IP 地址
                ip = ipaddress.ip_address(hostname)
                san_list.append(x509.IPAddress(ip))
            except ValueError:
                # 不是 IP，作为 DNS 名称
                san_list.append(x509.DNSName(hostname))
        
        # 构建服务器证书
        now = datetime.now(timezone.utc)
        server_cert = (
            x509.CertificateBuilder()
            .subject_name(server_name)
            .issuer_name(ca_cert.subject)
            .public_key(server_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=self.validity_days))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    key_cert_sign=False,
                    crl_sign=False,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True
            )
            .add_extension(
                x509.ExtendedKeyUsage([
                    ExtendedKeyUsageOID.SERVER_AUTH,
                    ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False
            )
            .add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False
            )
            .sign(ca_key, hashes.SHA256(), default_backend())
        )
        
        return server_cert, server_key
    
    def _save_certificates(
        self,
        ca_cert: x509.Certificate,
        ca_key: rsa.RSAPrivateKey,
        server_cert: x509.Certificate,
        server_key: rsa.RSAPrivateKey
    ) -> Dict[str, str]:
        """保存证书到文件"""
        ca_path = self.cert_dir / self.ca_cert_file
        cert_path = self.cert_dir / self.server_cert_file
        key_path = self.cert_dir / self.server_key_file
        
        # 保存 CA 证书
        ca_path.write_bytes(
            ca_cert.public_bytes(serialization.Encoding.PEM)
        )
        
        # 保存服务器证书（包含 CA 证书形成完整链）
        cert_chain = (
            server_cert.public_bytes(serialization.Encoding.PEM) +
            ca_cert.public_bytes(serialization.Encoding.PEM)
        )
        cert_path.write_bytes(cert_chain)
        
        # 保存服务器私钥
        key_path.write_bytes(
            server_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )
        
        # 设置私钥文件权限（仅所有者可读写）
        try:
            key_path.chmod(0o600)
        except Exception:
            pass  # Windows 可能不支持
        
        return {
            "ca_cert": str(ca_path),
            "server_cert": str(cert_path),
            "server_key": str(key_path),
        }


__all__ = ["SelfSignedGenerator"]
