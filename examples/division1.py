from tango import AttrWriteType
from facadedevice import Facade, local_attribute, logical_attribute


class Division1(Facade):

    A = local_attribute(dtype=float, access=AttrWriteType.READ_WRITE)

    B = local_attribute(dtype=float, access=AttrWriteType.READ_WRITE)

    @logical_attribute(dtype=float, bind=["A", "B"])
    def C(self, a, b):
        return a / b


if __name__ == "__main__":
    Division1.run_server()
