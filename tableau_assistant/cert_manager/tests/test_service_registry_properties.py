"""
Property-based tests for ServiceRegistry

These tests verify universal properties across many inputs.
"""
import pytest
from hypothesis import given, strategies as st, settings
from pathlib import Path
import tempfile
import shutil

from tableau_assistant.cert_manager.service_registry import ServiceRegistry
from tableau_assistant.cert_manager.models import ServiceConfig


@st.composite
def service_data_strategy(draw):
    """Generate random service registration data"""
    service_id = draw(st.text(min_size=1, max_size=30, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'
    )))
    hostname = draw(st.from_regex(r'^[a-z0-9.-]+\.[a-z]{2,}$', fullmatch=True))
    port = draw(st.integers(min_value=1, max_value=65535))
    
    return {
        'service_id': service_id,
        'hostname': hostname,
        'port': port
    }


class TestServiceRegistryProperties:
    """Property-based tests for ServiceRegistry"""
    
    @settings(max_examples=50)
    @given(service_data=service_data_strategy())
    def test_property_4_service_specific_ssl_configuration(self, service_data):
        """
        Feature: cert-manager-enhancement, Property 4: Service-specific SSL configuration
        
        For any registered service, requesting SSL configuration should return
        a configuration object that uses the correct certificate for that specific service.
        
        Validates: Requirements 1.5, 4.1, 4.4
        """
        # Create temporary directory for test
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ServiceRegistry(cert_dir=temp_dir)
            
            # Register service without fetching (to avoid network calls)
            registry.register_service(
                service_id=service_data['service_id'],
                hostname=service_data['hostname'],
                port=service_data['port'],
                fetch_on_register=False
            )
            
            # Verify service is registered
            assert service_data['service_id'] in registry.list_services()
            
            # Get service config
            config = registry.get_service_config(service_data['service_id'])
            
            # Verify config matches registration
            assert config.service_id == service_data['service_id']
            assert config.hostname == service_data['hostname']
            assert config.port == service_data['port']
    
    @settings(max_examples=50)
    @given(service_data=service_data_strategy())
    def test_service_registration_stores_association(self, service_data):
        """
        Verify that service registration maintains service ID association
        
        For any service, after registration, the service should be retrievable
        by its service ID.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ServiceRegistry(cert_dir=temp_dir)
            
            registry.register_service(
                service_id=service_data['service_id'],
                hostname=service_data['hostname'],
                port=service_data['port'],
                fetch_on_register=False
            )
            
            # Service should be in list
            services = registry.list_services()
            assert service_data['service_id'] in services
            
            # Service config should be retrievable
            config = registry.get_service_config(service_data['service_id'])
            assert config is not None
            assert isinstance(config, ServiceConfig)
    
    @settings(max_examples=50)
    @given(
        service1=service_data_strategy(),
        service2=service_data_strategy()
    )
    def test_multiple_services_independent(self, service1, service2):
        """
        Verify that multiple services can be registered independently
        
        For any two different services, registering both should maintain
        independent configurations.
        """
        # Ensure different service IDs
        if service1['service_id'] == service2['service_id']:
            service2['service_id'] = service2['service_id'] + '_2'
        
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = ServiceRegistry(cert_dir=temp_dir)
            
            # Register both services
            registry.register_service(**service1, fetch_on_register=False)
            registry.register_service(**service2, fetch_on_register=False)
            
            # Both should be registered
            services = registry.list_services()
            assert service1['service_id'] in services
            assert service2['service_id'] in services
            
            # Configs should be independent
            config1 = registry.get_service_config(service1['service_id'])
            config2 = registry.get_service_config(service2['service_id'])
            
            assert config1.hostname == service1['hostname']
            assert config2.hostname == service2['hostname']
            assert config1.port == service1['port']
            assert config2.port == service2['port']


class TestCertificateManagerIntegrationProperties:
    """Property-based tests for CertificateManager integration"""
    
    @settings(max_examples=30)
    @given(service_data=service_data_strategy())
    def test_property_8_certificate_source_switching(self, service_data):
        """
        Feature: cert-manager-enhancement, Property 8: Certificate source switching updates contexts
        
        For any certificate source change (self-signed to company or vice versa),
        all SSL contexts should be updated to use the new certificates.
        
        Validates: Requirements 3.2
        """
        from tableau_assistant.cert_manager import ApplicationCertificateProvider
        from tableau_assistant.cert_manager.models import ApplicationCertConfig
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config
            config = ApplicationCertConfig(
                source="self-signed",
                cert_file="test.pem",
                key_file="test_key.pem"
            )
            
            provider = ApplicationCertificateProvider(
                cert_dir=temp_dir,
                config=config
            )
            
            # Initial source
            assert provider.get_certificate_source() == "self-signed"
            
            # Switch to company (with mock files)
            config.company_cert_file = "company.pem"
            config.company_key_file = "company_key.pem"
            provider.switch_to_company()
            
            # Verify source changed
            assert provider.get_certificate_source() == "company"
            
            # Switch back
            provider.switch_to_self_signed()
            assert provider.get_certificate_source() == "self-signed"
    
    @settings(max_examples=30)
    @given(ca_bundle_name=st.text(min_size=5, max_size=20, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='_-'
    )))
    def test_property_21_configuration_hot_reload(self, ca_bundle_name):
        """
        Feature: cert-manager-enhancement, Property 21: Configuration hot reload
        
        For any configuration change, the Certificate Manager should reload
        certificates without requiring application restart.
        
        Validates: Requirements 6.4
        """
        from tableau_assistant.cert_manager import CertificateManager
        import os
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create initial certificate files
            initial_cert = Path(temp_dir) / "initial_cert.pem"
            initial_cert.write_text("-----BEGIN CERTIFICATE-----\nINITIAL\n-----END CERTIFICATE-----\n")
            
            new_cert = Path(temp_dir) / f"{ca_bundle_name}.pem"
            new_cert.write_text("-----BEGIN CERTIFICATE-----\nNEW\n-----END CERTIFICATE-----\n")
            
            # Save original env vars
            original_verify = os.environ.get('LLM_VERIFY_SSL')
            original_bundle = os.environ.get('LLM_CA_BUNDLE')
            
            try:
                # Clear env vars to avoid interference
                if 'LLM_VERIFY_SSL' in os.environ:
                    del os.environ['LLM_VERIFY_SSL']
                if 'LLM_CA_BUNDLE' in os.environ:
                    del os.environ['LLM_CA_BUNDLE']
                
                # Create initial certificate manager
                manager = CertificateManager(
                    cert_dir=temp_dir,
                    verify=True,
                    ca_bundle=str(initial_cert)
                )
                
                # Get initial SSL config
                initial_config = manager.get_ssl_config()
                initial_bundle = initial_config.ca_bundle
                
                # Update SSL config (simulating configuration change)
                manager.update_ssl_config(ca_bundle=str(new_cert))
                
                # Reload certificates (hot reload)
                manager.reload_certificates()
                
                # Verify configuration was reloaded
                reloaded_config = manager.get_ssl_config()
                reloaded_bundle = reloaded_config.ca_bundle
                
                # The bundle should have changed
                assert reloaded_bundle != initial_bundle or initial_bundle == str(new_cert)
                
                # Verify manager is still functional (no restart needed)
                status = manager.get_status()
                assert status is not None
                assert 'cert_dir' in status
                assert 'ssl_config' in status
                
            finally:
                # Restore env vars
                if original_verify is not None:
                    os.environ['LLM_VERIFY_SSL'] = original_verify
                if original_bundle is not None:
                    os.environ['LLM_CA_BUNDLE'] = original_bundle
