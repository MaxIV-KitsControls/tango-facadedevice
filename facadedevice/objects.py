"""Provide class objects for the facade device."""

# Imports
from ast import literal_eval
from functools import partial

# Tango imports
from tango import AttrWriteType
from tango.server import device_property, command, attribute

# Local imports
from facadedevice.graph import RestrictedNode, triplet
from facadedevice.utils import attributes_from_wildcard
from facadedevice.utils import check_attribute, make_subcommand


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
            device._run_callback,
            "running user callback for",
            self.callback.__get__(device)))

    # Binding helper

    @staticmethod
    def bind_node(device, node, bind, method, standard_aggregation=True):
        if not method:
            raise ValueError('No update method defined')
        if not bind:
            raise ValueError('No binding defined')
        # Set the binding
        aggregate = (
            device._standard_aggregation if standard_aggregation
            else device._custom_aggregation)
        func = partial(aggregate, node, method.__get__(device))
        device.graph.add_rule(node, func, bind)


# Local attribute

class local_attribute(node_object):
    """Tango attribute with event support.

    Local attributes support the standard attribute keywords.

    It can be used as a decorator to set a method providing the
    default value for the corresponding attribute.

    Args:
        create_attribute (str):
            Create the corresponding tango attribute. Default is True.
    """

    def __init__(self, create_attribute=True, **kwargs):
        if not create_attribute and kwargs:
            raise ValueError("Attribute creation is disabled")
        self.method = None
        self.kwargs = kwargs if create_attribute else None

    def __call__(self, method):
        self.method = method
        return self

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
            device._read_from_node(device.graph[key], attr)
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
                device._write_to_node(device.graph[key], value))

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
            device._run_callback,
            "pushing events for",
            device._push_event_for_node))

    def connect(self, device):
        if not self.method:
            return
        # Get method
        node = device.graph[self.key]
        get_default = self.method.__get__(device)
        # Get default result
        try:
            result = get_default()
            if not isinstance(result, triplet):
                result = triplet(result)
        # Set exception
        except Exception as exc:
            node.set_exception(exc)
        # Set result
        else:
            node.set_result(result)


# Logical attribute

class logical_attribute(local_attribute):
    """Tango attribute computed from the values of other attributes.

    Use it as a decorator to register the function that make this computation.
    Logical attributes also support the standard attribute keywords.

    Args:
        bind (list of str):
            List of node names to bind to. It has to contain at least one name.
        standard_aggregation (optional, bool):
            Use the default aggregation mecanism. Default is True.
        create_attribute (optional, bool):
            Create the corresponding tango attribute. Default is True.
    """

    def __init__(self, bind, standard_aggregation=True, **kwargs):
        self.bind = bind
        self.method = None
        self.standard_aggregation = standard_aggregation
        super(logical_attribute, self).__init__(**kwargs)

    def configure(self, device):
        super(logical_attribute, self).configure(device)
        node = device.graph[self.key]
        self.configure_binding(device, node)

    def configure_binding(self, device, node):
        self.bind_node(
            device, node, self.bind, self.method, self.standard_aggregation)

    def connect(self, device):
        # Override the local_attribute connect method
        pass


# Proxy attribute

