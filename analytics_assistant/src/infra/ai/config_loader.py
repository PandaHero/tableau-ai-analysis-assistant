# -*- coding: utf-8 -*-
"""
ModelManager 配置加载器

从 YAML 文件加载模型配置，支持环境变量展开。
"""
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigLoadError(Exception):
    """配置加载错误"""
    pass


class ModelConfigLoader:
    """模型配置加载器"""
    
    # 环境变量模式：${VAR_NAME} 或 ${VAR_NAME:-default}
    ENV_VAR_PATTERN = re.compile(r'\$\{([^}:]+)(?::-([^}]*))?\}')
    
    def __init__(
        self,
        config_path: str = "config/models.yaml",
        fallback_path: str = "config/models.example.yaml"
    ):
        """
        初始化配置加载器
        
        Args:
            config_path: 配置文件路径（相对于当前工作目录）
            fallback_path: 备用配置文件路径（相对于当前工作目录）
        """
        self.config_path = Path(config_path)
        self.fallback_path = Path(fallback_path)
    
    def load(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            配置字典
            
        Raises:
            ConfigLoadError: 配置加载失败
        """
        # 尝试加载主配置文件
        config_file = self.config_path
        if not config_file.exists():
            logger.warning(f"配置文件不存在: {config_file}")
            
            # 尝试备用配置文件
            if self.fallback_path.exists():
                logger.info(f"使用备用配置文件: {self.fallback_path}")
                config_file = self.fallback_path
            else:
                raise ConfigLoadError(
                    f"配置文件不存在: {self.config_path} 和 {self.fallback_path}"
                )
        
        # 加载 YAML
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigLoadError(f"YAML 解析错误: {e}")
        except Exception as e:
            raise ConfigLoadError(f"配置文件读取失败: {e}")
        
        # 展开环境变量
        config_data = self._expand_env_vars(raw_data)
        
        logger.info(f"配置加载成功: {config_file}")
        return config_data
    
    def _expand_env_vars(self, data: Any) -> Any:
        """
        递归展开环境变量
        
        支持格式：
        - ${VAR_NAME}: 读取环境变量，不存在则保持原样
        - ${VAR_NAME:-default}: 读取环境变量，不存在则使用默认值
        
        Args:
            data: 原始数据
            
        Returns:
            展开后的数据
        """
        if isinstance(data, str):
            return self._expand_string(data)
        elif isinstance(data, dict):
            return {k: self._expand_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._expand_env_vars(item) for item in data]
        else:
            return data
    
    def _expand_string(self, value: str) -> str:
        """
        展开字符串中的环境变量
        
        Args:
            value: 原始字符串
            
        Returns:
            展开后的字符串
        """
        def replace_match(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else match.group(0)
            
            # 获取环境变量
            env_value = os.environ.get(var_name)
            
            if env_value is not None:
                return env_value
            else:
                # 使用默认值
                return default_value
        
        return self.ENV_VAR_PATTERN.sub(replace_match, value)
    
    def load_llm_models(self) -> List[Dict[str, Any]]:
        """
        加载 LLM 模型配置
        
        Returns:
            LLM 模型配置列表
        """
        config = self.load()
        return config.get('llm_models', [])
    
    def load_embedding_models(self) -> List[Dict[str, Any]]:
        """
        加载 Embedding 模型配置
        
        Returns:
            Embedding 模型配置列表
        """
        config = self.load()
        return config.get('embedding_models', [])
    
    def load_global_config(self) -> Dict[str, Any]:
        """
        加载全局配置
        
        Returns:
            全局配置字典
        """
        config = self.load()
        return config.get('global', {})


def load_models_from_yaml(
    config_path: str = "config/models.yaml",
    fallback_path: str = "config/models.example.yaml"
) -> Dict[str, List[Dict[str, Any]]]:
    """
    从 YAML 文件加载模型配置（便捷函数）
    
    Args:
        config_path: 配置文件路径
        fallback_path: 备用配置文件路径
        
    Returns:
        包含 llm_models 和 embedding_models 的字典
        
    Raises:
        ConfigLoadError: 配置加载失败
    """
    loader = ModelConfigLoader(config_path, fallback_path)
    
    return {
        'llm_models': loader.load_llm_models(),
        'embedding_models': loader.load_embedding_models(),
        'global': loader.load_global_config(),
    }


__all__ = [
    "ModelConfigLoader",
    "ConfigLoadError",
    "load_models_from_yaml",
]
