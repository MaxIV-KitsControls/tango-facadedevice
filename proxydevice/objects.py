"""Provide class objects for the proxy device."""

# Imports
from time import time
from functools import wraps

# PyTango
from PyTango import AttrQuality
from PyTango.server import device_property, attribute, command


# Decorator
def catch_key_error(func=None, dtype=int):
    """Return a decorator to catch index errors."""
    def decorator(func):
        """Decorator to catch index erros."""
        @wraps(func)
        def wrapper(self):
            """Wrapper for attribute reader."""
            try:
                return func(self)
            except KeyError:
                return dtype(), time(), AttrQuality.ATTR_INVALID
        return wrapper
    # Decorate
    if func:
        return decorator(func)
    # Or return decorator
    return decorator


# Base proxy object
class proxy_object(object):
    """Provide a base for objects to be processed by ProxyMeta."""

    def update_class(self, dct):
        """Method to override."""
        raise NotImplementedError


# Base attribute object
class base_attribute(proxy_object):
    """Provide a base for enhanced Tango attributes."""

    def __init__(self, **kwargs):
        """Init with tango attribute keywords."""
        self.kwargs = kwargs

    def update_class(self, key, dct):
        """Create the attribute and read method."""
        # Attribute
        dtype = self.kwargs['dtype']
        dct[key] = attribute(**self.kwargs)
        reader_name = 'read_' + key
        # Read method
        def reader(device):
            """Read the value from attribute dictionary."""
            return device._proxy_data[key]
        reader.__name__ = reader_name
        # Set read method
        dct[reader_name] = catch_key_error(reader, dtype)


# Proxy attribute object
class proxy_attribute(base_attribute):
    """Tango attribute linked to the attribute of a remote device.
    Device and attribute are given as property names.
    Also supports the standard attribute keywords.
    """

    def __init__(self, device, attr, **kwargs):
        """Initialize with the device property name, the attribute property
        name and the standard tango attribute keywords.
        """
        self.device = device
        self.attr = attr
        self.kwargs = kwargs

    def update_class(self, key, dct):
        """Create properties, attribute and read method.
        Also register useful informations in the property dictionary.
        """
        # Parent method
        base_attribute.update_class(self, key, dct)
        dtype = self.kwargs['dtype']
        # Register proxy
        dct["_proxy_property_dct"].setdefault(self.device, [])
        # Register attribute
        value = key, self.attr, dtype
        dct["_proxy_property_dct"][self.device].append(value)
        # Create device properties
        dct[self.attr] = device_property(dtype=str, doc=self.attr)
        dct[self.device] = device_property(dtype=str, doc=self.device)

# Logical attribute object
class logical_attribute(base_attribute):
    """Tango attribute computed from the values of other attributes.
    Use it as a decorator to register the function that make this computation.
    The decorated method take the attribute value dictionnary as argument.
    Logical attributes also support the standard attribute keywords.
    """

    def __call__(self, method):
        """Decorator support."""
        self.method = method
        return self

    def update_class(self, key, dct):
        """Create attribute and register method."""
        base_attribute.update_class(self, key, dct)
        dct["_proxy_method_dct"][key] = self.method

# Proxy command object
class proxy_command(proxy_object):
    """Command to write an attribute of a remote device with a given value.
    Attribute and device are given as property names.
    It supports standard command keywords.
    """

    def __init__(self, device, attr, value, **kwargs):
        """Initialize with the device property name, the attribute property
        name, the value to write and the standard tango attribute keywords.
        """
        self.kwargs = kwargs
        self.device = device
        self.attr = attr
        self.value = value

    def update_class(self, key, dct):
        """Create the command, methods and device properties."""
        # Create command
        cmd = command(**self.kwargs)
        # Run method
        def run_command(device):
            """Write the attribute of the remote device with the value."""
            # Get device
            prop = getattr(device, self.device.lower())
            device_proxy = device._proxy_device_dct[prop]
            # Get attribute name
            attr = getattr(device, self.attr.lower())
            # Check attribute
            if attr.strip().lower() == "none":
                msg = "no attribute for {0} property."
                raise ValueError(msg.format(self.attr))
            # Write
            device_proxy.write_attribute(attr, self.value)
        # Set command
        run_command.__name__ = key
        dct[key] = cmd(run_command)
        # Is allowed method
        method_name = "is_" + key + "_allowed"
        def is_allowed(device):
            """The method is allowed if the device is connected."""
            return device.connected
        # Set method
        is_allowed.__name__ = method_name
        dct[method_name] = is_allowed
        # Create properties
        dct[self.attr] = device_property(dtype=str, doc=self.attr)
        dct[self.device] = device_property(dtype=str, doc=self.device)

