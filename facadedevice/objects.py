"""Provide class objects for the facade device."""

# Imports
import time
from functools import partial

from tango import AttributeProxy
from tango import AttrWriteType, CmdArgType, DevState
from tango.server import device_property, command, attribute

from facadedevice.base import Node, triplet
from facadedevice.common import aggregate_qualities, NONE_STRING


# Aggregation

def aggregate(logger, func, *nodes):
    results = [node.result() for node in nodes]
    values, stamps, qualities = zip(*results)
    try:
        result = func(*values)
    except Exception as exc:
        logger(exc)
        raise exc
    if isinstance(result, triplet):
        return result
    stamp = max(stamps)
    quality = aggregate_qualities(qualities)
    return triplet(result, stamp, quality)


# Base class object

class class_object(object):
    """Provide a base for objects to be processed by ProxyMeta."""

    # Methods to override

    def update_class(self, key, dct):
        self.key = key

    def configure(self, device):
        pass

    def connect(self, device):
        pass


# State attribute


class state_attribute(class_object):
    """Tango state attribute with event support."""

    def __init__(self, bind=None):
        self.bind = bind
        self.method = None

    def __call__(self, method):
        """Decorator support"""
        self.method = method
        return self

    # Device methods

    def set_state(self, device, node):
        try:
            if node.exception() is not None:
                device.set_state(DevState.FAULT)
                device.set_status("Error: {!r}".format(node.exception()))
            else:
                value, stamp, quality = node.result()
                try:
                    state, status = value
                except ValueError:
                    state, status = value, "The state is {}".format(value)
                device.set_state(state, stamp, quality)
                device.set_status(status, stamp, quality)
        except Exception as exc:
            device.ignore_exception(exc)

    # Configuration methods

    def update_class(self, key, dct):
        """Create the attribute and read method."""
        super(state_attribute, self).update_class(key, dct)
        dct['_class_dict'][key] = self

    def configure(self, device):
        node = Node(self.key)
        node.callbacks.append(partial(self.set_state, device))
        device.graph.add_node(node)
        if self.method and self.bind:
            msg = "Error while updating {!r}".format(node)
            logger = partial(device.ignore_exception, msg=msg)
            func = partial(aggregate, logger, self.method.__get__(device))
            device.graph.add_rule(node, func, self.bind)


# Local attribute

class local_attribute(class_object):
    """Tango attribute with event support.

    Local attributes support the standard attribute keywords.

    Args:
        callback (str or function): method to call when the attribute changes.
             It is called with the corresponding node as an argument
    """

    def __init__(self, callback=None, **kwargs):
        self.kwargs = kwargs
        self.dtype = self.kwargs['dtype']
        self.callback = None

    def notify(self, callback):
        """To use as a decorator to register a callback."""
        self.callback = callback
        return callback

    def run_callback(self, device, node):
        try:
            device.push_event_for_node(node)
        except Exception as exc:
            msg = "Error while pushing event for {!r}"
            device.ignore_exception(exc, msg.format(node))
        try:
            if self.callback:
                self.callback.__get__(device)(node)
        except Exception as exc:
            msg = "Error while running user callback for {!r}"
            device.ignore_exception(exc, msg.format(node))

    # Properties

    @property
    def writable(self):
        return self.kwargs.get('access') == AttrWriteType.READ_WRITE or \
               self.custom_writable

    @property
    def custom_writable(self):
        return set(self.kwargs) & set(['fwrite', 'fset'])

    # Configuration methods

    def update_class(self, key, dct):
        """Create the attribute and read method."""
        super(local_attribute, self).update_class(key, dct)

        kwargs = dict(self.kwargs)

        def read(device, attr=None):
            value, stamp, quality = device.graph[key].result()
            if attr:
                attr.set_value_date_quality(value, stamp, quality)
            return value, stamp, quality
        kwargs['fget'] = read

        if self.writable and not self.custom_writable:
            def write(device, value):
                device.graph[key].set_result()
            kwargs['fset'] = write

        dct[key] = attribute(**kwargs)
        dct['_class_dict'][key] = self

    def configure(self, device):
        node = Node(self.key)
        node.callbacks.append(partial(self.run_callback, device))
        device.graph.add_node(node)


# Logical attribute

class logical_attribute(local_attribute):
    """Tango attribute computed from the values of other attributes.

    Use it as a decorator to register the function that make this computation.
    The decorated method take the attribute value dictionnary as argument.
    Logical attributes also support the standard attribute keywords.
    """

    def __init__(self, bind, **kwargs):
        self.bind = bind
        self.method = None
        local_attribute.__init__(self, **kwargs)

    def __call__(self, method):
        """Decorator support."""
        self.method = method


# Proxy attribute

class proxy_attribute(local_attribute):
    """Tango attribute linked to the attribute of a remote device.

    Args:
        prop (str):
            Name of the property containing the attribute name.

    Also supports the standard attribute keywords.
    """

    def __init__(self, prop, **kwargs):
        super(proxy_attribute, self).__init__(**kwargs)
        self.prop = prop

    def update_class(self, key, dct):
        """Create properties, attribute and read method.

        Also register useful informations in the property dictionary.
        """
        # Parent method
        super(proxy_attribute, self).update_class(key, dct)

        # Create device property
        doc = "Attribute to be forwarded as {}.".format(key)
        dct[self.prop] = device_property(dtype=str, doc=doc)

        # Read-only
        if not self.writable or self.custom_writable:
            return

        # Write method

        def write(device, value):
            attr = getattr(device, self.prop)
            proxy = AttributeProxy(attr)
            proxy.write(value)

        # Set write method
        dct[key] = dct[key].setter(write)

    # Device methods

    def configure(self, device):
        # Parent call
        super(proxy_attribute, self).configure(device)
        # Get node
        node = device.graph[self.key]
        # Get properties
        attr = getattr(device, self.prop).strip().lower()
        # Ignore attribute
        if attr == NONE_STRING:
            node.remote_attr = None
        # Add attribute
        else:
            node.remote_attr = attr

    def connect(self, device):
        # Get node
        node = device.graph[self.key]
        # Subscribe
        device.subscribe(node.remote_attr, node)


# Proxy command object
class proxy_command(class_object):
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
        self.device = device
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
