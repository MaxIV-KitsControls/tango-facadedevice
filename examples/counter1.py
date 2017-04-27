from tango import AttrWriteType
from facadedevice import Facade, local_attribute


class Counter1(Facade):

    @local_attribute(
        dtype=int,
        access=AttrWriteType.READ_WRITE,)
    def count(self):
        return 0

if __name__ == '__main__':
    Counter1.run_server()
