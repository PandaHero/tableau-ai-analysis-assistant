"""
Tableau Assistant - 基于 DeepAgents 的 Tableau 数据分析助手

主要模块：
- src: 源代码
- tests: 测试代码
"""

__version__ = "0.1.0"


# ============================================
# 自动证书设置（应用启动时执行）
# ============================================

def _auto_setup_certificates():
    """
    应用启动时自动设置证书
    
    使用证书管理器，支持：
    - 多服务证书管理
    """
    try:
        import os
        import logging
        from pathlib import Path
        
        # 配置日志（如果还没配置）
        if not logging.getLogger().handlers:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        logger = logging.getLogger(__name__)
        
        # 获取 Tableau 配置
        from tableau_assistant.src.infra.config.settings import settings
        
        try:
            tableau_config = settings.get_tableau_config()
            domain = tableau_config.domain
        except Exception:
            logger.debug("未配置 Tableau 环境，跳过证书自动配置")
            return
        
        if not domain:
            logger.debug("未配置 Tableau 环境，跳过证书自动配置")
            return
        
        from tableau_assistant.src.infra.certs import CertificateManager
        from urllib.parse import urlparse
        
        # 初始化证书管理器
        manager = CertificateManager()
        
        # Tableau Cloud 使用系统证书，无需处理
        if "online.tableau.com" in domain.lower():
            logger.info(f"检测到 Tableau Cloud: {domain}，使用系统证书库")
            return
        
        # 内部 Tableau Server，使用证书管理器
        logger.info(f"检测到内部 Tableau Server: {domain}")
        
        # 解析域名
        parsed = urlparse(domain)
        hostname = parsed.hostname or parsed.path.split('/')[0]
        
        # 获取 Tableau 证书
        try:
            result = manager.fetch_and_save_certificates(hostname, force=False)
            
            if "server_cert" in result:
                cert_file = result["server_cert"]
                logger.info(f"✅ 证书已配置: {cert_file}")
                
                # 设置环境变量（运行时生效）
                os.environ["VIZQL_CA_BUNDLE"] = cert_file
                os.environ["VIZQL_VERIFY_SSL"] = "true"
        except Exception as e:
            logger.warning(f"Tableau 证书获取失败 ({hostname}): {e}")
        
    except Exception as e:
        # 静默失败，不影响应用启动
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"证书自动配置跳过: {e}")


# 在包导入时自动执行
_auto_setup_certificates()
