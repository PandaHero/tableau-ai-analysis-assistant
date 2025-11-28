"""
Property-based tests for certificate manager data models

These tests use Hypothesis to verify universal properties across many inputs.
Each test runs a minimum of 100 iterations with randomly generated data.
"""
import pytest
from hypothesis import given, strategies as st, settings
from datetime import datetime, timedelta
from tableau_assistant.cert_manager.models import (
    ServiceConfig,
    ApplicationCertConfig,
    CertificateMetadata
)


# Custom strategies for generating test data
@st.composite
def service_config_strategy(draw):
    """Generate random ServiceConfig instances"""
    service_id = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('Lu', 'Ll', 'Nd'), whitelist_characters='-_'
    )))
    hostname = draw(st.from_regex(r'^[a-z0-9.-]+\.[a-z]{2,}$', fullmatch=True))
    port = draw(st.integers(min_value=1, max_value=65535))
    ca_bundle = draw(st.one_of(
        st.none(),
        st.text(min_size=1, max_size=100)
    ))
    auto_fetch = draw(st.booleans())
    
    # Generate optional datetime values
    last_fetched = draw(st.one_of(
        st.none(),
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31)
        )
    ))
    last_validated = draw(st.one_of(
        st.none(),
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31)
        )
    ))
    validation_status = draw(st.sampled_from(["valid", "expired", "invalid", "unknown"]))
    
    return ServiceConfig(
        service_id=service_id,
        hostname=hostname,
        port=port,
        ca_bundle=ca_bundle,
        auto_fetch=auto_fetch,
        last_fetched=last_fetched,
        last_validated=last_validated,
        validation_status=validation_status
    )


class TestServiceConfigProperties:
    """Property-based tests for ServiceConfig"""
    
    @settings(max_examples=100)
    @given(config=service_config_strategy())
    def test_property_2_service_certificate_association(self, config):
        """
        Feature: cert-manager-enhancement, Property 2: Service certificate association
        
        For any registered service, the stored certificate should be retrievable
        using the service identifier.
        
        This test verifies that ServiceConfig can be serialized to a dictionary
        and deserialized back, maintaining the service_id association.
        
        Validates: Requirements 1.3
        """
        # Serialize to dictionary
        config_dict = config.to_dict()
        
        # Verify service_id is preserved in dictionary
        assert 'service_id' in config_dict
        assert config_dict['service_id'] == config.service_id
        
        # Deserialize from dictionary
        restored_config = ServiceConfig.from_dict(config_dict)
        
        # Verify service_id is preserved after round-trip
        assert restored_config.service_id == config.service_id
        
        # Verify all other fields are preserved
        assert restored_config.hostname == config.hostname
        assert restored_config.port == config.port
        assert restored_config.ca_bundle == config.ca_bundle
        assert restored_config.auto_fetch == config.auto_fetch
        assert restored_config.validation_status == config.validation_status
        
        # Verify datetime fields are preserved (with microsecond precision)
        if config.last_fetched:
            assert restored_config.last_fetched is not None
            # Compare timestamps (datetime comparison handles microseconds)
            assert abs((restored_config.last_fetched - config.last_fetched).total_seconds()) < 0.001
        else:
            assert restored_config.last_fetched is None
            
        if config.last_validated:
            assert restored_config.last_validated is not None
            assert abs((restored_config.last_validated - config.last_validated).total_seconds()) < 0.001
        else:
            assert restored_config.last_validated is None
    
    @settings(max_examples=100)
    @given(config=service_config_strategy())
    def test_service_config_round_trip_preserves_data(self, config):
        """
        Verify that ServiceConfig serialization is lossless
        
        For any ServiceConfig, converting to dict and back should preserve all data.
        """
        # Round trip: config -> dict -> config
        config_dict = config.to_dict()
        restored_config = ServiceConfig.from_dict(config_dict)
        
        # Verify the round trip preserves the data
        assert restored_config.service_id == config.service_id
        assert restored_config.hostname == config.hostname
        assert restored_config.port == config.port
        assert restored_config.ca_bundle == config.ca_bundle
        assert restored_config.auto_fetch == config.auto_fetch
        assert restored_config.validation_status == config.validation_status
    
    @settings(max_examples=100)
    @given(config=service_config_strategy())
    def test_service_config_dict_contains_all_fields(self, config):
        """
        Verify that to_dict() includes all required fields
        
        For any ServiceConfig, the dictionary representation should contain
        all fields defined in the dataclass.
        """
        config_dict = config.to_dict()
        
        # Verify all required fields are present
        required_fields = [
            'service_id', 'hostname', 'port', 'ca_bundle', 'auto_fetch',
            'last_fetched', 'last_validated', 'validation_status'
        ]
        
        for field in required_fields:
            assert field in config_dict, f"Field '{field}' missing from dictionary"
    
    @settings(max_examples=100)
    @given(config=service_config_strategy())
    def test_service_config_datetime_serialization(self, config):
        """
        Verify that datetime fields are properly serialized to ISO format
        
        For any ServiceConfig with datetime fields, they should be converted
        to ISO format strings in the dictionary representation.
        """
        config_dict = config.to_dict()
        
        # If datetime fields are present, they should be strings in ISO format
        if config.last_fetched:
            assert isinstance(config_dict['last_fetched'], str)
            # Verify it's a valid ISO format by parsing it back
            parsed = datetime.fromisoformat(config_dict['last_fetched'])
            assert isinstance(parsed, datetime)
        
        if config.last_validated:
            assert isinstance(config_dict['last_validated'], str)
            parsed = datetime.fromisoformat(config_dict['last_validated'])
            assert isinstance(parsed, datetime)


