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
    
    使用增强的证书管理器，支持：
    - 配置文件加载
    - 多服务证书管理
    - 环境变量配置
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
        
        # 从 settings 读取 Tableau 域名
        from tableau_assistant.src.config.settings import settings
        tableau_domain = settings.tableau_domain
        if not tableau_domain:
            logger.debug("TABLEAU_DOMAIN 未设置，跳过证书自动配置")
            return
        
        # Tableau Cloud 使用系统证书，无需处理
        if "online.tableau.com" in tableau_domain.lower():
            logger.info("检测到 Tableau Cloud，使用系统证书库")
            return
        
        # 内部 Tableau Server，使用增强的证书管理器
        logger.info(f"检测到内部 Tableau Server: {tableau_domain}")
        
        from tableau_assistant.cert_manager import CertificateManager
        from tableau_assistant.cert_manager.config_parser import ConfigurationParser
        
        # 检查是否有配置文件
        config_file = Path("cert_config.yaml")
        config = None
        
        if config_file.exists():
            try:
                parser = ConfigurationParser()
                config = parser.load_config_with_precedence(
                    config_file=str(config_file),
                    env_config=parser.extract_env_config()
                )
                logger.info("✅ 已加载证书配置文件")
            except Exception as e:
                logger.warning(f"配置文件加载失败，使用默认配置: {e}")
        
        # 初始化证书管理器
        manager = CertificateManager()
        
        # 注册预配置的服务（DeepSeek, Zhipu AI）
        try:
            results = manager.register_preconfigured_services(["deepseek", "zhipu-ai"])
            for service_id, result in results.items():
                if result["status"] == "registered":
                    logger.info(f"✅ {service_id} 服务已注册")
        except Exception as e:
            logger.debug(f"预配置服务注册跳过: {e}")
        
        # 注册 Tableau 服务（使用新的助手方法）
        try:
            result = manager.register_tableau_service(fetch_on_register=False)
            if result["status"] == "registered":
                logger.info(f"✅ Tableau 服务已注册: {result['hostname']}")
        except Exception as e:
            logger.warning(f"Tableau 服务注册失败: {e}")
            # 回退到旧方法
            result = manager.fetch_tableau_certificates(
                tableau_domain=tableau_domain,
                force=False
            )
        
        # 获取 Tableau 证书
        if "server_cert" in result:
            cert_file = result["server_cert"]
            status = result.get("status", "unknown")
            
            if status == "existing":
                logger.info(f"✅ 使用现有证书: {cert_file}")
            else:
                logger.info(f"✅ 证书已自动获取: {cert_file}")
            
            # 设置环境变量（运行时生效）
            os.environ["LLM_CA_BUNDLE"] = cert_file
            os.environ["LLM_VERIFY_SSL"] = "true"
        
    except Exception as e:
        # 静默失败，不影响应用启动
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"证书自动配置跳过: {e}")


# 在包导入时自动执行
_auto_setup_certificates()
