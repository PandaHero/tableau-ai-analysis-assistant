"""
证书数据模型

定义证书管理中使用的数据结构。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class CertificateInfo:
    """证书信息"""
    subject: str
    issuer: str
    not_before: datetime
    not_after: datetime
    serial_number: str
    fingerprint: Optional[str] = None
    
    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.not_after
    
    @property
    def days_until_expiry(self) -> int:
        return (self.not_after - datetime.now()).days


@dataclass
class CertificateChain:
    """证书链"""
    certificates: List[CertificateInfo] = field(default_factory=list)
    pem_content: str = ""
    
    @property
    def is_valid(self) -> bool:
        return len(self.certificates) > 0 and all(
            not cert.is_expired for cert in self.certificates
        )


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cert_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "CertificateInfo",
    "CertificateChain",
    "ValidationResult",
]
