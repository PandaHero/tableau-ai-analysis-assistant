# -*- coding: utf-8 -*-
"""Agent 中间件模块。

所有中间件均使用框架现成实现，不自定义中间件类：
- ModelRetryMiddleware: langchain.agents.middleware.ModelRetryMiddleware
- ToolRetryMiddleware: langchain.agents.middleware.ToolRetryMiddleware
- SummarizationMiddleware: langchain.agents.middleware.SummarizationMiddleware
- FilesystemMiddleware: deepagents.FilesystemMiddleware
"""
