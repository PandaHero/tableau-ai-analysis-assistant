"""
Application Certificate Provider Module

Manages certificates for the application's own HTTPS servers.
"""
from typing import Tuple, Optional
from pathlib import Path
import logging
from datetime import datetime, timedelta

from .models import ApplicationCertConfig
from .validator import CertificateValidator

logger = logging.getLogger(__name__)


class ApplicationCertificateProvider:
    """
    Provider for application HTTPS certificates
    
    This class manages SSL certificates for the application's own frontend
    and backend servers, supporting both self-signed and company-issued certificates.
    
    Usage:
        provider = ApplicationCertificateProvider(cert_dir="certs")
        cert_file, key_file = provider.get_server_certificate()
    """
    
    def __init__(
        self,
        cert_dir: str = "tableau_assistant/certs",
        config: Optional[ApplicationCertConfig] = None,
        warning_days: int = 30
    ):
        """
        Initialize the application certificate provider
        
        Args:
            cert_dir: Directory to store certificates
            config: Application certificate configuration
            warning_days: Days before expiration to start warning
        """
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        # Default configuration if not provided
        if config is None:
            config = ApplicationCertConfig(
                source="self-signed",
                cert_file="app_server.pem",
                key_file="app_server_key.pem",
                ca_bundle="app_ca.pem",
                common_name="localhost",
                validity_days=365
            )
        
        self.config = config
        self.validator = CertificateValidator(warning_days=warning_days)
        
        logger.info(
            f"ApplicationCertificateProvider initialized with source: {config.source}"
        )
    
    def get_server_certificate(self) -> Tuple[str, str]:
        """
        Get server certificate and private key paths
        
        Returns:
            Tuple of (cert_file_path, key_file_path)
            
        Raises:
            FileNotFoundError: If certificate files don't exist
        """
        cert_file = self.config.get_active_cert_file()
        key_file = self.config.get_active_key_file()
        
        # Convert to absolute paths
        cert_path = self._resolve_path(cert_file)
        key_path = self._resolve_path(key_file)
        
        # Check if files exist
        if not cert_path.exists():
            raise FileNotFoundError(
                f"Certificate file not found: {cert_path}. "
                f"Run generate_self_signed() to create certificates."
            )
        
        if not key_path.exists():
            raise FileNotFoundError(
                f"Private key file not found: {key_path}. "
                f"Run generate_self_signed() to create certificates."
            )
        
        return str(cert_path), str(key_path)
    
    def get_ca_bundle(self) -> str:
        """
        Get CA bundle for client trust
        
        Returns:
            Path to CA bundle file
            
        Raises:
            FileNotFoundError: If CA bundle doesn't exist
        """
        ca_bundle = self.config.get_active_ca_bundle()
        
        if not ca_bundle:
            raise ValueError("No CA bundle configured")
        
        ca_path = self._resolve_path(ca_bundle)
        
        if not ca_path.exists():
            raise FileNotFoundError(f"CA bundle not found: {ca_path}")
        
        return str(ca_path)
    
    def generate_self_signed(
        self,
        common_name: Optional[str] = None,
        validity_days: Optional[int] = None
    ) -> Tuple[str, str]:
        """
        Generate self-signed certificate
        
        Args:
            common_name: Common name for the certificate (default: from config)
            validity_days: Validity period in days (default: from config)
            
        Returns:
            Tuple of (cert_file_path, key_file_path)
        """
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        
        # Use config values if not provided
        cn = common_name or self.config.common_name
        days = validity_days or self.config.validity_days
        
        logger.info(f"Generating self-signed certificate for {cn}")
        
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        
        # Generate certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Tableau Assistant"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=days)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(cn),
                x509.DNSName("localhost"),
                x509.IPAddress("127.0.0.1"),
            ]),
            critical=False,
        ).sign(private_key, hashes.SHA256())
        
        # Save certificate
        cert_path = self._resolve_path(self.config.cert_file)
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        logger.info(f"Certificate saved to: {cert_path}")
        
        # Save private key
        key_path = self._resolve_path(self.config.key_file)
        with open(key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        logger.info(f"Private key saved to: {key_path}")
        
        # Also save as CA bundle (for self-signed, cert is its own CA)
        if self.config.ca_bundle:
            ca_path = self._resolve_path(self.config.ca_bundle)
            with open(ca_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            logger.info(f"CA bundle saved to: {ca_path}")
        
        # Validate the generated certificate
        validation_result = self.validator.validate_certificate_file(str(cert_path))
        if not validation_result["valid"]:
            logger.error(f"Generated certificate is invalid: {validation_result['errors']}")
            raise ValueError(f"Certificate validation failed: {validation_result['errors']}")
        
        logger.info("Self-signed certificate generated and validated successfully")
        
        return str(cert_path), str(key_path)
    
    def load_company_certificate(
        self,
        cert_file: str,
        key_file: str,
        ca_bundle: Optional[str] = None
    ) -> None:
        """
        Load company-issued certificate
        
        Args:
            cert_file: Path to company certificate file
            key_file: Path to company private key file
            ca_bundle: Path to company CA bundle (optional)
            
        Raises:
            FileNotFoundError: If certificate files don't exist
            ValueError: If certificate validation fails
        """
        logger.info("Loading company-issued certificate")
        
        # Validate certificate file exists
        cert_path = Path(cert_file)
        if not cert_path.exists():
            raise FileNotFoundError(f"Company certificate not found: {cert_file}")
        
        # Validate key file exists
        key_path = Path(key_file)
        if not key_path.exists():
            raise FileNotFoundError(f"Company private key not found: {key_file}")
        
        # Validate CA bundle if provided
        if ca_bundle:
            ca_path = Path(ca_bundle)
            if not ca_path.exists():
                raise FileNotFoundError(f"Company CA bundle not found: {ca_bundle}")
        
        # Validate the certificate
        validation_result = self.validator.validate_certificate_file(cert_file)
        if not validation_result["valid"]:
            raise ValueError(
                f"Company certificate validation failed: {validation_result['errors']}"
            )
        
        # Update configuration
        self.config.company_cert_file = cert_file
        self.config.company_key_file = key_file
        self.config.company_ca_bundle = ca_bundle
        self.config.source = "company"
        
        logger.info("Company certificate loaded and validated successfully")
    
    def get_certificate_source(self) -> str:
        """
        Get current certificate source
        
        Returns:
            "self-signed" or "company"
        """
        return self.config.source
    
    def switch_to_self_signed(self) -> None:
        """Switch to using self-signed certificates"""
        logger.info("Switching to self-signed certificates")
        self.config.source = "self-signed"
    
    def switch_to_company(self) -> None:
        """
        Switch to using company certificates
        
        Raises:
            ValueError: If company certificates are not configured
        """
        if not self.config.company_cert_file:
            raise ValueError(
                "Company certificates not configured. "
                "Call load_company_certificate() first."
            )
        
        logger.info("Switching to company certificates")
        self.config.source = "company"
    
    def _resolve_path(self, path: str) -> Path:
        """
        Resolve a path relative to cert_dir
        
        Args:
            path: File path (relative or absolute)
            
        Returns:
            Absolute Path object
        """
        p = Path(path)
        if p.is_absolute():
            return p
        return self.cert_dir / p
    
    def get_status(self) -> dict:
        """
        Get status of application certificates
        
        Returns:
            Dictionary with certificate status
        """
        status = {
            "source": self.config.source,
            "cert_dir": str(self.cert_dir),
            "certificates": {}
        }
        
        # Check self-signed certificates
        cert_path = self._resolve_path(self.config.cert_file)
        key_path = self._resolve_path(self.config.key_file)
        
        status["certificates"]["self_signed"] = {
            "cert_file": str(cert_path),
            "key_file": str(key_path),
            "cert_exists": cert_path.exists(),
            "key_exists": key_path.exists(),
        }
        
        if cert_path.exists():
            validation = self.validator.validate_certificate_file(str(cert_path))
            status["certificates"]["self_signed"]["valid"] = validation["valid"]
            status["certificates"]["self_signed"]["errors"] = validation.get("errors", [])
        
        # Check company certificates
        if self.config.company_cert_file:
            company_cert_path = Path(self.config.company_cert_file)
            company_key_path = Path(self.config.company_key_file)
            
            status["certificates"]["company"] = {
                "cert_file": str(company_cert_path),
                "key_file": str(company_key_path),
                "cert_exists": company_cert_path.exists(),
                "key_exists": company_key_path.exists(),
            }
            
            if company_cert_path.exists():
                validation = self.validator.validate_certificate_file(str(company_cert_path))
                status["certificates"]["company"]["valid"] = validation["valid"]
                status["certificates"]["company"]["errors"] = validation.get("errors", [])
        
        return status
    
    def __repr__(self) -> str:
        """String representation"""
        return f"ApplicationCertificateProvider(source='{self.config.source}')"
