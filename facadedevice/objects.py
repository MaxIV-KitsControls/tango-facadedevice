"""Provide class objects for the facade device."""

# Imports
from facadedevice.common import catch_key_error
from PyTango.server import device_property, attribute, command


# Base class object
class class_object(object):
    """Provide a base for objects to be processed by ProxyMeta."""

    def update_class(self, key, dct):
        """Method to override."""
        raise NotImplementedError


# Proxy object
class proxy(class_object):
    """Tango DeviceProxy handled automatically by the Proxy device."""

    def __init__(self, device=None):
        """Initialize with the device property name."""
        self.device = device

    def update_class(self, key, dct):
        """Register proxy and create device property."""
        if not self.device:
            self.device = key
        dct["_class_dict"]["devices"][key] = self
        dct[self.device] = device_property(dtype=str, doc=self.device)


# Logical attribute object
class logical_attribute(class_object):
    """Tango attribute computed from the values of other attributes.
    Use it as a decorator to register the function that make this computation.
    The decorated method take the attribute value dictionnary as argument.
    Logical attributes also support the standard attribute keywords.
    """

    def __init__(self, **kwargs):
        """Init with tango attribute keywords."""
        self.kwargs = kwargs
        self.dtype = self.kwargs['dtype']
        self.method = None
        self.attr = None
        self.device = None

    def __call__(self, method):
        """Decorator support."""
        self.method = method
        return self

    def update_class(self, key, dct):
        """Create the attribute and read method."""
        # Attribute
        dct[key] = attribute(**self.kwargs)
        dct["_class_dict"]["attributes"][key] = self

        # Read method
        def reader(device):
            """Read the value from attribute dictionary."""
            return device._data_dict[key]

        # Set reader method
        reader_name = 'read_' + key
        reader.__name__ = reader_name
        dct[reader_name] = catch_key_error(reader, self.dtype)


# Proxy attribute object
class proxy_attribute(logical_attribute, proxy):
    """Tango attribute linked to the attribute of a remote device.
    Device and attribute are given as property names.
    Also supports the standard attribute keywords.
    """

    def __init__(self, device, attr, **kwargs):
        """Initialize with the device property name, the attribute property
        name and the standard tango attribute keywords.
        """
        logical_attribute.__init__(self, **kwargs)
        proxy.__init__(self, device)
        self.attr = attr

    def update_class(self, key, dct):
        """Create properties, attribute and read method.
        Also register useful informations in the property dictionary.
        """
        # Parent method
        logical_attribute.update_class(self, key, dct)
        proxy.update_class(self, key, dct)
        # Create device property
        dct[self.attr] = device_property(dtype=str, doc=self.attr)


# Proxy command object
class proxy_command(proxy):
    """Command to write an attribute of a remote device with a given value.
    Attribute and device are given as property names.
    It supports standard command keywords.
    """

    def __init__(self, device, attr, value, **kwargs):
        """Initialize with the device property name, the attribute property
        name, the value to write and the standard tango attribute keywords.
        """
        proxy.__init__(self, device)
        self.kwargs = kwargs
        self.value = value
        self.attr = attr

    def update_class(self, key, dct):
        """Create the command, methods and device properties."""
        # Register
        proxy.update_class(self, key, dct)
        dct["_class_dict"]["commands"][key] = self

        # Command method
        def run_command(device):
            """Write the attribute of the remote device with the value."""
            # Get data
            attr, value = device._command_dict[key]
            # Check attribute
            if attr.strip().lower() == "none":
                msg = "no attribute for {0} property."
                raise ValueError(msg.format(self.attr))
            # Write
            device_proxy = device._device_dict[key]
            device_proxy.write_attribute(attr, value)

        # Set command
        cmd = command(**self.kwargs)
        run_command.__name__ = key
        dct[key] = cmd(run_command)

        # Is allowed method
        def is_allowed(device):
            """The method is allowed if the device is connected."""
            return device.connected

        # Set method
        method_name = "is_" + key + "_allowed"
        is_allowed.__name__ = method_name
        dct[method_name] = is_allowed
        # Create properties
        dct[self.attr] = device_property(dtype=str, doc=self.attr)
