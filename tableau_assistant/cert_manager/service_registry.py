"""
Service Registry Module

Manages certificates for multiple third-party API services.
"""
from typing import Dict, List, Optional, Any
from pathlib import Path
import logging
from datetime import datetime, timezone

from .models import ServiceConfig
from .fetcher import CertificateFetcher
from .validator import CertificateValidator

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """
    Registry for third-party service certificates
    
    This class manages SSL certificates for multiple external API services,
    providing a centralized way to register, fetch, and validate service certificates.
    
    Usage:
        registry = ServiceRegistry(cert_dir="certs")
        registry.register_service("deepseek", "api.deepseek.com")
        config = registry.get_service_config("deepseek")
    """
    
    def __init__(
        self,
        cert_dir: str = "tableau_assistant/certs",
        timeout: int = 10,
        warning_days: int = 30
    ):
        """
        Initialize the service registry
        
        Args:
            cert_dir: Directory to store certificates
            timeout: Network timeout for certificate fetching
            warning_days: Days before expiration to start warning
        """
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        # Storage for registered services
        self._services: Dict[str, ServiceConfig] = {}
        
        # Initialize components
        self.fetcher = CertificateFetcher(timeout=timeout)
        self.validator = CertificateValidator(warning_days=warning_days)
        
        logger.info(f"ServiceRegistry initialized with cert_dir: {self.cert_dir}")
    
    def register_service(
        self,
        service_id: str,
        hostname: str,
        port: int = 443,
        ca_bundle: Optional[str] = None,
        fetch_on_register: bool = True
    ) -> None:
        """
        Register a new service
        
        Args:
            service_id: Unique identifier for the service (e.g., "deepseek", "zhipu-ai")
            hostname: Server hostname (e.g., "api.deepseek.com")
            port: Server port (default: 443)
            ca_bundle: Path to CA bundle file (relative to cert_dir or absolute)
            fetch_on_register: Whether to fetch certificate immediately
            
        Raises:
            ValueError: If service_id is already registered
        """
        if service_id in self._services:
            logger.warning(f"Service '{service_id}' is already registered, updating configuration")
        
        # Create service configuration
        config = ServiceConfig(
            service_id=service_id,
            hostname=hostname,
            port=port,
            ca_bundle=ca_bundle,
            auto_fetch=fetch_on_register
        )
        
        # Store the service
        self._services[service_id] = config
        logger.info(f"Registered service: {service_id} ({hostname}:{port})")
        
        # Fetch certificate if requested
        if fetch_on_register:
            try:
                self.fetch_service_certificate(service_id, force=False)
            except Exception as e:
                logger.error(f"Failed to fetch certificate for {service_id}: {e}")
                # Don't raise - allow registration to succeed even if fetch fails
    
    def get_service_config(self, service_id: str) -> ServiceConfig:
        """
        Get SSL configuration for a service
        
        Args:
            service_id: Service identifier
            
        Returns:
            ServiceConfig for the service
            
        Raises:
            KeyError: If service is not registered
        """
        if service_id not in self._services:
            raise KeyError(
                f"Service '{service_id}' is not registered. "
                f"Available services: {', '.join(self.list_services())}"
            )
        
        return self._services[service_id]
    
    def fetch_service_certificate(
        self,
        service_id: str,
        force: bool = False
    ) -> Dict[str, str]:
        """
        Fetch certificate for a service
        
        Args:
            service_id: Service identifier
            force: Force re-fetch even if certificate exists
            
        Returns:
            Dictionary with certificate file paths
            
        Raises:
            KeyError: If service is not registered
        """
        config = self.get_service_config(service_id)
        
        # Determine certificate file path
        if config.ca_bundle:
            # Use configured path (may be relative or absolute)
            cert_path = Path(config.ca_bundle)
            if not cert_path.is_absolute():
                cert_path = self.cert_dir / cert_path
        else:
            # Generate default path
            safe_hostname = config.hostname.replace('.', '_')
            cert_path = self.cert_dir / f"{service_id}_{safe_hostname}_cert.pem"
        
        # Check if certificate already exists and is valid
        if cert_path.exists() and not force:
            logger.info(f"Certificate for {service_id} already exists, validating...")
            validation_result = self.validator.validate_certificate_file(str(cert_path))
            
            if validation_result["valid"]:
                logger.info(f"Existing certificate for {service_id} is valid")
                
                # Update service config
                config.last_validated = datetime.now(timezone.utc)
                config.validation_status = "valid"
                
                return {
                    "service_id": service_id,
                    "cert_file": str(cert_path),
                    "status": "existing"
                }
            else:
                logger.warning(
                    f"Existing certificate for {service_id} is invalid: "
                    f"{validation_result['errors']}"
                )
        
        # Fetch certificate from server
        logger.info(f"Fetching certificate for {service_id} from {config.hostname}:{config.port}")
        
        try:
            cert_info, cert_pem = self.fetcher.fetch_server_certificate(
                config.hostname,
                config.port,
                str(cert_path)
            )
            
            # Validate the fetched certificate
            validation_result = self.validator.validate_certificate_file(str(cert_path))
            
            if not validation_result["valid"]:
                logger.error(
                    f"Fetched certificate for {service_id} is invalid: "
                    f"{validation_result['errors']}"
                )
                config.validation_status = "invalid"
                raise ValueError(f"Certificate validation failed: {validation_result['errors']}")
            
            # Update service config
            config.ca_bundle = str(cert_path)
            config.last_fetched = datetime.now(timezone.utc)
            config.last_validated = datetime.now(timezone.utc)
            config.validation_status = "valid"
            
            logger.info(f"Successfully fetched and validated certificate for {service_id}")
            
            return {
                "service_id": service_id,
                "cert_file": str(cert_path),
                "cert_info": cert_info,
                "status": "fetched"
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch certificate for {service_id}: {e}")
            config.validation_status = "invalid"
            raise
    
    def list_services(self) -> List[str]:
        """
        List all registered services
        
        Returns:
            List of service IDs
        """
        return list(self._services.keys())
    
    def validate_service(self, service_id: str) -> Dict[str, Any]:
        """
        Validate service certificate
        
        Args:
            service_id: Service identifier
            
        Returns:
            Validation result dictionary
            
        Raises:
            KeyError: If service is not registered
        """
        config = self.get_service_config(service_id)
        
        if not config.ca_bundle:
            return {
                "valid": False,
                "service_id": service_id,
                "errors": ["No certificate configured for this service"]
            }
        
        # Validate the certificate file
        cert_path = Path(config.ca_bundle)
        if not cert_path.is_absolute():
            cert_path = self.cert_dir / cert_path
        
        validation_result = self.validator.validate_certificate_file(str(cert_path))
        
        # Update service config
        config.last_validated = datetime.now(timezone.utc)
        config.validation_status = "valid" if validation_result["valid"] else "invalid"
        
        # Add service_id to result
        validation_result["service_id"] = service_id
        validation_result["hostname"] = config.hostname
        validation_result["port"] = config.port
        
        return validation_result
    
    def get_service_ca_bundle(self, service_id: str) -> Optional[str]:
        """
        Get the CA bundle path for a service
        
        Args:
            service_id: Service identifier
            
        Returns:
            Absolute path to CA bundle, or None if not configured
            
        Raises:
            KeyError: If service is not registered
        """
        config = self.get_service_config(service_id)
        
        if not config.ca_bundle:
            return None
        
        cert_path = Path(config.ca_bundle)
        if not cert_path.is_absolute():
            cert_path = self.cert_dir / cert_path
        
        return str(cert_path) if cert_path.exists() else None
    
    def unregister_service(self, service_id: str) -> None:
        """
        Unregister a service
        
        Args:
            service_id: Service identifier
            
        Raises:
            KeyError: If service is not registered
        """
        if service_id not in self._services:
            raise KeyError(f"Service '{service_id}' is not registered")
        
        del self._services[service_id]
        logger.info(f"Unregistered service: {service_id}")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all registered services
        
        Returns:
            Dictionary with service statuses
        """
        status = {
            "cert_dir": str(self.cert_dir),
            "service_count": len(self._services),
            "services": {}
        }
        
        for service_id, config in self._services.items():
            service_status = {
                "hostname": config.hostname,
                "port": config.port,
                "ca_bundle": config.ca_bundle,
                "validation_status": config.validation_status,
                "last_fetched": config.last_fetched.isoformat() if config.last_fetched else None,
                "last_validated": config.last_validated.isoformat() if config.last_validated else None,
            }
            
            # Check if certificate file exists
            if config.ca_bundle:
                cert_path = Path(config.ca_bundle)
                if not cert_path.is_absolute():
                    cert_path = self.cert_dir / cert_path
                service_status["cert_exists"] = cert_path.exists()
            else:
                service_status["cert_exists"] = False
            
            status["services"][service_id] = service_status
        
        return status
    
    def __repr__(self) -> str:
        """String representation"""
        return f"ServiceRegistry(services={len(self._services)}, cert_dir='{self.cert_dir}')"
