"""
Tests for configuration parser
"""
import pytest
import tempfile
import os
from pathlib import Path

from tableau_assistant.cert_manager.config_parser import ConfigurationParser


class TestConfigurationParser:
    """Tests for ConfigurationParser"""
    
    def test_load_config_from_yaml(self):
        """Test loading configuration from YAML file"""
        parser = ConfigurationParser()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.yaml"
            config_file.write_text("""
cert_dir: "test_certs"
verify_ssl: true
warning_days: 15

application:
  source: "self-signed"
  backend:
    cert_file: "test.pem"
    key_file: "test_key.pem"

services:
  test-service:
    hostname: "test.example.com"
    port: 443
""")
            
            config = parser.load_config(str(config_file))
            
            assert config['cert_dir'] == "test_certs"
            assert config['verify_ssl'] is True
            assert config['warning_days'] == 15
            assert config['application']['source'] == "self-signed"
            assert config['services']['test-service']['hostname'] == "test.example.com"
    
    def test_environment_variable_substitution(self):
        """Test environment variable substitution in config"""
        parser = ConfigurationParser()
        
        # Set test environment variable
        os.environ['TEST_HOSTNAME'] = 'env.example.com'
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                config_file = Path(temp_dir) / "test_config.yaml"
                config_file.write_text("""
services:
  test-service:
    hostname: "${TEST_HOSTNAME}"
    port: 443
""")
                
                config = parser.load_config(str(config_file))
                
                assert config['services']['test-service']['hostname'] == 'env.example.com'
        finally:
            del os.environ['TEST_HOSTNAME']
    
    def test_validate_config_valid(self):
        """Test validation of valid configuration"""
        parser = ConfigurationParser()
        
        config = {
            'cert_dir': 'certs',
            'verify_ssl': True,
            'warning_days': 30,
            'application': {
                'source': 'self-signed',
                'backend': {
                    'cert_file': 'test.pem',
                    'key_file': 'test_key.pem'
                }
            },
            'services': {
                'test': {
                    'hostname': 'test.com',
                    'port': 443
                }
            }
        }
        
        result = parser.validate_config(config)
        
        assert result['valid'] is True
        assert len(result['errors']) == 0
    
    def test_validate_config_with_file_path_check(self):
        """Test validation with file path checking"""
        parser = ConfigurationParser()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test certificate files
            cert_file = Path(temp_dir) / "test.pem"
            cert_file.write_text("test cert")
            
            config = {
                'cert_dir': temp_dir,
                'application': {
                    'backend': {
                        'cert_file': 'test.pem',
                        'key_file': 'missing_key.pem'  # This file doesn't exist
                    }
                }
            }
            
            result = parser.validate_config(config, check_file_paths=True)
            
            # Should still be valid (warnings, not errors)
            assert result['valid'] is True
            # Should have warnings about missing key file
            assert len(result['warnings']) > 0
            assert any('missing_key.pem' in w for w in result['warnings'])
    
    def test_validate_config_invalid(self):
        """Test validation of invalid configuration"""
        parser = ConfigurationParser()
        
        config = {
            'verify_ssl': 'not_a_boolean',  # Should be boolean
            'warning_days': -5,  # Should be non-negative
            'application': {
                'source': 'invalid',  # Should be 'self-signed' or 'company'
                'backend': {
                    # Missing required fields
                }
            }
        }
        
        result = parser.validate_config(config)
        
        assert result['valid'] is False
        assert len(result['errors']) > 0
    
    def test_get_default_config(self):
        """Test getting default configuration"""
        parser = ConfigurationParser()
        
        config = parser.get_default_config()
        
        assert 'cert_dir' in config
        assert 'verify_ssl' in config
        assert 'application' in config
        assert 'services' in config
    
    def test_merge_configs(self):
        """Test merging multiple configurations"""
        parser = ConfigurationParser()
        
        config1 = {
            'cert_dir': 'dir1',
            'verify_ssl': True,
            'application': {
                'source': 'self-signed'
            }
        }
        
        config2 = {
            'cert_dir': 'dir2',
            'warning_days': 15,
            'application': {
                'backend': {
                    'cert_file': 'test.pem'
                }
            }
        }
        
        merged = parser.merge_configs(config1, config2)
        
        # Later config should override
        assert merged['cert_dir'] == 'dir2'
        assert merged['verify_ssl'] is True
        assert merged['warning_days'] == 15
        # Nested dicts should be merged
        assert merged['application']['source'] == 'self-signed'
        assert merged['application']['backend']['cert_file'] == 'test.pem'
    
    def test_extract_env_config(self):
        """Test extracting configuration from environment variables"""
        parser = ConfigurationParser()
        
        # Set test environment variables
        os.environ['CERT_DIR'] = 'test_certs'
        os.environ['LLM_VERIFY_SSL'] = 'false'
        os.environ['CERT_WARNING_DAYS'] = '20'
        
        try:
            env_config = parser.extract_env_config()
            
            assert env_config['cert_dir'] == 'test_certs'
            assert env_config['verify_ssl'] is False
            assert env_config['warning_days'] == 20
        finally:
            del os.environ['CERT_DIR']
            del os.environ['LLM_VERIFY_SSL']
            del os.environ['CERT_WARNING_DAYS']
    
    def test_load_config_with_precedence(self):
        """Test loading configuration with precedence rules"""
        parser = ConfigurationParser()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "test_config.yaml"
            config_file.write_text("""
cert_dir: "file_certs"
verify_ssl: false
""")
            
            env_config = {
                'cert_dir': 'env_certs'
            }
            
            config = parser.load_config_with_precedence(
                config_file=str(config_file),
                env_config=env_config
            )
            
            # Environment should override file
            assert config['cert_dir'] == 'env_certs'
            # File should override defaults
            assert config['verify_ssl'] is False
