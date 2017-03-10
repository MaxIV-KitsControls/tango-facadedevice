"""Provide a proxy device to subclass."""

# Imports
from facadedevice.device import Facade, FacadeMeta
from facadedevice.objects import local_attribute, logical_attribute
from facadedevice.objects import proxy_attribute, proxy_command
from facadedevice.objects import block_attribute

__all__ = ['Facade', 'FacadeMeta', 'proxy_attribute', 'local_attribute',
           'logical_attribute', 'proxy_command', 'block_attribute']
