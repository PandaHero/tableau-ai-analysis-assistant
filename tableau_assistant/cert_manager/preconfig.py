"""
Pre-configured Services Module

Provides default configurations for common third-party services.
"""
from typing import Dict, Any
import os


def _get_tableau_hostname() -> str:
    """从 settings 获取 Tableau 域名"""
    from tableau_assistant.src.config.settings import settings
    return settings.tableau_domain or "tableau.company.com"


# Pre-configured service definitions
PRECONFIGURED_SERVICES = {
    "deepseek": {
        "hostname": "api.deepseek.com",
        "port": 443,
        "ca_bundle": "deepseek_full_chain.pem",
        "auto_fetch": True,
        "description": "DeepSeek AI API"
    },
    "zhipu-ai": {
        "hostname": "open.bigmodel.cn",
        "port": 443,
        "ca_bundle": "zhipu_full_chain.pem",
        "auto_fetch": True,
        "description": "Zhipu AI (智谱 AI) API"
    },
    "tableau": {
        "hostname": None,  # 动态获取
        "port": 443,
        "ca_bundle": "tableau_cert.pem",
        "auto_fetch": False,  # Manually managed
        "description": "Tableau Server"
    }
}


def register_preconfigured_services(certificate_manager) -> Dict[str, Any]:
    """
    Register all pre-configured services with the certificate manager
    
    Args:
        certificate_manager: CertificateManager instance
        
    Returns:
        Dictionary with registration results
    """
    results = {}
    
    for service_id, config in PRECONFIGURED_SERVICES.items():
        try:
            # Handle dynamic hostname for tableau
            hostname = config["hostname"]
            if service_id == "tableau":
                hostname = _get_tableau_hostname()
                if not hostname or hostname == "tableau.company.com":
                    results[service_id] = {
                        "status": "skipped",
                        "reason": "TABLEAU_DOMAIN not configured"
                    }
                    continue
            
            certificate_manager.register_service(
                service_id=service_id,
                hostname=hostname,
                port=config["port"],
                ca_bundle=config["ca_bundle"],
                fetch_on_register=config["auto_fetch"]
            )
            
            results[service_id] = {
                "status": "registered",
                "hostname": hostname,
                "port": config["port"]
            }
            
        except Exception as e:
            results[service_id] = {
                "status": "failed",
                "error": str(e)
            }
    
    return results


def get_service_info(service_id: str) -> Dict[str, Any]:
    """
    Get information about a pre-configured service
    
    Args:
        service_id: Service identifier
        
    Returns:
        Service configuration dictionary
        
    Raises:
        KeyError: If service is not pre-configured
    """
    if service_id not in PRECONFIGURED_SERVICES:
        raise KeyError(
            f"Service '{service_id}' is not pre-configured. "
            f"Available services: {', '.join(PRECONFIGURED_SERVICES.keys())}"
        )
    
    return PRECONFIGURED_SERVICES[service_id].copy()


def list_preconfigured_services() -> list:
    """
    List all pre-configured service IDs
    
    Returns:
        List of service IDs
    """
    return list(PRECONFIGURED_SERVICES.keys())


def register_tableau_service(
    certificate_manager,
    hostname: str = None,
    port: int = 443,
    ca_bundle: str = None,
    fetch_on_register: bool = False
) -> Dict[str, Any]:
    """
    Register Tableau Server service with dynamic hostname support
    
    This is a helper method specifically for Tableau Server registration,
    which supports dynamic hostname from environment variables or parameters.
    
    Args:
        certificate_manager: CertificateManager instance
        hostname: Tableau Server hostname (if None, reads from TABLEAU_DOMAIN env var)
        port: Tableau Server port (default: 443)
        ca_bundle: CA bundle filename (default: "tableau_cert.pem")
        fetch_on_register: Whether to fetch certificate immediately (default: False)
        
    Returns:
        Registration result dictionary
        
    Raises:
        ValueError: If hostname is not provided and TABLEAU_DOMAIN is not set
        
    Example:
        # Using settings (recommended)
        result = register_tableau_service(manager)
        
        # Using explicit hostname
        result = register_tableau_service(manager, hostname='cpse.cpgroup.cn')
    """
    # Determine hostname
    if hostname is None:
        hostname = _get_tableau_hostname()
        if not hostname or hostname == "tableau.company.com":
            raise ValueError(
                "Tableau hostname not provided. "
                "Either pass 'hostname' parameter or configure TABLEAU_DOMAIN in .env"
            )
    
    # Parse hostname if it's a full URL
    if hostname.startswith(('http://', 'https://')):
        from urllib.parse import urlparse
        parsed = urlparse(hostname)
        hostname = parsed.hostname or parsed.path.split('/')[0]
        if parsed.port:
            port = parsed.port
    
    # Determine CA bundle filename
    if ca_bundle is None:
        # Generate safe filename from hostname
        safe_hostname = hostname.replace('.', '_').replace(':', '_')
        ca_bundle = f"tableau_{safe_hostname}_cert.pem"
    
    try:
        # Register the service
        certificate_manager.register_service(
            service_id="tableau",
            hostname=hostname,
            port=port,
            ca_bundle=ca_bundle,
            fetch_on_register=fetch_on_register
        )
        
        return {
            "status": "registered",
            "service_id": "tableau",
            "hostname": hostname,
            "port": port,
            "ca_bundle": ca_bundle
        }
        
    except Exception as e:
        return {
            "status": "failed",
            "service_id": "tableau",
            "error": str(e)
        }
