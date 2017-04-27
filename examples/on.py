from tango import DevState
from facadedevice import Facade


class On(Facade):

    def safe_init_device(self):
        super(Facade, self).safe_init_device()
        self.set_state(DevState.ON)

if __name__ == '__main__':
    On.run_server()
