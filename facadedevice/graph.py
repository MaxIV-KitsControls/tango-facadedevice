"""Provide objects for building reactive graphs."""

# Imports

import time
import warnings
from functools import partial
from collections import Mapping, namedtuple, defaultdict

from numpy import array_equal
from tango import AttrQuality

# Constants

VALID = AttrQuality.ATTR_VALID
INVALID = AttrQuality.ATTR_INVALID


# Triplet object

triplet = namedtuple("triplet", ("value", "stamp", "quality"))


def new_triplet(cls, value, stamp=None, quality=VALID):
    if isinstance(value, triplet):
        raise TypeError("The value cannot be a triplet")
    if stamp is None:
        stamp = time.time()
    if not isinstance(stamp, float):
        raise TypeError("The timestamp is not a float")
    if not isinstance(quality, int):
        raise TypeError("The quality is not a integer")
    if value is None or quality == INVALID:
        value, quality = None, INVALID
    return cls.__rawnew__(cls, value, stamp, quality)


def compare_triplet(a, b):
    assert isinstance(a, triplet)
    try:
        value, stamp, quality = b
    except:
        return False
    return (a.stamp == stamp and
            a.quality == quality and
            array_equal(a.value, value))


def from_attr_value(cls, attr_value):
    return cls(attr_value.value, attr_value.time.totime(), attr_value.quality)


triplet.__rawnew__ = staticmethod(triplet.__new__)
triplet.__new__ = staticmethod(new_triplet)
triplet.__eq__ = compare_triplet
triplet.__ne__ = lambda self, arg: not self.__eq__(arg)
triplet.from_attr_value = classmethod(from_attr_value)


# Node object

class Node(object):

    def __init__(self, name, description=None, callbacks=()):
        self._result = None
        self._exception = None
        self.name = name
        self.description = description or name
        self.callbacks = list(callbacks)

    # Setters

    def set_result(self, result):
        diff = (
            self._exception is not None or
            self._result != result)
        self._result = result
        self._exception = None
        if diff:
            self.notify()

    def set_exception(self, exception):
        if not isinstance(exception, BaseException):
            raise TypeError('Not a valid exception')
        diff = (
            self._result is not None or
            self._exception != exception)
        self._result = None
        self._exception = exception
        if diff:
            self.notify()

    # Getters

    def result(self):
        if self._exception is not None:
            raise self._exception
        return self._result

    def exception(self):
        return self._exception

    # Notifying

    def notify(self):
        for callback in self.callbacks:
            try:
                callback(self)
            except Exception as exc:
                message = "Node {} failed to notify: {!r}"
                warnings.warn(message.format(self.name, exc))

    # Representation

    def __repr__(self):
        return "node <{}>".format(self.name)


# Restricted node

class RestrictedNode(Node):

    def set_result(self, result):
        if result is not None and not isinstance(result, triplet):
            raise TypeError("Not a triplet (or None)")
        return super(RestrictedNode, self).set_result(result)


# Graph object

class Graph(Mapping):

    def __init__(self):
        # Graph state
        self._nodes = {}
        self._rules = {}
        # Computed state
        self._updates = {}
        self._dependencies = defaultdict(set)
        self._subscriptions = defaultdict(set)
        # Propagation state
        self._pending = set()
        self._propagating = False

    # Accessors

    def subnodes(self, name):
        node = self._nodes[name]
        if node not in self._rules:
            return []
        _, bind = self._rules[node]
        return [self._nodes[subname] for subname in bind]

    # Create graph

    def add_node(self, node):
        if node.name in self._nodes:
            message = "A node called {} already exists"
            raise ValueError(message.format(node.name))
        self._nodes[node.name] = node

    def add_rule(self, node, func, bind):
        if node not in self._nodes.values():
            message = "The node {!r} is not in the graph"
            raise ValueError(message.format(node))
        if node in self._rules:
            message = "A rule for {} already exists"
            raise ValueError(message.format(node.name))
        self._rules[node] = func, bind

    # Build dependencies

    def build(self):
        # Loop over rules
        for node, (func, bind) in self._rules.items():
            # Set update callbacks
            publishers = [self._nodes[subname] for subname in bind]
            self._updates[node] = partial(func, *publishers)
            # Set subscriptions
            for publisher in publishers:
                self._subscriptions[publisher].add(node)
            # Compute dependencies
            seen = set()
            names = set(bind)
            while names:
                current_name = names.pop()
                seen.add(current_name)
                current_node = self._nodes[current_name]
                if current_node not in self._rules:
                    continue
                current_rule = self._rules[current_node]
                names |= set(current_rule[1]) - seen
            # Check cyclic dependencies
            if node.name in seen:
                msg = '{} is involved in a cyclic dependency'
                raise ValueError(msg.format(node))
            # Set dependencies
            self._dependencies[node] = {self._nodes[name] for name in seen}
        # Set callbacks (after the graph is proven to be valid)
        for publisher in self._subscriptions.keys():
            if self.callback not in publisher.callbacks:
                publisher.callbacks.append(self.callback)

    # Reset

    def reset(self):
        # Remove callbacks
        for publisher in self._subscriptions.keys():
            if self.callback in publisher.callbacks:
                publisher.callbacks.remove(self.callback)
        # Reset computed state
        self._updates = {}
        self._dependencies = defaultdict(set)
        self._subscriptions = defaultdict(set)
        # Reset propagation state
        self._pending = set()
        self._propagating = False

    # Propagation

    def callback(self, node):
        self._pending |= self._subscriptions[node]
        if not self._propagating:
            self.propagate()

    def propagate(self):
        # Set propagation flag
        try:
            self._propagating = True
            # Loop over pending updates
            while self._pending:
                # Find next item
                for node in self._pending:
                    dependencies = self._dependencies[node]
                    if self._pending.isdisjoint(dependencies):
                        self._pending.remove(node)
                        break
                # Deadlock
                else:
                    warnings.warn('Propagation deadlocked')
                    node = self._pending.pop()
                # Update and notify
                self.update(node)
        # Reset propagation flag
        finally:
            self._propagating = False

    def update(self, node):
        callback = self._updates[node]
        try:
            node.set_result(callback())
        except Exception as exc:
            node.set_exception(exc)

    # Dict interface

    def __getitem__(self, key):
        return self._nodes[key]

    def __iter__(self):
        return iter(self._nodes)

    def __len__(self):
        return len(self._nodes)
