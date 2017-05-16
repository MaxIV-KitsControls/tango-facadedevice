"""Provide helpers for tango."""

# Imports
import time
import fnmatch
import itertools
import functools
import collections

# Conditional imports
try:
    from threading import get_ident
except ImportError:  # pragma: no cover
    from threading import _get_ident as get_ident

# Exception imports
from facadedevice.exception import traceback_string, exception_string

# Tango imports
from tango.server import Device, command
from tango import AutoTangoMonitor, Database, DeviceProxy
from tango import AttrQuality, AttrWriteType, DevState, DispLevel
from tango import AttrDataFormat, CmdArgType


# Constants

ATTR_NOT_ALLOWED = "API_AttrNotAllowed"


# Default attribute value

def get_default_attribute_value(dformat, dtype):
    if dformat == AttrDataFormat.IMAGE:
        return ((),)
    if dformat == AttrDataFormat.SPECTRUM:
        return ()
    if dtype == CmdArgType.DevString:
        return ""
    # Zero should work for everything else
    return 0


# Aggregate qualities

def aggregate_qualities(qualities):
    length = len(AttrQuality.values)
    sortable = map(lambda x: (x-1) % length, qualities)
    result = (min(sortable) + 1) % length
    return AttrQuality.values[result]


# Patched device proxy

def create_device_proxy(*args, **kwargs):
    proxy = DeviceProxy(*args, **kwargs)
    proxy._get_info_()
    return proxy


# Split attribute name

def split_tango_name(name):
    lst = name.split('/')
    return '/'.join(lst[:-1]), lst[-1]


# Attribute check

def check_attribute(name, writable=False):
    device, attr = split_tango_name(name)
    proxy = create_device_proxy(device)
    cfg = proxy.get_attribute_config(attr)
    if writable and cfg.writable is AttrWriteType.READ:
        raise ValueError("The attribute {} is not writable".format(name))
    return cfg


# Attribute from wildcard

def attributes_from_wildcard(wildcard):
    db = Database()
    wdev, wattr = split_tango_name(wildcard)
    for device in db.get_device_exported(wdev):
        proxy = create_device_proxy(device)
        infos = proxy.attribute_list_query()
        attrs = sorted(info.name.lower() for info in infos)
        for attr in fnmatch.filter(attrs, wattr):
            yield '{}/{}'.format(device.lower(), attr)


# Tango command check

def check_command(name):
    device, cmd = split_tango_name(name)
    proxy = create_device_proxy(device)
    return proxy.command_query(cmd)


# Make subcommand

def make_subcommand(name, attr=False):
    # Check value
    if attr:
        check_attribute(name)
    else:
        check_command(name)
    # Create proxy
    device, obj = split_tango_name(name)
    proxy = create_device_proxy(device)
    # Make subcommand
    method = proxy.write_attribute if attr else proxy.command_inout
    return functools.partial(method, obj)


# Device class

