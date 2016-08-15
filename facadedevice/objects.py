"""Provide class objects for the facade device."""

# Imports
import time
from PyTango import AttrWriteType, CmdArgType
from PyTango.server import device_property, attribute, command
from facadedevice.common import event_property, mapping
from facadedevice.common import NONE_STRING

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


# Local attribute object
class local_attribute(class_object):
    """Tango attribute with event support.
    It will also be available through the data dictionary.
    Local attributes support the standard attribute keywords.

    Args:
        callback (str or function): method to call when the attribute
            changes. It is called with value, stamp and quality.
        errback (str or function): method to call when the callback
            fails. It is called with error, message and origin.
    """

    def __init__(self, callback=None, errback='ignore_exception', **kwargs):
        """Init with tango attribute keywords.

        Args:
            callback (str or function): method to call when the attribute
                changes. It is called with value, stamp and quality.
            errback (str or function): method to call when the callback
                fails. It is called with error, message and origin.
        """
        self.kwargs = kwargs
        self.dtype = self.kwargs['dtype']
        self.callback = callback
        self.errback = errback
        self.method = None
        self.attr = None
        self.prop = None
        self.device = None

    def notify(self, callback):
        """To use as a decorator to register a callback."""
        self.callback = callback
        return callback

    def update_class(self, key, dct):
        """Create the attribute and read method."""
        # Property
        prop = event_property(key, dtype=self.dtype, event="push_events",
                              is_allowed=self.kwargs.get("fisallowed"),
                              callback=self.callback, errback=self.errback)
        dct[attr_data_name(key)] = prop
        # Attribute
        dct[key] = attribute(fget=prop.read, **self.kwargs)
        dct["_class_dict"]["attributes"][key] = self


class logical_attribute(local_attribute):
    """Tango attribute computed from the values of other attributes.

    Use it as a decorator to register the function that make this computation.
    The decorated method take the attribute value dictionnary as argument.
    Logical attributes also support the standard attribute keywords.
    """

    def __call__(self, method):
        """Decorator support."""
        self.method = method
        return self


# Proxy attribute object
class proxy_attribute(logical_attribute, proxy):
    """Tango attribute linked to the attribute of a remote device.

    Args:
        device (str):
            Name of the property that contains the device name.
        prop (str):
            Name of the property containing the attribute name.
            None to not use a property (None by default).
        attr (str):
            Name of the attribute to forward. If `prop` is specified,
            `attr` is the default property value (None by default).

    A ValueError is raised if neither of `prop` or `attr` is specified.
    Also supports the standard attribute keywords.
    """

    def __init__(self, device, attr=None, prop=None, **kwargs):
        """Initialize the proxy attribute.

        Args:
            device (str):
                Name of the property that contains the device name.
            prop (str):
                Name of the property containing the attribute name.
                None to not use a property (None by default).
            attr (str):
                Name of the attribute to forward. If `prop` is specified,
                `attr` is the default property value (None by default).

        A ValueError is raised if neither of `prop` or `attr` is specified.
        Also supports the standard attribute keywords.
        """
        logical_attribute.__init__(self, **kwargs)
        proxy.__init__(self, device)
        if not (attr or prop):
            raise ValueError(
                "Either attr or prop argument has to be specified "
                "to initialize a {0}".format(type(self).__name__))
        self.attr = attr
        self.prop = prop

    def update_class(self, key, dct):
        """Create properties, attribute and read method.

        Also register useful informations in the property dictionary.
        """
        # Parent method
        logical_attribute.update_class(self, key, dct)
        proxy.update_class(self, key, dct)
        # Create device property
        doc = "Attribute of '{0}' forwarded as {1}.".format(self.device, key)
        if self.prop:
            dct[self.prop] = device_property(dtype=str, doc=doc,
                                             default_value=self.attr)
        # Read-only
        if not self.writable:
            return
        # Custom write
        if dct.get("is_" + key + "_allowed") or \
           set(self.kwargs) & set(["fwrite", "fset"]):
            return

        # Write method
        def write(device, value):
            proxy_name = device._device_dict[key]
            device_proxy = device._proxy_dict[proxy_name]
            proxy_attr = device._attribute_dict[key]
            device_proxy.write_attribute(proxy_attr, value)
        dct[key] = dct[key].setter(write)

    @property
    def writable(self):
        return self.kwargs.get("access") == AttrWriteType.READ_WRITE or \
            set(self.kwargs) & set(["fwrite", "fset"])


