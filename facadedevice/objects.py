"""Provide class objects for the facade device."""

# Imports
from functools import partial

# Tango imports
from tango import AttrWriteType
from tango.server import device_property, command, attribute

# Local imports
from facadedevice.graph import RestrictedNode

# Constants

NONE_STRING = "none"


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
            device.safe_callback,
            "running user callback for",
            self.callback.__get__(device)(node)))

    # Binding helper

    @staticmethod
    def bind_node(device, node, bind, method):
        if not method:
            raise ValueError('No update method defined')
        if not bind:
            raise ValueError('Update method not bound')
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
        super(local_attribute, self).update_class(key, dct)
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
            device.safe_callback,
            "pushing events for",
            device.push_event_for_node))


# Logical attribute

class logical_attribute(local_attribute):
    """Tango attribute computed from the values of other attributes.

    Use it as a decorator to register the function that make this computation.
    Logical attributes also support the standard attribute keywords.
    """

    def __init__(self, bind, **kwargs):
        self.bind = bind
        self.method = None
        super(logical_attribute, self).__init__(**kwargs)

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
        prop (str):
            Name of the property containing the attribute name.

    Also supports the standard attribute keywords.
    """

    def __init__(self, prop, **kwargs):
        self.prop = prop
        super(proxy_attribute, self).__init__(None, **kwargs)

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
                device.write_remote_attribute_from_property(self.prop, value))

    def configure_binding(self, device, node):
        # Get properties
        attr = getattr(device, self.prop).strip().lower()
        # Ignore attribute
        if attr == NONE_STRING:
            node.subnodes = []
            return
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

    def __init__(self, prop, **kwargs):
        super(combined_attribute, self).__init__(prop, **kwargs)
        if self.writable:
            raise ValueError('A combined attribute cannot be writable')

    def update_class(self, key, dct):
        # Parent method
        super(combined_attribute, self).update_class(key, dct)
        # Override device property
        doc = "Attributes to be combined as {}.".format(key)
        dct[self.prop] = device_property(dtype=(str,), doc=doc)

    def configure_binding(self, device, node):
        # Init subnodes
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
            device.safe_callback,
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

    def __init__(self, prop, attr=False, **kwargs):
        self.prop = prop
        self.attr = attr
        self.kwargs = kwargs
        self.method = None

    def __call__(self, method):
        self.method = method
        return self

    def update_class(self, key, dct):
        # Check method
        if not self.method:
            raise ValueError('No method defined')
        # Set command
        decorator = command(**self.kwargs)
        factory = partial(make_subcommand, attr=self.attr)
        dct[key] = decorator(
            lambda device, *args:
                device.run_proxy_command(
                    factory, self.prop, self.method.__get__(device), *args))
        dct[key].__name__ = key
        # Set is allowed method
        method_name = "is_" + key + "_allowed"
        if method_name not in dct:
            dct[method_name] = lambda device, attr: device.connected
            dct[method_name].__name__ = method_name
        # Create properties
        dct[self.prop] = device_property(dtype=str)

    def configure(self, device):
        # Check subcommand
        name = getattr(device, self.prop)
        make_subcommand(name, attr=self.attr)
