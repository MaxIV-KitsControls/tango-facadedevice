"""Contain the tests for proxy device server."""

# Imports
from mock import Mock
from PyTango.server import command
from devicetest import DeviceTestCase
from PyTango import DevState, DevFailed, AttrQuality, AttrWriteType

# Proxy imports
from facadedevice import Facade, FacadeMeta
from facadedevice import device as proxy_module
from facadedevice import proxy_command, proxy_attribute
from facadedevice import proxy, logical_attribute


# Example
class CameraScreen(Facade):
    __metaclass__ = FacadeMeta

    # Proxy
    PLCDevice = proxy("PLCDevice")

    # Proxy attributes
    StatusIn = proxy_attribute(
        device="OPCDevice",
        prop="InStatusTag",
        dtype=bool)

    StatusOut = proxy_attribute(
        device="OPCDevice",
        prop="OutStatusTag",
        dtype=bool)

    # Logical attributes
    @logical_attribute(dtype=bool)
    def Error(self, data):
        return data["StatusIn"] == data["StatusOut"]

    # Proxy commands
    MoveIn = proxy_command(
        device="OPCDevice",
        prop="InCmdTag",
        attr=True,
        value=1)

    MoveOut = proxy_command(
        device="OPCDevice",
        prop="OutCmdTag",
        attr=True,
        value=1)

    # State
    def state_from_data(self, data):
        if data['Error']:
            return DevState.FAULT
        return DevState.INSERT if data['StatusIn'] else DevState.EXTRACT

    # Status
    def status_from_data(self, data):
        if data['Error']:
            return "Conflict between IN and OUT informations"
        return "IN" if data['StatusIn'] else "OUT"

    Reset = proxy_command(
        device="PLCDevice",
        cmd="Reset")


# Device test case
class ProxyTestCase(DeviceTestCase):
    """Test case for packet generation."""

    device = CameraScreen
    properties = {"PushEvents":   "False",
                  "InCmdTag":     "tag1",
                  "OutCmdTag":    "tag2",
                  "InStatusTag":  "tag3",
                  "OutStatusTag": "tag4",
                  "OPCDevice":    "a/b/c",
                  "PLCDevice":    "c/d/e"}

    @classmethod
    def mocking(cls):
        # Mock DeviceProxy
        cls.attrx, cls.attry = Mock(), Mock()
        cls.attrx.value, cls.attry.value = 0, 0
        cls.attrx.time.totime.return_value = 0
        cls.attry.time.totime.return_value = 0
        cls.attrx.quality, cls.attry.quality = (AttrQuality.ATTR_VALID,) * 2
        proxy_module.create_device_proxy = Mock(name="DeviceProxy")
        cls.DeviceProxy = proxy_module.create_device_proxy
        cls.proxy = cls.DeviceProxy.return_value
        cls.proxy.dev_name.return_value = "some/device/name"
        cls.proxy.read_attributes.return_value = [cls.attry, cls.attrx]
        cls.proxy.subscribe_event.side_effect = DevFailed

    def test_attributes(self):
        # Expected values
        tags = ['tag4', 'tag3']
        states = [[DevState.FAULT, DevState.EXTRACT],
                  [DevState.INSERT, DevState.FAULT]]
        status = [["Conflict", "OUT"], ["IN", "Conflict"]]
        # InStatus in [False, True]
        for x in range(2):
            # OutStatus in [False, True]
            for y in range(2):
                # Perform tests
                self.attrx.value, self.attry.value = x, y
                self.assertEqual(self.device.StatusIn, x)
                self.assertEqual(self.device.StatusOut, y)
                self.assertEqual(self.device.Error, x == y)
                self.assertEqual(self.device.state(), states[x][y])
                self.assertIn(status[x][y], self.device.status())
                self.proxy.read_attributes.assert_called_with(tags)
        # Proxy
        args_list = [x.args for x in self.DeviceProxy.call_args_list]
        self.assertEqual(len(args_list), 2)
        self.assertIn(("a/b/c",), args_list)
        self.assertIn(("c/d/e",), args_list)

    def test_commands(self):
        # MoveIn command
        self.device.MoveIn()
        self.proxy.write_attribute.assert_called_with("tag1", 1)
        # MoveOut command
        self.device.MoveOut()
        self.proxy.write_attribute.assert_called_with("tag2", 1)
        # Rest command
        self.device.Reset()
        self.proxy.command_inout.assert_called_once_with("Reset", None)
        # Info command
        expected = """\
The device is currently connected.
It does not push change events.
It didn't subscribe to any event.
It is polling the following attribute(s):
- StatusOut: some/device/name/tag4
- StatusIn: some/device/name/tag3
It doesn't use any caching to limit the calls the other devices.
-----
No errors in history since
"""
        self.assertIn(expected.strip(), self.device.GetInfo())

    def test_exception(self):
        self.proxy.read_attributes.side_effect = DevFailed("Fail!")
        self.assertEqual(self.device.StatusIn, None)
        self.assertEqual(self.device.State(), DevState.FAULT)
        self.assertIn("Cannot read from proxy", self.device.Status())
        self.assertIn("Fail!", self.device.Status())

    def test_broken(self):
        self.assertEqual(True, True, 'Oops, I broke the tests')

    def test_writable_attributes(self):
        self.proxy.get_attribute_config().writable = AttrWriteType.READ
        self.device.init()
        status = self.device.status()
        self.assertIn("command 'moveout' failure: attribute",status)
        self.assertIn("command 'movein' failure: attribute", status)
        self.assertIn("not writable", status)
        self.assertEqual(self.device.state(), DevState.FAULT)

    def test_tangocmd_exist(self):
        self.proxy.command_query.side_effect = DevFailed
        self.device.init()
        self.assertEqual(self.device.state(), DevState.FAULT)
        status =  self.device.status()
        self.assertIn("command 'reset' failure: command", status)
        self.assertIn("doesn't exist", status)
