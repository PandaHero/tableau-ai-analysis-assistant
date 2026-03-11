# -*- coding: utf-8 -*-
"""Agent 中间件模块。

LangChain 内置中间件（直接使用，不重复造轮子）：
- ModelRetryMiddleware: langchain.agents.middleware.ModelRetryMiddleware
- ToolRetryMiddleware: langchain.agents.middleware.ToolRetryMiddleware
- SummarizationMiddleware: langchain.agents.middleware.SummarizationMiddleware

本地实现中间件（替代 deepagents 依赖）：
- FilesystemMiddleware: analytics_assistant.src.agents.base.middleware.filesystem
"""

from .filesystem import FilesystemMiddleware

__all__ = ["FilesystemMiddleware"]