@st.composite
def application_cert_config_strategy(draw):
    """Generate random ApplicationCertConfig instances"""
    source = draw(st.sampled_from(["self-signed", "company"]))
    cert_file = draw(st.text(min_size=1, max_size=100))
    key_file = draw(st.text(min_size=1, max_size=100))
    ca_bundle = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))
    common_name = draw(st.text(min_size=1, max_size=50))
    validity_days = draw(st.integers(min_value=1, max_value=3650))
    
    # Company certificate fields
    company_cert_file = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))
    company_key_file = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))
    company_ca_bundle = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))
    
    return ApplicationCertConfig(
        source=source,
        cert_file=cert_file,
        key_file=key_file,
        ca_bundle=ca_bundle,
        common_name=common_name,
        validity_days=validity_days,
        company_cert_file=company_cert_file,
        company_key_file=company_key_file,
        company_ca_bundle=company_ca_bundle
    )


class TestApplicationCertConfigProperties:
    """Property-based tests for ApplicationCertConfig"""
    
    @settings(max_examples=100)
    @given(config=application_cert_config_strategy())
    def test_application_cert_config_round_trip(self, config):
        """
        Verify that ApplicationCertConfig serialization is lossless
        
        For any ApplicationCertConfig, converting to dict and back should preserve all data.
        """
        # Round trip: config -> dict -> config
        config_dict = config.to_dict()
        restored_config = ApplicationCertConfig.from_dict(config_dict)
        
        # Verify all fields are preserved
        assert restored_config.source == config.source
        assert restored_config.cert_file == config.cert_file
        assert restored_config.key_file == config.key_file
        assert restored_config.ca_bundle == config.ca_bundle
        assert restored_config.common_name == config.common_name
        assert restored_config.validity_days == config.validity_days
        assert restored_config.company_cert_file == config.company_cert_file
        assert restored_config.company_key_file == config.company_key_file
        assert restored_config.company_ca_bundle == config.company_ca_bundle
    
    @settings(max_examples=100)
    @given(config=application_cert_config_strategy())
    def test_active_cert_file_returns_correct_source(self, config):
        """
        Verify that get_active_cert_file() returns the correct file based on source
        
        For any ApplicationCertConfig, the active cert file should match the source.
        """
        active_cert = config.get_active_cert_file()
        
        if config.source == "company" and config.company_cert_file:
            assert active_cert == config.company_cert_file
        else:
            assert active_cert == config.cert_file
    
    @settings(max_examples=100)
    @given(config=application_cert_config_strategy())
    def test_active_key_file_returns_correct_source(self, config):
        """
        Verify that get_active_key_file() returns the correct file based on source
        
        For any ApplicationCertConfig, the active key file should match the source.
        """
        active_key = config.get_active_key_file()
        
        if config.source == "company" and config.company_key_file:
            assert active_key == config.company_key_file
        else:
            assert active_key == config.key_file
    
    @settings(max_examples=100)
    @given(config=application_cert_config_strategy())
    def test_active_ca_bundle_returns_correct_source(self, config):
        """
        Verify that get_active_ca_bundle() returns the correct bundle based on source
        
        For any ApplicationCertConfig, the active CA bundle should match the source.
        """
        active_ca = config.get_active_ca_bundle()
        
        if config.source == "company" and config.company_ca_bundle:
            assert active_ca == config.company_ca_bundle
        else:
            assert active_ca == config.ca_bundle