# Block attribute object
class block_attribute(proxy_attribute):
    """Tango attribute to gather several attributes of a remote device
    using a common prefix.

    Args:
        device (str):
            Name of the property that contains the device name.
        prop (str):
            Name of the property containing the attribute prefix.
            None to not use a property (None by default).
        attr (str):
            Prefix of the attributes to forward. If `prop` is specified,
            `attr` is the default property value (None by default).

    A ValueError is raised if neither of `prop` or `attr` is specified.
    Also supports the standard attribute keywords.
    """

    def __init__(self, device, attr=None, prop=None, **kwargs):
        """Initialize the block attribute.

        Args:
            device (str):
                Name of the property that contains the device name.
            prop (str):
                Name of the property containing the attribute prefix.
                None to not use a property (None by default).
            attr (str):
                Prefix of the attributes to forward. If `prop` is specified,
                `attr` is the default property value (None by default).

        A ValueError is raised if neither of `prop` or `attr` is specified.
        Also supports the standard attribute keywords.
        """
        kwargs.setdefault('dtype', self.dtype)
        kwargs.setdefault('max_dim_x', 5)
        kwargs.setdefault('max_dim_y', 1000)
        proxy_attribute.__init__(self, device, attr, prop, **kwargs)
        if self.writable:
            raise ValueError("A block attribute has to be read-only")

    def update_class(self, key, dct):
        """Create the attribute and read method."""
        proxy_attribute.update_class(self, key, dct)
        self.method = self.make_method(key)

    def __call__(self, *args, **kwargs):
        raise TypeError("A block attribute cannot be used as a decorator")

    @classmethod
    def make_method(cls, key):
        def update(self, data):
            device = self._device_dict[key]
            attrs = self._block_dict[device][key]
            return [(cls.format_name(attr),) + cls.format_value(data[attr])
                    for attr in attrs]
        return update

    @staticmethod
    def format_name(name):
        return name.split('.')[-1].replace('__', '.')

    @staticmethod
    def format_value(value):
        return (str(value.value), str(value.quality),
                str(value.type), str(value.time))

    @property
    def dtype(self):
        return ((str,),)

    @dtype.setter
    def dtype(self, value):
        if value != self.dtype:
            raise ValueError("A block attribute has to be an image of string")