class EnhancedDevice(Device):
    """Enhanced version of server.Device"""

    # Property

    @property
    def connected(self):
        return self._connected

    # Exception helpers

    def register_exception(self, exc, msg=None, ignore=False):
        # Stream traceback
        self.debug_stream(traceback_string(exc).replace('%', '%%'))
        # Exception as a string
        status = exception_string(exc, wrap=msg)
        # Stream error
        self.error_stream(status)
        # Save in history
        self._exception_history[status] += 1
        # Set state and status
        if not ignore:
            self.set_status(status)
            self.set_state(DevState.FAULT)
        # Return exception status
        return status

    def ignore_exception(self, exc, msg=None):
        return self.register_exception(exc, msg=msg, ignore=True)

    def debug_exception(self, exc, msg=None):
        string = exception_string(exc, wrap=msg)
        self.debug_stream(string.replace('%', '%%'))

    # Initialization and cleanup

    def get_device_properties(self, cls=None):
        """Raise a ValueError if a property is missing."""
        Device.get_device_properties(self, cls)
        for key, value in self.device_property_list.items():
            if value[2] is None:
                raise ValueError('Missing property: ' + key)

    def init_device(self):
        # Init attributes
        self._event_dict = {}
        self._connected = False
        self._tango_properties = {}
        self._init_stamp = time.time()
        self._eid_counter = itertools.count(1)
        self._exception_history = collections.defaultdict(int)
        # Init state and status events
        self.set_change_event('State', True, False)
        self.set_archive_event('State', True, True)
        self.set_change_event('Status', True, False)
        self.set_archive_event('Status', True, True)
        # Set INIT state
        self.set_state(DevState.INIT)
        # Initialize the device
        try:
            self._init_ident = get_ident()
            self.safe_init_device()
        # Register exception
        except Exception as exc:
            msg = "Exception while initializing the device"
            self.register_exception(exc, msg)
            self.delete_device()
            return
        # Connection successful
        else:
            self._connected = True
            self._init_ident = None
        # Set default state
        if self.get_state() == DevState.INIT:
            self.set_state(DevState.UNKNOWN)

    def safe_init_device(self):
        self.get_device_properties()

    def delete_device(self):
        # Unsubscribe all
        try:
            self.unsubscribe_all()
        except Exception as exc:
            msg = "Exception while unsubscribing"
            return self.ignore_exception(exc, msg)
        # Parent call
        super(Device, self).delete_device()

    # Event subscribtion

    def _wrap_callback(self, callback, eid):
        def wrapped(event):
            # Fix libtango bug #316
            if self._init_ident is not None and \
               self._init_ident != get_ident():
                return  # pragma: no cover
            # Acquire monitor lock
            try:
                with AutoTangoMonitor(self):
                    if eid in self._event_dict:
                        callback(event)
            # Register exception
            except Exception as exc:
                message = "Exception while running event callback {}"
                self.ignore_exception(exc, message.format(eid))
        return wrapped

    def subscribe_event(self, attr_name, event_type, callback,
                        filters=[], stateless=False, proxy=None):
        # Get proxy
        if proxy is None:
            device_name, attr_name = split_tango_name(attr_name)
            proxy = create_device_proxy(device_name)
        # Create callback
        eid = next(self._eid_counter)
        self._event_dict[eid] = proxy, attr_name, None
        wrapped = self._wrap_callback(callback, eid)
        # Subscribe
        try:
            proxy_eid = proxy.subscribe_event(
                attr_name, event_type, wrapped, filters, stateless)
        # Error
        except Exception:
            del self._event_dict[eid]
            raise
        # Success
        self._event_dict[eid] = proxy, attr_name, proxy_eid, event_type
        return eid

    def unsubscribe_event(self, eid):
        proxy, _, proxy_eid, _ = self._event_dict.pop(eid)
        proxy.unsubscribe_event(proxy_eid)

    def unsubscribe_all(self):
        for eid in list(self._event_dict):
            proxy, attr_name, _, _ = self._event_dict[eid]
            attr_name = '/'.join((proxy.dev_name(), attr_name))
            try:
                self.unsubscribe_event(eid)
            except Exception as exc:
                msg = "Exception while unsubscribing from attribute {}"
                msg = msg.format(attr_name)
                self.ignore_exception(exc, msg)
            else:
                msg = "Successfully unsubscribed from attribute {}"
                msg = msg.format(attr_name)
                self.info_stream(msg)

    # State, status

    def set_state(self, state, stamp=None, quality=AttrQuality.ATTR_VALID):
        super(Device, self).set_state(state)
        if stamp is None:
            stamp = time.time()
        # Pushing specific values for events on state attribute doesn't work
        self.push_change_event('State')  # ... state, stamp, quality)
        self.push_archive_event('State')  # ... state, stamp, quality)

    def set_status(self, status, stamp=None, quality=AttrQuality.ATTR_VALID):
        super(Device, self).set_status(status)
        if stamp is None:
            stamp = time.time()
        # Pushing specific values for events on status attribute doesn't work
        self.push_change_event('Status')  # ... state, stamp, quality)
        self.push_archive_event('Status')  # ... state, stamp, quality)

    # Commands

    @command(
        dtype_out=str,
        doc_out="Information about events and exceptions.",
        display_level=DispLevel.EXPERT)
    def GetInfo(self):
        lines = []
        # Connection
        if self._connected:
            lines.append("The device is currently connected.")
        else:
            lines.append("The device is currently stopped because of:")
            lines.append(self.get_status())
        # Event subscription
        if self._event_dict:
            lines.append("It subscribed to event channel "
                         "of the following attribute(s):")
            for proxy, attr_name, _, event_type in self._event_dict.values():
                attr_name = '/'.join((proxy.dev_name(), attr_name))
                lines.append("- {} ({})".format(attr_name, event_type))
        else:
            lines.append("It doesn't hold a subsription to any event channel.")
        # Exception history
        lines.append("-" * 5)
        strtime = time.ctime(self._init_stamp)
        if self._exception_history:
            msg = "Error history since {} (last initialization):"
            lines.append(msg.format(strtime))
            for key, value in self._exception_history.items():
                string = 'once' if value == 1 else '{} times'.format(value)
                lines.append(' - Raised {}:'.format(string))
                lines.extend(' ' * 4 + line for line in key.split('\n'))
        else:
            msg = "No errors in history since {} (last initialization)."
            lines.append(msg.format(strtime))
        # Return result
        return '\n'.join(lines)
