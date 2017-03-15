"""Provide class objects for the facade device."""

# Imports
from functools import partial

from tango import AttrWriteType
from tango.server import device_property, command, attribute

from facadedevice.base import RestrictedNode
from facadedevice.common import NONE_STRING


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
            self.callback.__get__(device)(node)))


# Logical object

class logical_object(node_object):
    """Logical object."""

    method = None

    def __init__(self, bind=None):
        self.bind = bind

    def __call__(self, method):
        self.method = method
        return self

    # Configuration methods

    def configure(self, device):
        super(logical_object, self).configure(device)
        node = device.graph[self.key]
        # Check values
        if self.bind and not self.method:
            raise ValueError('No update method defined')
        if not self.bind and self.method:
            raise ValueError('Update method not bound')
        # Add aggregation rule
        if self.bind and self.method:
            func = partial(
                device.aggregate_for_node,
                node,
                self.method.__get__(device))
            device.graph.add_rule(node, func, self.bind)


# State attribute

class state_attribute(logical_object):
    """Tango state attribute with event support."""

    def configure(self, device):
        super(state_attribute, self).configure(device)
        node = device.graph[self.key]
        # Add set state callback
        node.callbacks.append(partial(
            device.run_callback,
            "setting the state from",
            device.set_state_from_node))


# Local attribute

class local_attribute(node_object):
    """Tango attribute with event support.

    Local attributes support the standard attribute keywords.

    Args:
        callback (str or function): method to call when the attribute changes.
             It is called with the corresponding node as an argument
    """

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    # Properties

    @property
    def writable(self):
        return (self.kwargs.get('access') == AttrWriteType.READ_WRITE or
                self.custom_writable)

    @property
    def custom_writable(self):
        return set(self.kwargs) & set(['fwrite', 'fset'])

    # Configuration methods

    def update_class(self, key, dct):
        """Create the attribute and read method."""
        super(local_attribute, self).update_class(key, dct)
        kwargs = dict(self.kwargs)
        # Read method
        kwargs['fget'] = lambda device, attr=None: \
            device.read_from_node(device.graph[key], attr)
        # Create attribute
        dct[key] = attribute(**kwargs)
        # Read-only
        if not self.writable or self.custom_writable:
            return
        # Set write method
        dct[key] = dct[key].setter(
            lambda device, value:
                device.write_to_node(device.graph[key], value))

    def configure(self, device):
        super(local_attribute, self).configure(device)
        node = device.graph[self.key]
        # Add push event callback
        node.callbacks.append(partial(
            device.run_callback,
            "pushing events for",
            device.push_event_for_node))


# Logical attribute

class logical_attribute(local_attribute, logical_object):
    """Tango attribute computed from the values of other attributes.

    Use it as a decorator to register the function that make this computation.
    Logical attributes also support the standard attribute keywords.
    """

    def __init__(self, bind, **kwargs):
        logical_object.__init__(self, bind)
        local_attribute.__init__(self, **kwargs)


# Proxy attribute

class proxy_attribute(logical_attribute):
    """Tango attribute linked to the attribute of a remote device.

    Args:
        prop (str):
            Name of the property containing the attribute name.

    Also supports the standard attribute keywords.
    """

    def __init__(self, prop, **kwargs):
        local_attribute.__init__(self, **kwargs)
        self.prop = prop

    @property
    def bind(self):
        return (self.key + "[0]",) if self.method else ()

    def update_class(self, key, dct):
        # Parent method
        super(proxy_attribute, self).update_class(key, dct)
        # Create device property
        doc = "Attribute to be forwarded as {}.".format(key)
        dct[self.prop] = device_property(dtype=str, doc=doc)
        # Read-only
        if not self.writable or self.custom_writable:
            return
        # Set write method
        dct[key] = dct[key].setter(
            lambda device, value:
                device.write_attribute_from_property(self.prop, value))

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
            node.subnode = None
            return
        # Add attribute
        if self.method is None:
            node.remote_attr = attr
            node.subnode = node
            return
        # Add subnode
        node.subnode = RestrictedNode(self.bind[0])
        device.graph.add_node(node.subnode)
        node.remote_attr = node.subnode.remote_attr = attr

    def connect(self, device):
        # Get node
        node = device.graph[self.key]
        # Ignore empty subnode
        if node.subnode is None:
            return
        # Subscribe
        device.subscribe_for_node(node.remote_attr, node.subnode)


# Combined attribute

class combined_attribute(logical_attribute):

    def __init__(self, prop, **kwargs):
        local_attribute.__init__(self, **kwargs)
        self.prop = prop
        if self.writable:
            raise ValueError('A combined attribute cannot be writable')

    def update_class(self, key, dct):
        # Parent method
        super(combined_attribute, self).update_class(key, dct)
        # Create device property
        doc = "Attributes to be combined as {}.".format(key)
        dct[self.prop] = device_property(dtype=(str,), doc=doc)

    def configure(self, device):
        # Check method
        if self.method is None:
            raise ValueError('Method not defined')
        # Skip parent call to set the binding later
        local_attribute.configure(self, device)
        # Get node
        node = device.graph[self.key]
        node.subnodes = []
        # Strip property
        attrs = getattr(device, self.prop)
        attrs = list(filter(None, map(str.strip, map(str.lower, attrs))))
        # Empty property
        if not attrs:
            raise ValueError('Property is empty')
        # Ignore attribute
        if len(attrs) == 1 and attrs[0] == NONE_STRING:
            return
        # Build the subnodes
        for i, attr in enumerate(check_attributes(attrs)):
            subnode = RestrictedNode('{}[{}]'.format(self.key, i))
            subnode.remote_attr = attr
            device.graph.add_node(subnode)
            node.subnodes.append(subnode)
        # Set the binding
        bind = tuple(node.name for node in node.subnodes)
        func = partial(self.aggregate, node, self.method.__get__(device))
        device.graph.add_rule(node, func, bind)

    def connect(self, device):
        # Get node
        node = device.graph[self.key]
        # Subscribe
        for subnode in node.subnodes:
            device.subscribe_for_node(subnode.remote_attr, subnode)


# Proxy command

class proxy_command(class_object):
    """Command to write an attribute or run a command of a remote device.

    It is meant to be used as a decorator

    Args:
        prop (str):
            Name of the property containing the attribute or command name.
            None to not use a property (None by default)
        attr (bool):
            True if the subcommand should an attribute write, False otherwise.
            Default is false.

    Also supports the standard command keywords.
    """

    method = None

    def __init__(self, prop, attr=False, **kwargs):
        self.prop = prop
        self.attr = attr
        self.kwargs = kwargs

    def __call__(self, method):
        self.method = method
        return self

    def run_command(self, device, func, *args):
        """Write the attribute of the remote device with the value."""
        name = getattr(device, self.prop)
        subcommand = make_subcommand(name, attr=self.attr)
        return func(subcommand, *args)

    def update_class(self, key, dct):
        # Check method
        if not self.method:
            raise ValueError('No method defined')
        # Set command
        decorator = command(**self.kwargs)
        dct[key] = decorator(
            lambda device, *args:
                self.run_command(device, self.method.__get__(device), *args))
        dct[key].__name__ = key
        # Set is allowed method
        method_name = "is_" + key + "_allowed"
        if method_name not in dct:
            dct[method_name] = lambda device: device.connected
            dct[method_name].__name__ = method_name
        # Create properties
        dct[self.prop] = device_property(dtype=str)

    def configure(self, device):
        name = getattr(device, self.prop)
        make_subcommand(name, attr=self.attr)
