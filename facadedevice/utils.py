"""Provide helpers for tango."""

# Imports
import time
import ctypes
import threading
import functools
import itertools
import traceback
import collections

# Tango imports
from tango.server import Device, command
from tango import AutoTangoMonitor, DeviceProxy, LatestDeviceImpl
from tango import AttrQuality, AttrWriteType, DevFailed, DevState, DispLevel


# Numpy print options

try:
    import numpy
    numpy.set_printoptions(precision=5, threshold=6)
except Exception:
    print("Couldn't customize numpy print options")


# Constants

ATTR_NOT_ALLOWED = "API_AttrNotAllowed"


# TID helper

def gettid():
    libc = 'libc.so.6'
    for cmd in (186, 224, 178):
        try:
            tid = ctypes.CDLL(libc).syscall(cmd)
        except OSError:
            return threading.current_thread().ident
        if tid != -1:
            return tid


# Safer traceback

def safe_traceback(limit=None):
    return traceback.format_exc(limit=limit).replace("%", "%%")


# Aggregate qualities

def aggregate_qualities(qualities):
    length = len(AttrQuality.values)
    t1 = lambda x: (int(x) - 1) % length
    t2 = lambda x: (int(x) + 1) % length
    result = t2(min(map(t1, qualities)))
    return AttrQuality.values[result]


# Debug it decorator

def debug_it(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Enter method
        tid = gettid()
        method = func.__name__
        msg = "Entering method {0} (tid={1})"
        self.debug_stream(msg.format(method, tid))
        # Run method
        try:
            result = func(self, *args, **kwargs)
        # Exit method with exception
        except Exception as exception:
            msg = "Method {0} failed (exception={1!r}, tid={2})"
            self.debug_stream(msg.format(method, exception, tid))
            raise
        # Exit method with result
        else:
            msg = "Method {0} returned (result={1!r}, tid={2})"
            self.debug_stream(msg.format(method, result, tid))
            return result
    return wrapper


# Patched device proxy

def create_device_proxy(*args, **kwargs):
    proxy = DeviceProxy(*args, **kwargs)
    proxy._get_info_()
    return proxy


# Writable attribute check

def is_writable_attribute(attr_name, device_proxy):
    """ Return if tango attribute exists and is writable, and also return
     string description """
    desc = "Attribute {0}/{1} is writable"
    writable = True
    try:
        # get attribute configuration
        cfg = device_proxy.get_attribute_config(attr_name)
        if cfg.writable is AttrWriteType.READ:
            # attribute exists but it is not writable
            desc = "Attribute {0}/{1} is not writable"
            writable = False
    except DevFailed:
        # attribute doesn't exist
        desc = "Can't find attribute {0}/{1} "
        writable = False
    desc = desc.format(device_proxy.name(), attr_name)
    return writable, desc


# Tango command check

def tango_command_exist(cmd_name, device_proxy):
    """ Return if tango command exist and return string description."""
    desc = "Command {0}/{1} exists"
    cmd_exists = True
    try:
        # check command description
        device_proxy.command_query(cmd_name)
    except DevFailed:
        # command_query failed, command doesn't exist
        desc += "-Command {0}/{1} doesn't exist'\n"
        cmd_exists = False
    desc = desc.format(device_proxy.name(), cmd_name)
    return cmd_exists, desc


# Device class

class EnhancedDevice(Device):
    """Enhanced version of server.Device"""

    # Property

    @property
    def connected(self):
        return self._connected

    # Exception helpers

    def register_exception(self, exc, msg="", ignore=False):
        # Stream traceback
        self.debug_stream(safe_traceback())
        # Convert DevFailed
        if isinstance(exc, DevFailed) and exc.args:
            exc = exc.args[0]
        # Exception as a string
        try:
            exc = exc.desc
        except AttributeError:
            exc = str(exc) if str(exc) else repr(exc)
        # Format status
        status = '\n'.join(filter(None, [msg, exc]))
        # Stream error
        self.error_stream(status)
        # Save in history
        self._exception_history[status] += 1
        # Ignore exception
        if ignore:
            return status
        # Set state and status
        self.set_status(status)
        self.set_state(DevState.FAULT)
        # Return exception status
        return status

    def ignore_exception(self, exc, msg=''):
        return self.register_exception(exc, msg=msg, ignore=True)

    # Initialization and cleanup

    def get_device_properties(self, cls=None):
        """Raise a ValueError if a property is missing."""
        Device.get_device_properties(self, cls)
        for key, value in self.device_property_list.items():
            if value[2] is None:
                raise ValueError('Missing property: ' + key)

    def __init__(self, cl, name):
        # Init attributes
        self._event_dict = {}
        self._connected = False
        self._tango_properties = {}
        self._init_stamp = time.time()
        self._eid_counter = itertools.count(1)
        self._exception_history = collections.defaultdict(int)
        # Skip Device.__init__ parent call
        LatestDeviceImpl.__init__(self, cl, name)
        # Init state and status events
        self.set_change_event('State', True, False)
        self.set_archive_event('State', True, True)
        self.set_change_event('Status', True, False)
        self.set_archive_event('Status', True, True)
        # Set INIT state
        self.set_state(DevState.INIT)
        # Get device properties
        try:
            self.get_device_properties()
        except Exception as exc:
            msg = "Error while getting device properties"
            self.register_exception(exc, msg)
            return
        # Initialize the device
        try:
            self.init_device()
        except Exception as exc:
            msg = "Exception while initializing the device"
            self.register_exception(exc, msg)
            return
        else:
            self._connected = True
        # Set default state
        if self.get_state() == DevState.INIT:
            self.set_state(DevState.UNKNOWN)

    def init_device(self):
        pass

    def delete_device(self):
        # Unsubscribe all
        try:
            self.unsubscribe_all()
        except Exception as exc:
            msg = "Error while unsubscribing"
            return self.ignore_exception(exc, msg)
        # Parent call
        super(Device, self).delete_device()

    # Event subscribtion

    def _wrap_callback(self, callback, eid):
        def wrapped(event):
            with AutoTangoMonitor(self):
                if eid in self._event_dict:
                    callback(event)
        return wrapped

    def subscribe_event(self, attr_name, event_type, callback,
                        filters=[], stateless=False, proxy=None):
        # Get proxy
        if proxy is None:
            device_name = '/'.join(attr_name.split('/')[:-1])
            attr_name = attr_name.split('/')[-1]
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
                msg = "Cannot unsubscribe from attribute {0}"
                msg = msg.format(attr_name)
                self.ignore_exception(exc, msg)
            else:
                msg = "Successfully Unsubscribed from attribute {0}"
                msg = msg.format(attr_name)
                self.info_stream(msg)

    # State, status

    def set_state(self, state, stamp=None, quality=AttrQuality.ATTR_VALID):
        super(Device, self).set_state(state)
        if stamp is None:
            stamp = time.time()
        self.push_change_event('State', state, stamp, quality)
        self.push_archive_event('State', state, stamp, quality)

    def set_status(self, status, stamp=None, quality=AttrQuality.ATTR_VALID):
        super(Device, self).set_status(status)
        if stamp is None:
            stamp = time.time()
        self.push_change_event('Status', status, stamp, quality)
        self.push_archive_event('Status', status, stamp, quality)

    # Commands

    @command(
        dtype_out=str,
        doc_out="Information about polling and events.",
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
            lines.append("It didn't subscribe to any event.")
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
