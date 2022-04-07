"""Contain the tests for proxy device server."""

# Imports
import pytest

from unittest.mock import Mock, patch

# Tango imports
from tango import DevState, DevFailed
from tango.test_context import DeviceTestContext

# Facade imports
from facadedevice import Facade, proxy_command, utils


def test_simple_proxy_command():
    class Test(Facade):

        double = proxy_command(
            property_name="prop", dtype_in=int, dtype_out=int
        )

    with patch("facadedevice.utils.DeviceProxy") as inner_proxy:
        inner_proxy = utils.DeviceProxy.return_value
        inner_proxy.dev_name.return_value = "a/b/c"
        inner_proxy.command_inout.side_effect = lambda attr, x: x * 2

        with DeviceTestContext(Test, properties={"prop": "a/b/c/d"}) as proxy:
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check mocks
            utils.DeviceProxy.assert_any_call("a/b/c")
            # Run command
            assert proxy.double(3) == 6
            # Check
            inner_proxy.command_inout.assert_called_once_with("d", 3)


def test_complex_proxy_command():
    class Test(Facade):
        @proxy_command(property_name="prop", dtype_in=int)
        def cmd(self, subcommand, n):
            for _ in range(n):
                subcommand()

    with patch("facadedevice.utils.DeviceProxy") as inner_proxy:
        inner_proxy = utils.DeviceProxy.return_value
        inner_proxy.dev_name.return_value = "a/b/c"

        with DeviceTestContext(Test, properties={"prop": "a/b/c/d"}) as proxy:
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check mocks
            utils.DeviceProxy.assert_any_call("a/b/c")
            # Run command
            proxy.cmd(3)
            # Check
            mock = Mock(return_value=None)
            for i in range(3):
                mock("d")
            assert (
                inner_proxy.command_inout.call_args_list == mock.call_args_list
            )


def test_disabled_proxy_command():
    class Test(Facade):

        double = proxy_command(
            property_name="prop", dtype_in=int, dtype_out=int
        )

    with patch("facadedevice.utils.DeviceProxy") as inner_proxy:

        with DeviceTestContext(Test, properties={"prop": "None"}) as proxy:
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check mocks
            inner_proxy.assert_not_called()
            # Run command
            with pytest.raises(DevFailed) as ctx:
                proxy.double(3)
            # Check
            assert "This proxy command is disabled" in str(ctx.value)


def test_emulated_proxy_command():
    class Test(Facade):

        get_pi = proxy_command(property_name="prop", dtype_out=float)

    with patch("facadedevice.utils.DeviceProxy") as inner_proxy:

        with DeviceTestContext(Test, properties={"prop": "3.14"}) as proxy:
            # Device not in fault
            assert proxy.state() == DevState.UNKNOWN
            # Check mocks
            inner_proxy.assert_not_called()
            # Run command
            assert proxy.get_pi() == 3.14
