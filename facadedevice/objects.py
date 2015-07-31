"""Provide class objects for the facade device."""

# Imports
import time
from PyTango import AttrWriteType
from PyTango.server import device_property, attribute, command
from facadedevice.common import event_property, mapping

# Constants
PREFIX = ''
SUFFIX = '_data'


# Attribute data name
def attr_data_name(key):
    return PREFIX + key.lower() + SUFFIX


# Attribute mapping
def attribute_mapping(instance):
    keys = instance._class_dict["attributes"]
    return mapping(instance, attr_data_name, keys)


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
        dct[self.device] = device_property(dtype=str, doc="Proxy device.")


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
        # Property
        prop = event_property(key, dtype=self.dtype, event="use_events",
                              is_allowed=self.kwargs.get("fisallowed"))
        dct[attr_data_name(key)] = prop
        # Attribute
        dct[key] = attribute(fget=prop.read, **self.kwargs)
        dct["_class_dict"]["attributes"][key] = self


# Proxy attribute object
class proxy_attribute(logical_attribute, proxy):
    """Tango attribute linked to the attribute of a remote device.

    Device and attribute are given as property names.
    Also supports the standard attribute keywords.
    """

    def __init__(self, device, attr, default_attr=None, **kwargs):
        """Initialize with the device property name, the attribute property
        name and the standard tango attribute keywords.
        """
        logical_attribute.__init__(self, **kwargs)
        proxy.__init__(self, device)
        self.attr = attr
        self.default_attr = default_attr

    def update_class(self, key, dct):
        """Create properties, attribute and read method.

        Also register useful informations in the property dictionary.
        """
        # Parent method
        logical_attribute.update_class(self, key, dct)
        proxy.update_class(self, key, dct)
        # Create device property
        doc = "Attribute of {0} forwarded as {1}.".format(self.device, key)
        dct[self.attr] = device_property(dtype=str, doc=doc,
                                         default_value=self.default_attr)
        # Write type
        write = self.kwargs.get("access") == AttrWriteType.READ_WRITE
        write = write and not dct.get("is_" + key + "_allowed")
        write = write and not set(self.kwargs) & set(["fwrite", "fset"])
        if not write:
            return

        # Write method
        def write(device, value):
            proxy_name = device._device_dict[key]
            device_proxy = device._proxy_dict[proxy_name]
            proxy_attr = device._attribute_dict[key]
            device_proxy.write_attribute(proxy_attr, value)
        dct[key] = dct[key].setter(write)


# Proxy command object
class proxy_command(proxy):
    """Command to write an attribute of a remote device with a given value.

    Attribute and device are given as property names.
    It supports standard command keywords.
    """

    def __init__(self, device, attr, value, reset_value=None, reset_delay=0,
                 **kwargs):
        """Initialize with the device property name, the attribute property
        name, the value to write and the standard tango attribute
        keywords.

        Optionally you may add a reset_value and a
        reset_delay [ms], meaning that the reset value will be written
        after some time (e.g. for PLCs where the tag needs to be
        zeroed again after setting). Note that this means that the
        command will take at least reset_delay ms to complete
        """
        proxy.__init__(self, device)
        self.kwargs = kwargs
        self.value = value
        self.attr = attr
        self.reset_value = reset_value
        self.reset_delay = reset_delay

    def update_class(self, key, dct):
        """Create the command, methods and device properties."""
        # Register
        proxy.update_class(self, key, dct)
        dct["_class_dict"]["commands"][key] = self

        # Command method
        def run_command(device):
            """Write the attribute of the remote device with the value."""
            # Get data
            attr, value, reset_value, reset_delay = device._command_dict[key]
            # Check attribute
            if attr.strip().lower() == "none":
                msg = "no attribute for {0} property."
                raise ValueError(msg.format(self.attr))
            # Write
            proxy_name = device._device_dict[key]
            device_proxy = device._proxy_dict[proxy_name]
            device_proxy.write_attribute(attr, value)
            if reset_value is not None:
                time.sleep(reset_delay / 1000.0)
                device_proxy.write_attribute(attr, reset_value)

        # Set command
        cmd = command(**self.kwargs)
        run_command.__name__ = key
        doc = "Write the attribute '{0}' of '{1}' with value {2}"
        run_command.__doc__ = doc.format(self.attr, self.device, self.value)
        dct[key] = cmd(run_command)

        # Is allowed method
        def is_allowed(device):
            """The method is allowed if the device is connected."""
            return device.connected

        # Set method
        method_name = "is_" + key + "_allowed"
        # prefer user defined "is_X_allowed" methods
        if method_name not in dct:
            is_allowed.__name__ = method_name
            dct[method_name] = is_allowed
        # Create properties
        dct[self.attr] = device_property(dtype=str, doc=self.attr)


# Update docs function
def update_docs(dct):
    """Update the documentation for device properties."""
    # Get attributes
    attrs_dct = {}
    for attr, value in dct["_class_dict"]["devices"].items():
        if isinstance(value, proxy_attribute):
            attrs_dct.setdefault(value.device, []).append(attr)
    # Generate doc
    for device, attrs in attrs_dct.items():
        doc = 's ' + ', '.join(attrs[:-1]) + ' and ' if attrs[:-1] else ' '
        doc = 'Proxy device for attribute{0}.'.format(doc + attrs[-1])
        dct[device] = device_property(dtype=str, doc=doc)
