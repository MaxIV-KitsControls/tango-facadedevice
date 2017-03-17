"""Provide a proxy device to subclass."""

# Imports
from facadedevice.device import Facade, TimedFacade
from facadedevice.objects import local_attribute, logical_attribute
from facadedevice.objects import proxy_attribute, proxy_command
from facadedevice.objects import state_attribute, combined_attribute

__all__ = ['Facade', 'TimedFacade',
           'proxy_attribute', 'local_attribute', 'logical_attribute',
           'state_attribute', 'proxy_command', 'combined_attribute']
