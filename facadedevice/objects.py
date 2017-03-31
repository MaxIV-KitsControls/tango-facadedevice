"""Provide class objects for the facade device."""

# Imports
from functools import partial

# Tango imports
from tango import AttrWriteType
from tango.server import device_property, command, attribute

# Local imports
from facadedevice.graph import RestrictedNode
from facadedevice.utils import attributes_from_wildcard
from facadedevice.utils import check_attribute, make_subcommand

# Constants

NONE_STRING = "none"


# Base class object

class class_object(object):
    """Provide a base for objects to be processed by ProxyMeta."""

    # Methods to override

    def update_class(self, key, dct):
        self.key = key

    def configure(self, device):
        pass  # pragma: no cover

    def connect(self, device):
        pass  # pragma: no cover

    # Representation

    def __repr__(self):
        key = self.key if self.key else "unnamed"
        return "{} <{}>".format(type(self).__name__, key)


# Node object

class node_object(class_object):

    callback = None

    def notify(self, callback):
        """Use as a decorator to register a callback."""
        self.callback = callback
        return callback

    def configure(self, device):
        node = RestrictedNode(self.key)
        device.graph.add_node(node)
        # No user callback
        if not self.callback:
            return
        # Add user callback
        node.callbacks.append(partial(
            device.run_callback,
            "running user callback for",
            self.callback.__get__(device)))

    # Binding helper

    @staticmethod
    def bind_node(device, node, bind, method):
        if not method:
            raise ValueError('No update method defined')
        if not bind:
            raise ValueError('No binding defined')
        # Set the binding
        func = partial(
            device.aggregate_for_node,
            node,
            method.__get__(device))
        device.graph.add_rule(node, func, bind)


# Local attribute

class local_attribute(node_object):
    """Tango attribute with event support.

    Local attributes support the standard attribute keywords.

    Args:
        callback (str or function): method to call when the attribute changes.
             It is called with the corresponding node as an argument
    """

    def __init__(self, create_attribute=True, **kwargs):
        if not create_attribute and kwargs:
            raise ValueError("Attribute creation is disabled")
        self.kwargs = kwargs if create_attribute else None

    # Properties

    @property
    def use_default_write(self):
        return (self.kwargs is not None and
                self.kwargs.get('access') == AttrWriteType.READ_WRITE and
                not set(self.kwargs) & set(['fwrite', 'fset']))

    # Configuration methods

    def update_class(self, key, dct):
        super(local_attribute, self).update_class(key, dct)
        # Attribute creation disabled
        if self.kwargs is None:
            return
        kwargs = dict(self.kwargs)
        # Read method
        kwargs['fget'] = lambda device, attr=None: \
            device.read_from_node(device.graph[key], attr)
        # Is allowed method
        method_name = "is_" + key + "_allowed"
        if method_name not in dct:
            dct[method_name] = lambda device, attr: device.connected
            dct[method_name].__name__ = method_name
        # Create attribute
        dct[key] = attribute(**kwargs)
        # Read-only
        if not self.use_default_write:
            return
        # Set write method
        dct[key] = dct[key].setter(
            lambda device, value:
                device.write_to_node(device.graph[key], value))

    def configure(self, device):
        # Build node
        super(local_attribute, self).configure(device)
        node = device.graph[self.key]
        # Attribute creation disabled
        if self.kwargs is None:
            return
        # Configure events
        attr = getattr(device, self.key)
        attr.set_archive_event(True, True)
        attr.set_change_event(True, False)
        # Add push event callback
        node.callbacks.append(partial(
            device.run_callback,
            "pushing events for",
            device.push_event_for_node))


# Logical attribute

class logical_attribute(local_attribute):
    """Tango attribute computed from the values of other attributes.

    Use it as a decorator to register the function that make this computation.
    Logical attributes also support the standard attribute keywords.
    """

    def __init__(self, bind, create_attribute=True, **kwargs):
        self.bind = bind
        self.method = None
        super(logical_attribute, self).__init__(
            create_attribute=create_attribute, **kwargs)

    def __call__(self, method):
        self.method = method
        return self

    def configure(self, device):
        super(logical_attribute, self).configure(device)
        node = device.graph[self.key]
        self.configure_binding(device, node)

    def configure_binding(self, device, node):
        self.bind_node(device, node, self.bind, self.method)


# Proxy attribute

class proxy_attribute(logical_attribute):
    """Tango attribute linked to the attribute of a remote device.

    Args:
        property_name (str):
            Name of the property containing the attribute name.
        create_property (str):
            Create the corresponding device property. Default is True.

    Also supports the standard attribute keywords.
    """

    def __init__(self, property_name,
                 create_property=True, create_attribute=True,
                 **kwargs):
        self.property_name = property_name
        self.create_property = create_property
        super(proxy_attribute, self).__init__(
            None, create_attribute=create_attribute, **kwargs)

    def update_class(self, key, dct):
        # Parent method
        super(proxy_attribute, self).update_class(key, dct)
        # Create device property
        if self.create_property:
            doc = "Attribute to be forwarded as {}.".format(key)
            dct[self.property_name] = device_property(dtype=str, doc=doc)
        # Read-only or custom write
        if not self.use_default_write:
            return
        # Set write method
        factory = partial(make_subcommand, attr=True)
        dct[key] = dct[key].setter(
            lambda device, value:
                device.run_proxy_command(
                    factory, self.property_name, value))

    def configure_binding(self, device, node):
        # Get properties
        attr = getattr(device, self.property_name).strip().lower()
        # Ignore attribute
        if attr == NONE_STRING:
            node.subnodes = []
            return
        # Check attribute
        check_attribute(attr, writable=self.use_default_write)
        # Add attribute
        if self.method is None:
            node.remote_attr = attr
            node.subnodes = [node]
            return
        # Add subnode
        bind = (self.key + "[0]",)
        subnode = RestrictedNode(bind[0])
        subnode.remote_attr = attr
        node.subnodes = [subnode]
        device.graph.add_node(subnode)
        # Binding
        self.bind_node(device, node, bind, self.method)

    def connect(self, device):
        # Get node
        node = device.graph[self.key]
        # Subscribe
        for subnode in node.subnodes:
            device.subscribe_for_node(subnode.remote_attr, subnode)


