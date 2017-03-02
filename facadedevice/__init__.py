"""Provide a proxy device to subclass."""

__all__ = ['Facade', 'FacadeMeta', 'proxy_attribute', 'local_attribute',
           'logical_attribute', 'proxy_command', 'proxy', 'block_attribute',
           'stamped']

# Imports
from facadedevice.device import Facade, FacadeMeta
from facadedevice.objects import local_attribute, logical_attribute
from facadedevice.objects import proxy_attribute, proxy_command
from facadedevice.objects import block_attribute
from facadedevice.common import stamped
