"""Provide a proxy device to subclass."""

__all__ = ['Proxy', 'ProxyMeta', 'proxy_attribute', 'logical_attribute',
           'proxy_command', 'proxy']

# Imports
from proxydevice.device import Proxy, ProxyMeta
from proxydevice.objects import proxy_attribute, logical_attribute
from proxydevice.objects import proxy_command, proxy
