from tango.server import command
from facadedevice import Facade, local_attribute, triplet


class Counter2(Facade):

    @local_attribute(
        dtype=int)
    def count(self):
        return 0

    @command
    def increment(self):
        node = self.graph['count']
        value, stamp, quality = node.result()
        new_result = triplet(value+1)
        node.set_result(new_result)

if __name__ == '__main__':
    Counter2.run_server()