# Proxy command object
class proxy_command(proxy):
    """Command to write an attribute or run a command
    of a remote device with a given value.

    Args:
        device (str):
            Name of the property that contains the device name.
        prop (str):
            Name of the property containing the attribute or command name.
            None to not use a property (None by default)
        attr (str):
            Name of the attribute to write.
            If `prop` is specified, `attr` is the default property value.
            `attr` can be True to indicate attribute mode without specifiying
            a default value.
        cmd (str):
            Name of the command to run.
            If `prop` is specified, `cmd` is the default property value.
            `cmd` can be True to indicate command mode without specifiying
            a default value
        value (any type):
            The value to write the attribute or send to the command.
            None by default, to run a command with no argument.
        reset_value (any type):
            An optional value to write the attribute or send to the command
            after the `value`. Typically used to reset a flag in a PLC.
            None by default, to not perform a reset action.
        reset_delay (float):
            Delay in seconds between the set and the reset actions.
            Default is 0; ignored if no `reset_value` given.


    A ValueError is raised if neither of `attr` or `cmd` is specified.
    A ValueError is raised if both `attr` and `cmd` are specified.
    Also supports the standard command keywords.

    If dtype_in is defined, the command argument is given to the
    sub-command or used to write the sub0attribute.

    If dtype_out is defined, the command returns the result of the last
    sub-command, or the value of the attribute after it's been written.
    """

    void = CmdArgType.DevVoid

    def __init__(self, device, attr=None, cmd=None, prop=None,
                 dtype_in=None, dtype_out=None,
                 value=None, reset_value=None, reset_delay=0, **kwargs):
        """Initialize the proxy command.

        Args:
            device (str):
                Name of the property that contains the device name.
            prop (str):
                Name of the property containing the attribute or command name.
                None to not use a property (None by default)
            attr (str):
                Name of the attribute to write.
                If `prop` is specified, `attr` is the default property value.
                `attr` can be True to indicate attribute mode without
                specifiying a default value.
            cmd (str):
                Name of the command to run.
                If `prop` is specified, `cmd` is the default property value.
                `cmd` can be True to indicate command mode without specifiying
                a default value
            value (any type):
                The value to write the attribute or send to the command.
                None by default, to run a command with no argument.
            reset_value (any type):
                An optional value to write the attribute or send to the command
                after the `value`. Typically used to reset a flag in a PLC.
                None by default, to not perform a reset action.
            reset_delay (float):
                Delay in seconds between the set and the reset actions.
                Default is 0; ignored if no `reset_value` given.


        A ValueError is raised if neither of `attr` or `cmd` is specified.
        A ValueError is raised if both `attr` and `cmd` are specified.
        Also supports the standard command keywords.

        If dtype_in is defined, the command argument is given to the
        sub-command or used to write the sub-attribute.

        If dtype_out is defined, the command returns the result of the last
        sub-command, or the value of the attribute after it's been written.
        """
        proxy.__init__(self, device)
        # Cast dtype
        if dtype_in == self.void:
            dtype_in = None
        if dtype_out == self.void:
            dtype_out = None
        # Check arguments
        if attr and cmd:
            raise ValueError(
                "Both attr and cmd arguments can't be specified "
                "to initialize a proxy_command")
        if not (attr or cmd):
            raise ValueError(
                "Either attr or cmd argument has to be specified "
                "to initialize a proxy_command")
        if value is not None and dtype_in is not None:
            raise ValueError(
                "Both dtype_in and value can't be specified "
                "to initialize a proxy_command")
        if bool(attr) and value is None and dtype_in is None:
            raise ValueError(
                "value or dtype_in has to be specified "
                "when the command is linked to an attribute")
        # Save arguments
        self.dtype_in = kwargs['dtype_in'] = dtype_in
        self.dtype_out = kwargs['dtype_out'] = dtype_out
        self.kwargs = kwargs
        self.value = value
        self.cmd = cmd
        self.attr = attr
        self.prop = prop
        self.is_attr = bool(attr)
        self.reset_value = reset_value
        self.reset_delay = reset_delay

    def update_class(self, key, dct):
        """Create the command, methods and device properties."""
        # Register
        proxy.update_class(self, key, dct)
        dct["_class_dict"]["commands"][key] = self

        # Command method
        def run_command(device, arg=None):
            """Write the attribute of the remote device with the value."""
            # Get data
            name, is_attr, value, reset, delay = device._command_dict[key]
            # Get value
            if self.dtype_in:
                value = arg
            # Check attribute
            if name.strip().lower() == NONE_STRING:
                if is_attr:
                    msg = "No attribute to write for commmand {0}"
                else:
                    msg = "No sub-command to run for command {0}"
                raise ValueError(msg.format(key))
            # Prepare
            proxy_name = device._device_dict[key]
            device_proxy = device._proxy_dict[proxy_name]
            if is_attr:
                write = device_proxy.write_attribute
            else:
                write = device_proxy.command_inout
            # Write
            result = write(name, value)
            # Reset
            if reset is not None:
                time.sleep(delay)
                result = write(name, reset)
            # Return
            if not self.dtype_out:
                return
            if not is_attr:
                return result
            # Read attribute
            result = device_proxy.read_attribute(name)
            return result.value

        # Set command
        cmd = command(**self.kwargs)
        run_command.__name__ = key
        if self.is_attr:
            doc = "Write the attribute '{0}' of '{1}' with value {2}"
            run_command.__doc__ = doc.format(self.prop or self.attr,
                                             self.device, self.value)
        else:
            doc = "Run the command '{0}' of '{1}' with value {2}"
            run_command.__doc__ = doc.format(self.prop or self.cmd,
                                             self.device, self.value)
        dct[key] = cmd(run_command)

        # Is allowed method
        def is_allowed(device):
            """The method is allowed if the device is connected."""
            return device.connected

        # Set is allowed method
        method_name = "is_" + key + "_allowed"
        if method_name not in dct:
            is_allowed.__name__ = method_name
            dct[method_name] = is_allowed

        # Create properties
        if self.prop:
            default = self.attr if self.is_attr else self.cmd
            if not isinstance(default, basestring):
                default = None
            if self.is_attr:
                doc = "Attribute of '{0}' to write "
            else:
                doc = "Command of '{0}' to run "
            doc += "when command {1} is executed"
            dct[self.prop] = device_property(dtype=str, default_value=default,
                                             doc=doc.format(self.device, key))


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
