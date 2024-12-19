"""Provide a proxy device to subclass."""

# Imports
from facadedevice.device import Facade, TimedFacade
from facadedevice.graph import triplet
from facadedevice.objects import (
    combined_attribute,
    local_attribute,
    logical_attribute,
    proxy_attribute,
    proxy_command,
    state_attribute,
)

__all__ = [
    "Facade",
    "TimedFacade",
    "triplet",
    "proxy_attribute",
    "local_attribute",
    "logical_attribute",
    "state_attribute",
    "proxy_command",
    "combined_attribute",
]
