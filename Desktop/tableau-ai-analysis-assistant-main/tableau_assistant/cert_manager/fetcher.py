"""
证书获取模块

提供从远程服务器获取SSL证书的功能
"""
import ssl
import socket
import urllib.request
import base64
from typing import Optional, List, Tuple
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class CertificateFetcher:
    """
    证书获取器
    
    从远程服务器获取SSL证书和证书链
    """
    
    def __init__(self, timeout: int = 10):
        """
        初始化证书获取器
        
        Args:
            timeout: 连接超时时间(秒)
        """
        self.timeout = timeout
    
    def fetch_server_certificate(
        self,
        hostname: str,
        port: int = 443,
        output_file: Optional[str] = None
    ) -> Tuple[dict, str]:
        """
        获取服务器证书
        
        Args:
            hostname: 服务器主机名
            port: 端口号
            output_file: 输出文件路径(可选)
        
        Returns:
            (证书信息字典, PEM格式证书字符串)
        """
        logger.info(f"正在从 {hostname}:{port} 获取证书...")
        
        try:
            context = ssl.create_default_context()
            
            with socket.create_connection((hostname, port), timeout=self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    # 获取证书信息
                    cert = ssock.getpeercert()
                    cert_bin = ssock.getpeercert(binary_form=True)
                    
                    # 转换为PEM格式
                    cert_pem = ssl.DER_cert_to_PEM_cert(cert_bin)
                    
                    # 保存到文件
                    if output_file:
                        output_path = Path(output_file)
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_text(cert_pem)
                        logger.info(f"证书已保存到: {output_file}")
                    
                    logger.info(f"成功获取证书: {cert.get('subject')}")
                    return cert, cert_pem
        
        except ssl.SSLError as e:
            logger.error(f"SSL错误: {e}")
            raise
        except socket.timeout:
            logger.error(f"连接超时: {hostname}:{port}")
            raise
        except Exception as e:
            logger.error(f"获取证书失败: {e}")
            raise
    
    def fetch_certificate_chain(
        self,
        hostname: str,
        port: int = 443
    ) -> List[str]:
        """
        获取完整的证书链
        
        注意: 此方法依赖服务器发送完整的证书链
        
        Args:
            hostname: 服务器主机名
            port: 端口号
        
        Returns:
            证书链列表(PEM格式)
        """
        logger.info(f"正在从 {hostname}:{port} 获取证书链...")
        
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            
            with socket.create_connection((hostname, port), timeout=self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    # 获取证书链
                    cert_bin = ssock.getpeercert(binary_form=True)
                    cert_pem = ssl.DER_cert_to_PEM_cert(cert_bin)
                    
                    logger.info(f"协议: {ssock.version()}")
                    logger.info(f"加密套件: {ssock.cipher()}")
                    
                    # 注意: Python的ssl模块不直接提供获取完整证书链的方法
                    # 这里只返回服务器证书
                    return [cert_pem]
        
        except Exception as e:
            logger.error(f"获取证书链失败: {e}")
            raise
    
    def download_intermediate_certificate(
        self,
        url: str,
        output_file: Optional[str] = None
    ) -> str:
        """
        从URL下载中间证书
        
        Args:
            url: 证书下载URL
            output_file: 输出文件路径(可选)
        
        Returns:
            PEM格式证书字符串
        """
        logger.info(f"正在从 {url} 下载证书...")
        
        try:
            context = ssl.create_default_context()
            
            with urllib.request.urlopen(url, context=context, timeout=self.timeout) as response:
                cert_data = response.read()
                
                # 检查是否是DER格式
                if cert_data.startswith(b'\x30\x82'):
                    logger.debug("检测到DER格式,转换为PEM")
                    # 转换为PEM格式
                    cert_b64 = base64.b64encode(cert_data).decode('ascii')
                    
                    # 格式化为PEM
                    pem_cert = "-----BEGIN CERTIFICATE-----\n"
                    for i in range(0, len(cert_b64), 64):
                        pem_cert += cert_b64[i:i+64] + "\n"
                    pem_cert += "-----END CERTIFICATE-----\n"
                else:
                    # 假设已经是PEM格式
                    pem_cert = cert_data.decode('utf-8')
                
                # 保存到文件
                if output_file:
                    output_path = Path(output_file)
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(pem_cert)
                    logger.info(f"证书已保存到: {output_file}")
                
                logger.info("证书下载成功")
                return pem_cert
        
        except Exception as e:
            logger.error(f"下载证书失败: {e}")
            raise
    
    def create_certificate_chain(
        self,
        server_cert_file: str,
        intermediate_cert_file: str,
        output_file: str
    ) -> str:
        """
        创建完整的证书链文件
        
        Args:
            server_cert_file: 服务器证书文件路径
            intermediate_cert_file: 中间证书文件路径
            output_file: 输出文件路径
        
        Returns:
            完整证书链内容
        """
        logger.info("正在创建证书链...")
        
        try:
            # 读取服务器证书
            server_cert = Path(server_cert_file).read_text()
            logger.debug(f"读取服务器证书: {server_cert_file}")
            
            # 读取中间证书
            intermediate_cert = Path(intermediate_cert_file).read_text()
            logger.debug(f"读取中间证书: {intermediate_cert_file}")
            
            # 合并证书链
            full_chain = server_cert.strip() + "\n\n" + intermediate_cert.strip() + "\n"
            
            # 保存到文件
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(full_chain)
            
            logger.info(f"证书链已创建: {output_file}")
            return full_chain
        
        except Exception as e:
            logger.error(f"创建证书链失败: {e}")
            raise
    
    def fetch_deepseek_certificates(
        self,
        output_dir: str = "certs"
    ) -> dict:
        """
        获取DeepSeek API的完整证书链
        
        这是一个便捷方法,专门用于获取DeepSeek的证书
        
        Args:
            output_dir: 输出目录
        
        Returns:
            包含证书文件路径的字典
        """
        logger.info("正在获取DeepSeek证书...")
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        result = {}
        
        try:
            # 1. 获取服务器证书
            server_cert_file = output_path / "deepseek_server.pem"
            _, server_cert = self.fetch_server_certificate(
                "api.deepseek.com",
                443,
                str(server_cert_file)
            )
            result["server_cert"] = str(server_cert_file)
            
            # 2. 下载中间证书
            intermediate_cert_file = output_path / "geotrust_intermediate.pem"
            
            # GeoTrust TLS RSA CA G1 中间证书URL
            intermediate_urls = [
                "https://cacerts.digicert.com/GeoTrustTLSRSACAG1.crt",
                "https://cacerts.geotrust.com/GeoTrustTLSRSACAG1.crt",
            ]
            
            intermediate_cert = None
            for url in intermediate_urls:
                try:
                    intermediate_cert = self.download_intermediate_certificate(
                        url,
                        str(intermediate_cert_file)
                    )
                    result["intermediate_cert"] = str(intermediate_cert_file)
                    break
                except Exception as e:
                    logger.warning(f"从 {url} 下载失败: {e}")
                    continue
            
            if not intermediate_cert:
                logger.warning("无法下载中间证书,使用内置证书")
                # 使用内置的GeoTrust中间证书
                intermediate_cert = self._get_builtin_geotrust_cert()
                intermediate_cert_file.write_text(intermediate_cert)
                result["intermediate_cert"] = str(intermediate_cert_file)
            
            # 3. 创建完整证书链
            full_chain_file = output_path / "deepseek_full_chain.pem"
            self.create_certificate_chain(
                str(server_cert_file),
                str(intermediate_cert_file),
                str(full_chain_file)
            )
            result["full_chain"] = str(full_chain_file)
            
            logger.info("DeepSeek证书获取完成")
            return result
        
        except Exception as e:
            logger.error(f"获取DeepSeek证书失败: {e}")
            raise
    
    def fetch_tableau_certificates(
        self,
        tableau_domain: str,
        output_dir: str = "certs"
    ) -> dict:
        """
        获取Tableau Server的证书
        
        Args:
            tableau_domain: Tableau服务器域名 (例如: https://tableau.company.com)
            output_dir: 输出目录
        
        Returns:
            包含证书文件路径的字典
        """
        logger.info(f"正在获取Tableau Server证书: {tableau_domain}")
        
        # 解析域名
        from urllib.parse import urlparse
        parsed = urlparse(tableau_domain)
        hostname = parsed.hostname or parsed.path.split('/')[0]
        port = parsed.port or 443
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        result = {}
        
        try:
            # 获取服务器证书
            safe_hostname = hostname.replace('.', '_')
            server_cert_file = output_path / f"tableau_{safe_hostname}_cert.pem"
            
            _, server_cert = self.fetch_server_certificate(
                hostname,
                port,
                str(server_cert_file)
            )
            result["server_cert"] = str(server_cert_file)
            result["hostname"] = hostname
            result["port"] = port
            
            logger.info("Tableau Server证书获取完成")
            return result
        
        except Exception as e:
            logger.error(f"获取Tableau Server证书失败: {e}")
            raise
    
    def _get_builtin_geotrust_cert(self) -> str:
        """
        获取内置的GeoTrust中间证书
        
        这是一个备用方案,当无法从DigiCert官网下载中间证书时使用。
        这个证书是公开的,可以从DigiCert官方网站获取。
        
        证书信息:
        - 名称: GeoTrust TLS RSA CA G1
        - 颁发者: DigiCert Global Root G2
        - 有效期: 2017-11-02 至 2027-11-02
        - 用途: 作为DeepSeek API证书的中间CA
        
        Returns:
            PEM格式的证书字符串
        """
        return """-----BEGIN CERTIFICATE-----
MIIEjTCCA3WgAwIBAgIQDQd4KhM/xvmlcpbhMf/ReTANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0xNzExMDIxMjIzMzdaFw0yNzExMDIxMjIzMzdaMGAxCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xHzAdBgNVBAMTFkdlb1RydXN0IFRMUyBSU0EgQ0EgRzEwggEiMA0GCSqGSIb3
DQEBAQUAA4IBDwAwggEKAoIBAQC+F+jsvikKy/65LWEx/TMkCDIuWegh1Ngwvm4Q
yISgP7oU5d79eoySG3vOhC3w/3jEMuipoH1fBtp7m0tTpsYbAhch4XA7rfuD6whU
gajeErLVxoiWMPkC/DnUvbgi74BJmdBiuGHQSd7LwsuXpTEGG9fYXcbTVN5SATYq
DfbexbYxTMwVJWoVb6lrBEgM3gBBqiiAiy800xu1Nq07JdCIQkBsNpFtZbIZhsDS
fzlGWP4wEmBQ3O67c+ZXkFr2DcrXBEtHam80Gp2SNhou2U5U7UesDL/xgLK6/0d7
6TnEVMSUVJkZ8VeZr+IUIlvoLrtjLbqugb0T3OYXW+CQU0kBAgMBAAGjggFAMIIB
PDAdBgNVHQ4EFgQUlE/UXYvkpOKmgP792PkA76O+AlcwHwYDVR0jBBgwFoAUTiJU
IBiV5uNu5g/6+rkS7QYXjzkwDgYDVR0PAQH/BAQDAgGGMB0GA1UdJQQWMBQGCCsG
AQUFBwMBBggrBgEFBQcDAjASBgNVHRMBAf8ECDAGAQH/AgEAMDQGCCsGAQUFBwEB
BCgwJjAkBggrBgEFBQcwAYYYaHR0cDovL29jc3AuZGlnaWNlcnQuY29tMEIGA1Ud
HwQ7MDkwN6A1oDOGMWh0dHA6Ly9jcmwzLmRpZ2ljZXJ0LmNvbS9EaWdpQ2VydEds
b2JhbFJvb3RHMi5jcmwwPQYDVR0gBDYwNDAyBgRVHSAAMCowKAYIKwYBBQUHAgEW
HGh0dHBzOi8vd3d3LmRpZ2ljZXJ0LmNvbS9DUFMwDQYJKoZIhvcNAQELBQADggEB
AIIcBDqC6cWpyGUSXAjjAcYwsK4iiGF7KweG97i1RJz1kwZhRoo6orU1JtBYnjzB
c4+/sXmnHJk3mlPyL1xuIAt9sMeC7+vreRIF5wFBC0MCN5sbHwhNN1JzKbifNeP5
ozpZdQFmkCo+neBiKR6HqIA+LMTMCMMuv2khGGuPHmtDze4GmEGZtYLyF8EQpa5Y
jPuV6k2Cr/N3XxFpT3hRpt/3usU/Zb9wfKPtWpoznZ4/44c1p4rzFcZYrWkj3A+7
TNBJE0GmP2fhXhP1D/XVfIW/h0yCJGEiV9Glm/uGOa3DXHlmbAcxSyCRraG+ZBkA
7h4SeM6Y8l/7MBRpPCz6l8Y=
-----END CERTIFICATE-----"""