@st.composite
def certificate_metadata_strategy(draw):
    """Generate random CertificateMetadata instances"""
    file_path = draw(st.text(min_size=1, max_size=100))
    cert_type = draw(st.sampled_from(["service", "application", "ca_bundle"]))
    service_id = draw(st.one_of(st.none(), st.text(min_size=1, max_size=50)))
    
    # Generate optional datetime values
    created_at = draw(st.one_of(
        st.none(),
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31)
        )
    ))
    expires_at = draw(st.one_of(
        st.none(),
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31)
        )
    ))
    
    issuer = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))
    subject = draw(st.one_of(st.none(), st.text(min_size=1, max_size=100)))
    is_valid = draw(st.booleans())
    validation_errors = draw(st.lists(st.text(min_size=1, max_size=100), max_size=5))
    
    return CertificateMetadata(
        file_path=file_path,
        cert_type=cert_type,
        service_id=service_id,
        created_at=created_at,
        expires_at=expires_at,
        issuer=issuer,
        subject=subject,
        is_valid=is_valid,
        validation_errors=validation_errors
    )


class TestCertificateMetadataProperties:
    """Property-based tests for CertificateMetadata"""
    
    @settings(max_examples=100)
    @given(metadata=certificate_metadata_strategy())
    def test_certificate_metadata_round_trip(self, metadata):
        """
        Verify that CertificateMetadata serialization is lossless
        
        For any CertificateMetadata, converting to dict and back should preserve all data.
        """
        # Round trip: metadata -> dict -> metadata
        metadata_dict = metadata.to_dict()
        restored_metadata = CertificateMetadata.from_dict(metadata_dict)
        
        # Verify all fields are preserved
        assert restored_metadata.file_path == metadata.file_path
        assert restored_metadata.cert_type == metadata.cert_type
        assert restored_metadata.service_id == metadata.service_id
        assert restored_metadata.issuer == metadata.issuer
        assert restored_metadata.subject == metadata.subject
        assert restored_metadata.is_valid == metadata.is_valid
        assert restored_metadata.validation_errors == metadata.validation_errors
        
        # Verify datetime fields are preserved
        if metadata.created_at:
            assert restored_metadata.created_at is not None
            assert abs((restored_metadata.created_at - metadata.created_at).total_seconds()) < 0.001
        else:
            assert restored_metadata.created_at is None
            
        if metadata.expires_at:
            assert restored_metadata.expires_at is not None
            assert abs((restored_metadata.expires_at - metadata.expires_at).total_seconds()) < 0.001
        else:
            assert restored_metadata.expires_at is None
    
    @settings(max_examples=100)
    @given(metadata=certificate_metadata_strategy())
    def test_certificate_metadata_datetime_serialization(self, metadata):
        """
        Verify that datetime fields are properly serialized to ISO format
        
        For any CertificateMetadata with datetime fields, they should be converted
        to ISO format strings in the dictionary representation.
        """
        metadata_dict = metadata.to_dict()
        
        # If datetime fields are present, they should be strings in ISO format
        if metadata.created_at:
            assert isinstance(metadata_dict['created_at'], str)
            parsed = datetime.fromisoformat(metadata_dict['created_at'])
            assert isinstance(parsed, datetime)
        
        if metadata.expires_at:
            assert isinstance(metadata_dict['expires_at'], str)
            parsed = datetime.fromisoformat(metadata_dict['expires_at'])
            assert isinstance(parsed, datetime)