# Combined attribute

class combined_attribute(proxy_attribute):
    """Tango attribute computed from the values of other remote attributes.

    Use it as a decorator to register the function that make this computation.
    The remote attribute names are provided by a property, either as a list or
    a pattern.

    Args:
        property_name (str):
            Name of the property containing the attribute names.
        create_property (str):
            Create the corresponding device property. Default is True.
        create_attribute (str):
            Create the corresponding tango attribute. Default is True.

    Also supports the standard attribute keywords.
    """

    def update_class(self, key, dct):
        # Parent method
        super(combined_attribute, self).update_class(key, dct)
        # Check write access
        if self.use_default_write:
            raise ValueError('{} cannot be writable'.format(self))
        # Override device property
        if self.create_property:
            doc = "Attributes to be combined as {}.".format(key)
            dct[self.property_name] = device_property(dtype=(str,), doc=doc)

    def configure_binding(self, device, node):
        # Init subnodes
        node.subnodes = []
        # Strip property
        attrs = getattr(device, self.property_name)
        attrs = list(filter(None, map(str.strip, map(str.lower, attrs))))
        # Empty property
        if not attrs:
            msg = 'Property {!r} is empty'
            raise ValueError(msg.format(self.property_name))
        # Ignore attribute
        if len(attrs) == 1 and attrs[0] == NONE_STRING:
            return
        # Pattern matching
        if len(attrs) == 1:
            wildcard = attrs[0]
            attrs = list(attributes_from_wildcard(wildcard))
            if not attrs:
                msg = 'No attributes matching {} wildcard'
                raise ValueError(msg.format(wildcard))
        # Check attributes
        else:
            for attr in attrs:
                check_attribute(attr)
        # Build the subnodes
        for i, attr in enumerate(attrs):
            subnode = RestrictedNode('{}[{}]'.format(self.key, i))
            subnode.remote_attr = attr
            device.graph.add_node(subnode)
            node.subnodes.append(subnode)
        # Set the binding
        bind = tuple(subnode.name for subnode in node.subnodes)
        self.bind_node(device, node, bind, self.method)


# State attribute

class state_attribute(node_object):
    """Tango state attribute with event support."""

    def __init__(self, bind=None):
        self.bind = bind
        self.method = None

    def __call__(self, method):
        self.method = method
        return self

    def update_class(self, key, dct):
        super(state_attribute, self).update_class(key, dct)
        # Restore method
        if self.method:
            self.method.bind = self.bind
            dct[key] = self.method

    def configure(self, device):
        # Parent call
        super(state_attribute, self).configure(device)
        node = device.graph[self.key]
        # Add set state callback
        node.callbacks.append(partial(
            device.run_callback,
            "setting the state from",
            device.set_state_from_node))
        # Nothing to bind
        if not self.bind and not self.method:
            return
        # Bind node
        self.bind_node(device, node, self.bind, self.method)


# Proxy command

class proxy_command(class_object):
    """Command to write an attribute or run a command of a remote device.

    It can be used as a decorator to define a more precise behavior.
    The decorated method takes the subcommand as its firt argument.

    Args:
        property_name (str):
            Name of the property containing the attribute or command name.
        create_property (str):
            Create the corresponding device property. Default is True.
        write_attribute (bool):
            True if the subcommand should an attribute write, False otherwise.
            Default is false.

    Also supports the standard command keywords.
    """

    def __init__(self, property_name, create_property=True,
                 write_attribute=False, **kwargs):
        self.kwargs = kwargs
        self.property_name = property_name
        self.create_property = create_property
        self.write_attribute = write_attribute
        # Default method
        self.method = lambda device, sub, *args: sub(*args)

    def __call__(self, method):
        self.method = method
        return self

    def update_class(self, key, dct):
        # Set command
        factory = partial(make_subcommand, attr=self.write_attribute)
        dct[key] = lambda device, *args: \
            device.run_proxy_command_context(
                factory, self.property_name,
                self.method.__get__(device), *args)
        dct[key].__name__ = key
        dct[key] = command(**self.kwargs)(dct[key])
        # Set is allowed method
        method_name = "is_" + key + "_allowed"
        if method_name not in dct:
            dct[method_name] = lambda device: device.connected
            dct[method_name].__name__ = method_name
        # Create property
        if self.create_property:
            doc = ("Attribute to be written"
                   if self.write_attribute else
                   "Subcommand to be executed")
            doc += " in {} command.".format(key)
            dct[self.property_name] = device_property(dtype=str, doc=doc)

    def configure(self, device):
        name = getattr(device, self.property_name).strip().lower()
        # Disabled command
        if name == NONE_STRING:
            return
        # Check subcommand
        make_subcommand(name, attr=self.write_attribute)
