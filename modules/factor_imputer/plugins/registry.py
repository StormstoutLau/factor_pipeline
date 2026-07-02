# -*- coding: utf-8 -*-
"""
插件注册表模块
管理所有插补插件
"""

from typing import Dict, List, Optional

from .base import ImputationPlugin


class PluginRegistry:
    """插件注册表"""

    def __init__(self):
        self._plugins: Dict[str, ImputationPlugin] = {}

    def register(self, plugin: ImputationPlugin) -> None:
        """注册插件"""
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str) -> None:
        """注销插件"""
        if name in self._plugins:
            del self._plugins[name]

    def get(self, name: str) -> Optional[ImputationPlugin]:
        """获取插件"""
        return self._plugins.get(name)

    def list_plugins(self) -> List[str]:
        """列出所有插件"""
        return list(self._plugins.keys())

    def get_plugins_for_pattern(self, pattern: str) -> List[ImputationPlugin]:
        """获取支持特定模式的插件"""
        return [plugin for plugin in self._plugins.values() if pattern in plugin.supported_patterns]
