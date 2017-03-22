"""Contain the tests for proxy device server."""

# Imports
import pytest

# Tango imports
from tango import DevState, DevFailed
from tango.test_context import DeviceTestContext

# Facade imports
from facadedevice import Facade, proxy_command, utils


def test_simple_proxy_command(mocker):

    class Test(Facade):

        double = proxy_command(
            property_name='prop',
            dtype_in=int,
            dtype_out=int)

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'
    inner_proxy.command_inout.side_effect = lambda attr, x: x*2

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.DeviceProxy.assert_any_call('a/b/c')
        # Run command
        assert proxy.double(3) == 6
        # Check
        inner_proxy.command_inout.assert_called_once_with('d', 3)


def test_complex_proxy_command(mocker):

    class Test(Facade):

        @proxy_command(
            property_name='prop',
            dtype_in=int)
        def cmd(self, subcommand, n):
            for _ in range(n):
                subcommand()

    mocker.patch('facadedevice.utils.DeviceProxy')
    inner_proxy = utils.DeviceProxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.DeviceProxy.assert_any_call('a/b/c')
        # Run command
        proxy.cmd(3)
        # Check
        expected = [mocker.call('d')] * 3
        assert inner_proxy.command_inout.call_args_list == expected


def test_no_proxy_command(mocker):

    class Test(Facade):

        double = proxy_command(
            property_name='prop',
            dtype_in=int,
            dtype_out=int)

    mocker.patch('facadedevice.utils.DeviceProxy')

    with DeviceTestContext(Test, properties={'prop': 'NONE'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        assert not utils.DeviceProxy.called
        # Run command
        with pytest.raises(DevFailed) as ctx:
            assert proxy.double(3)
        # Check
        assert "This proxy command is disabled" in str(ctx.value)
