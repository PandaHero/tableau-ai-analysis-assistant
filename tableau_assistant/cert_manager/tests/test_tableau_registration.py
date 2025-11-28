"""
Tests for Tableau service registration helper
"""
import pytest
import os
import tempfile
from pathlib import Path

from tableau_assistant.cert_manager import CertificateManager
from tableau_assistant.cert_manager.preconfig import register_tableau_service


class TestTableauRegistration:
    """Tests for Tableau service registration"""
    
    def test_register_tableau_with_explicit_hostname(self):
        """Test registering Tableau with explicit hostname"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = CertificateManager(cert_dir=temp_dir)
            
            result = manager.register_tableau_service(
                hostname="tableau.example.com",
                fetch_on_register=False
            )
            
            assert result['status'] == 'registered'
            assert result['hostname'] == 'tableau.example.com'
            assert result['port'] == 443
            assert 'tableau_' in result['ca_bundle']
    
    def test_register_tableau_with_env_var(self):
        """Test registering Tableau using environment variable"""
        os.environ['TABLEAU_DOMAIN'] = 'cpse.cpgroup.cn'
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                manager = CertificateManager(cert_dir=temp_dir)
                
                result = manager.register_tableau_service(fetch_on_register=False)
                
                assert result['status'] == 'registered'
                assert result['hostname'] == 'cpse.cpgroup.cn'
        finally:
            del os.environ['TABLEAU_DOMAIN']
    
    def test_register_tableau_with_url(self):
        """Test registering Tableau with full URL"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = CertificateManager(cert_dir=temp_dir)
            
            result = manager.register_tableau_service(
                hostname="https://tableau.example.com:8443",
                fetch_on_register=False
            )
            
            assert result['status'] == 'registered'
            assert result['hostname'] == 'tableau.example.com'
            assert result['port'] == 8443
    
    def test_register_tableau_without_hostname_fails(self):
        """Test that registration fails without hostname"""
        # Ensure TABLEAU_DOMAIN is not set
        if 'TABLEAU_DOMAIN' in os.environ:
            del os.environ['TABLEAU_DOMAIN']
        
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = CertificateManager(cert_dir=temp_dir)
            
            with pytest.raises(ValueError, match="Tableau hostname not provided"):
                register_tableau_service(manager)
    
    def test_register_tableau_with_custom_ca_bundle(self):
        """Test registering Tableau with custom CA bundle"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = CertificateManager(cert_dir=temp_dir)
            
            result = manager.register_tableau_service(
                hostname="tableau.example.com",
                ca_bundle="custom_tableau.pem",
                fetch_on_register=False
            )
            
            assert result['status'] == 'registered'
            assert result['ca_bundle'] == 'custom_tableau.pem'
    
    def test_tableau_service_is_retrievable(self):
        """Test that registered Tableau service can be retrieved"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = CertificateManager(cert_dir=temp_dir)
            
            manager.register_tableau_service(
                hostname="tableau.example.com",
                fetch_on_register=False
            )
            
            # Should be able to get service config
            registry = manager._init_service_registry()
            config = registry.get_service_config("tableau")
            
            assert config.service_id == "tableau"
            assert config.hostname == "tableau.example.com"
            assert config.port == 443
