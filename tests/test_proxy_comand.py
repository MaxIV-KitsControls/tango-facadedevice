"""Contain the tests for proxy device server."""

# Imports
import time  # noqa
from collections import defaultdict

from tango import DevState
from tango.test_context import DeviceTestContext

# Proxy imports
from facadedevice.graph import VALID
from facadedevice import Facade, TimedFacade, proxy_command, utils


def test_proxy_command(mocker):

    class Test(Facade):

        @proxy_command(
            prop='prop',
            dtype_in=int)
        def cmd2(self, subcommand, n):
            for _ in range(n):
                subcommand()

    mocker.patch('facadedevice.utils.create_device_proxy')
    inner_proxy = utils.create_device_proxy.return_value
    inner_proxy.dev_name.return_value = 'a/b/c'

    with DeviceTestContext(Test, properties={'prop': 'a/b/c/d'}) as proxy:
        # Device not in fault
        assert proxy.state() == DevState.UNKNOWN
        # Check mocks
        utils.create_device_proxy.assert_any_call('a/b/c')
        # Run command
        proxy.cmd2(3)
        # Check
        expected = [mocker.call()] * 3
        assert inner_proxy.command_inout.call_args == expected
