"""
Data models for certificate management

This module defines the data structures used throughout the certificate manager.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List


@dataclass
class ServiceConfig:
    """
    Configuration for a third-party service
    
    This dataclass stores all configuration needed to manage certificates
    for a third-party API service (e.g., DeepSeek, Zhipu AI, Tableau).
    
    Attributes:
        service_id: Unique identifier for the service
        hostname: Server hostname (e.g., "api.deepseek.com")
        port: Server port (default: 443)
        ca_bundle: Path to CA bundle file for this service
        auto_fetch: Whether to automatically fetch certificates on registration
        last_fetched: Timestamp of last certificate fetch
        last_validated: Timestamp of last certificate validation
        validation_status: Current validation status ("valid", "expired", "invalid", "unknown")
    """
    service_id: str
    hostname: str
    port: int = 443
    ca_bundle: Optional[str] = None
    auto_fetch: bool = True
    last_fetched: Optional[datetime] = None
    last_validated: Optional[datetime] = None
    validation_status: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary
        
        Returns:
            Dictionary representation with datetime objects converted to ISO format
        """
        data = asdict(self)
        
        # Convert datetime objects to ISO format strings
        if self.last_fetched:
            data['last_fetched'] = self.last_fetched.isoformat()
        if self.last_validated:
            data['last_validated'] = self.last_validated.isoformat()
            
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceConfig":
        """
        Create from dictionary
        
        Args:
            data: Dictionary with service configuration
            
        Returns:
            ServiceConfig instance
        """
        # Create a copy to avoid modifying the input
        data = data.copy()
        
        # Convert ISO format strings back to datetime objects
        if 'last_fetched' in data and data['last_fetched']:
            if isinstance(data['last_fetched'], str):
                data['last_fetched'] = datetime.fromisoformat(data['last_fetched'])
        
        if 'last_validated' in data and data['last_validated']:
            if isinstance(data['last_validated'], str):
                data['last_validated'] = datetime.fromisoformat(data['last_validated'])
        
        return cls(**data)
    
    def __repr__(self) -> str:
        """String representation"""
        return (
            f"ServiceConfig(service_id='{self.service_id}', "
            f"hostname='{self.hostname}', port={self.port}, "
            f"status='{self.validation_status}')"
        )


@dataclass
class ApplicationCertConfig:
    """
    Configuration for application certificates
    
    This dataclass manages configuration for the application's own HTTPS certificates,
    supporting both self-signed and company-issued certificates.
    
    Attributes:
        source: Certificate source ("self-signed" or "company")
        cert_file: Path to certificate file (for self-signed)
        key_file: Path to private key file (for self-signed)
        ca_bundle: Path to CA bundle (optional)
        common_name: Common name for self-signed certificates
        validity_days: Validity period for self-signed certificates
        company_cert_file: Path to company certificate file
        company_key_file: Path to company private key file
        company_ca_bundle: Path to company CA bundle
    """
    source: str  # "self-signed" or "company"
    cert_file: str
    key_file: str
    ca_bundle: Optional[str] = None
    common_name: str = "localhost"
    validity_days: int = 365
    
    # Company certificate paths (when source == "company")
    company_cert_file: Optional[str] = None
    company_key_file: Optional[str] = None
    company_ca_bundle: Optional[str] = None
    
    def get_active_cert_file(self) -> str:
        """
        Get the active certificate file based on source
        
        Returns:
            Path to the active certificate file
        """
        if self.source == "company" and self.company_cert_file:
            return self.company_cert_file
        return self.cert_file
    
    def get_active_key_file(self) -> str:
        """
        Get the active key file based on source
        
        Returns:
            Path to the active private key file
        """
        if self.source == "company" and self.company_key_file:
            return self.company_key_file
        return self.key_file
    
    def get_active_ca_bundle(self) -> Optional[str]:
        """
        Get the active CA bundle based on source
        
        Returns:
            Path to the active CA bundle, or None if not configured
        """
        if self.source == "company" and self.company_ca_bundle:
            return self.company_ca_bundle
        return self.ca_bundle
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary
        
        Returns:
            Dictionary representation
        """
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApplicationCertConfig":
        """
        Create from dictionary
        
        Args:
            data: Dictionary with application certificate configuration
            
        Returns:
            ApplicationCertConfig instance
        """
        return cls(**data)
    
    def __repr__(self) -> str:
        """String representation"""
        return (
            f"ApplicationCertConfig(source='{self.source}', "
            f"cert_file='{self.get_active_cert_file()}')"
        )


@dataclass
class CertificateMetadata:
    """
    Metadata for a certificate
    
    This dataclass stores metadata about a certificate including its validation
    status, expiration information, and any errors encountered.
    
    Attributes:
        file_path: Path to the certificate file
        cert_type: Type of certificate ("service", "application", "ca_bundle")
        service_id: Associated service ID (for service certificates)
        created_at: Certificate creation timestamp
        expires_at: Certificate expiration timestamp
        issuer: Certificate issuer
        subject: Certificate subject
        is_valid: Whether the certificate is currently valid
        validation_errors: List of validation errors
    """
    file_path: str
    cert_type: str  # "service", "application", "ca_bundle"
    service_id: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    issuer: Optional[str] = None
    subject: Optional[str] = None
    is_valid: bool = False
    validation_errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary
        
        Returns:
            Dictionary representation with datetime objects converted to ISO format
        """
        data = asdict(self)
        
        # Convert datetime objects to ISO format strings
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.expires_at:
            data['expires_at'] = self.expires_at.isoformat()
            
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CertificateMetadata":
        """
        Create from dictionary
        
        Args:
            data: Dictionary with certificate metadata
            
        Returns:
            CertificateMetadata instance
        """
        # Create a copy to avoid modifying the input
        data = data.copy()
        
        # Convert ISO format strings back to datetime objects
        if 'created_at' in data and data['created_at']:
            if isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'])
        
        if 'expires_at' in data and data['expires_at']:
            if isinstance(data['expires_at'], str):
                data['expires_at'] = datetime.fromisoformat(data['expires_at'])
        
        return cls(**data)
    
    def __repr__(self) -> str:
        """String representation"""
        status = "valid" if self.is_valid else "invalid"
        return (
            f"CertificateMetadata(file_path='{self.file_path}', "
            f"type='{self.cert_type}', status='{status}')"
        )