class proxy_attribute(logical_attribute):
    """Tango attribute linked to the attribute of a remote device.

    Args:
        property_name (str):
            Name of the property containing the attribute name.
        create_property (optional, bool):
            Create the corresponding device property. Default is True.
        standard_aggregation (optional, bool):
            Use the default aggregation mecanism. Default is True.
        create_attribute (optional, bool):
            Create the corresponding tango attribute. Default is True.

    Also supports the standard attribute keywords.
    """

    def __init__(self, property_name, create_property=True, **kwargs):
        self.property_name = property_name
        self.create_property = create_property
        super(proxy_attribute, self).__init__(None, **kwargs)

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
        dct[key] = dct[key].setter(
            lambda device, value:
                device._run_proxy_command(
                    key, value))

    def configure_binding(self, device, node):
        # Get properties
        attr = getattr(device, self.property_name).strip()
        # Empty property
        if not attr:
            msg = 'Property {!r} is empty'
            raise ValueError(msg.format(self.property_name))
        # Default value
        if '/' not in attr:
            node.default_value = literal_eval(attr)
            # Make subcommand
            if self.use_default_write:
                subcommand = partial(device._write_to_node, node)
                device._subcommand_dict[self.key] = subcommand
            return
        # Check attribute
        attr = attr.lower()
        check_attribute(attr, writable=self.use_default_write)
        # Make subcommand
        if self.use_default_write:
            subcommand = make_subcommand(attr, attr=True)
            device._subcommand_dict[self.key] = subcommand
        # Add attribute
        if self.method is None:
            node.remote_attr = attr
            return
        # Add subnode
        bind = (self.key + "[0]",)
        subnode = RestrictedNode(bind[0])
        subnode.remote_attr = attr
        device.graph.add_node(subnode)
        # Binding
        self.bind_node(
            device, node, bind, self.method, self.standard_aggregation)

    def connect(self, device):
        node = device.graph[self.key]
        # Set default_value
        if hasattr(node, 'default_value'):
            node.set_result(triplet(node.default_value))
        # Get subnodes
        if hasattr(node, 'remote_attr'):
            subnodes = [node]
        else:
            subnodes = device.graph.subnodes(self.key)
        # Subscribe
        for subnode in subnodes:
            device._subscribe_for_node(subnode.remote_attr, subnode)


# Combined attribute

class combined_attribute(proxy_attribute):
    """Tango attribute computed from the values of other remote attributes.

    Use it as a decorator to register the function that make this computation.
    The remote attribute names are provided by a property, either as a list or
    a pattern.

    Args:
        property_name (str):
            Name of the property containing the attribute names.
        create_property (optional, bool):
            Create the corresponding device property. Default is True.
        standard_aggregation (optional, bool):
            Use the default error aggregation mecanism. Default is True.
        create_attribute (optional, bool):
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
        # Strip property
        attrs = getattr(device, self.property_name)
        if not isinstance(attrs, str):
            attrs = '\n'.join(attrs)
        attrs = attrs.strip()
        # Empty property
        if not attrs:
            msg = 'Property {!r} is empty'
            raise ValueError(msg.format(self.property_name))
        # Default value
        if '/' not in attrs:
            node.default_value = literal_eval(attrs)
            return
        # Split lines
        attrs = attrs.lower().splitlines()
        attrs = list(filter(None, map(str.strip, attrs)))
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
        # Build the bindings
        bind = tuple(
            '{}[{}]'.format(self.key, i)
            for i, _ in enumerate(attrs))
        # Build the subnodes
        for key, attr in zip(bind, attrs):
            subnode = RestrictedNode(key)
            subnode.remote_attr = attr
            device.graph.add_node(subnode)
        # Set the binding
        self.bind_node(
            device, node, bind, self.method, self.standard_aggregation)


# State attribute

class state_attribute(node_object):
    """Tango state attribute with event support.

    Args:
        bind (list of str):
            List of node names to bind to, or None to disable the binding.
            Default is None.
        standard_aggregation (optional, bool):
            Use the default error aggregation mecanism. Default is True.
    """

    def __init__(self, bind=None, standard_aggregation=True):
        self.bind = bind
        self.method = None
        self.standard_aggregation = standard_aggregation

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
            device._run_callback,
            "setting the state from",
            device._set_state_from_node))
        # Nothing to bind
        if not self.bind and not self.method:
            return
        # Bind node
        self.bind_node(
            device, node, self.bind, self.method, self.standard_aggregation)


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
        super(proxy_command, self).update_class(key, dct)
        # Set command
        dct[key] = lambda device, *args: \
            device._run_proxy_command_context(
                key, self.method.__get__(device), *args)
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
        name = getattr(device, self.property_name).strip()
        # Default value
        if '/' not in name:
            value = literal_eval(name)
            subcommand = partial(device._emulate_subcommand, value)
        # Check subcommand
        else:
            subcommand = make_subcommand(name, attr=self.write_attribute)
        # Set subcommand
        device._subcommand_dict[self.key] = subcommand
