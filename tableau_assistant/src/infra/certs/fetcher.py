"""
证书获取模块

提供从远程服务器获取SSL证书的功能。
"""
import ssl
import socket
from typing import Optional, List, Tuple, Dict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class CertificateFetcher:
    """证书获取器"""
    
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
    
    def fetch_server_certificate(
        self,
        hostname: str,
        port: int = 443,
        output_file: Optional[str] = None
    ) -> Tuple[dict, str]:
        """获取服务器证书"""
        logger.info(f"正在从 {hostname}:{port} 获取证书...")
        
        context = ssl.create_default_context()
        
        with socket.create_connection((hostname, port), timeout=self.timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                cert_bin = ssock.getpeercert(binary_form=True)
                cert_pem = ssl.DER_cert_to_PEM_cert(cert_bin)
                
                if output_file:
                    output_path = Path(output_file)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(cert_pem)
                    logger.info(f"证书已保存到: {output_file}")
                
                return cert, cert_pem
    
    def fetch_certificate_chain(
        self,
        hostname: str,
        port: int = 443,
        output_file: Optional[str] = None
    ) -> List[str]:
        """
        获取完整证书链（服务器证书 + 中间证书 + 根证书）
        
        Args:
            hostname: 服务器主机名
            port: 端口号
            output_file: 可选，保存完整证书链的文件路径
            
        Returns:
            PEM 格式的证书列表
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with socket.create_connection((hostname, port), timeout=self.timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                # 尝试获取完整证书链
                try:
                    certs = ssock.get_verified_chain()
                    if certs:
                        pem_certs = []
                        for cert_bytes in certs:
                            # cert_bytes 已经是 DER 格式的 bytes
                            cert_pem = ssl.DER_cert_to_PEM_cert(cert_bytes)
                            pem_certs.append(cert_pem)
                        
                        logger.info(f"获取到 {len(pem_certs)} 个证书的完整链")
                        
                        if output_file:
                            full_chain = "\n".join(pem_certs)
                            output_path = Path(output_file)
                            output_path.parent.mkdir(parents=True, exist_ok=True)
                            output_path.write_text(full_chain)
                            logger.info(f"证书链已保存到: {output_file}")
                        
                        return pem_certs
                except AttributeError:
                    # Python < 3.10 没有 get_verified_chain
                    logger.warning("get_verified_chain 不可用，回退到单证书模式")
                
                # 回退：只获取服务器证书
                cert_bin = ssock.getpeercert(binary_form=True)
                cert_pem = ssl.DER_cert_to_PEM_cert(cert_bin)
                
                if output_file:
                    output_path = Path(output_file)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(cert_pem)
                    logger.info(f"证书已保存到: {output_file}")
                
                return [cert_pem]
    
    def create_certificate_chain(
        self,
        server_cert_file: str,
        intermediate_cert_file: str,
        output_file: str
    ) -> str:
        """创建完整的证书链文件"""
        server_cert = Path(server_cert_file).read_text()
        intermediate_cert = Path(intermediate_cert_file).read_text()
        
        full_chain = server_cert.strip() + "\n\n" + intermediate_cert.strip() + "\n"
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_chain)
        
        logger.info(f"证书链已创建: {output_file}")
        return full_chain


__all__ = ["CertificateFetcher"]
