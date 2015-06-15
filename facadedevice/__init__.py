"""Provide a proxy device to subclass."""

__all__ = ['Facade', 'FacadeMeta', 'proxy_attribute', 'logical_attribute',
           'proxy_command', 'proxy', 'stamped']

# Imports
from facadedevice.device import Facade, FacadeMeta
from facadedevice.objects import proxy_attribute, logical_attribute
from facadedevice.objects import proxy_command, proxy
from facadedevice.common import stamped
