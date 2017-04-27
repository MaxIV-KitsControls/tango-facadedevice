from tango import DevState
from tango.server import command
from facadedevice import Facade, local_attribute, state_attribute


class Counter3(Facade):

    @local_attribute(
        dtype=int)
    def count(self):
        return 0

    @command
    def increment(self):
        node = self.graph['count']
        value, stamp, quality = node.result()
        new_result = (value+1,)
        node.set_result(new_result)

    @state_attribute(
        bind=['count'])
    def state_and_status(self, count):
        if count == 0:
            return DevState.OFF, 'The count is 0'
        return DevState.ON, 'The count is {}'.format(count)

if __name__ == '__main__':
    Counter3.run_server()
