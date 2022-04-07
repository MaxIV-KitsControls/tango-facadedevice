from tango import DevState
from facadedevice import Facade, proxy_command
from facadedevice import proxy_attribute, logical_attribute, state_attribute


class CameraScreen(Facade):

    # Proxy attributes

    StatusIn = proxy_attribute(dtype=bool, property_name="StatusInAttribute")

    StatusOut = proxy_attribute(dtype=bool, property_name="StatusOutAttribute")

    # Logical attributes

    @logical_attribute(dtype=bool, bind=["StatusIn", "StatusOut"])
    def Error(self, status_in, status_out):
        return status_in and status_out

    @logical_attribute(dtype=bool, bind=["StatusIn", "StatusOut"])
    def Moving(self, status_in, status_out):
        return not status_in and not status_out

    # Proxy commands

    @proxy_command(property_name="MoveInAttribute", write_attribute=True)
    def MoveIn(self, subcommand):
        subcommand(1)

    @proxy_command(property_name="MoveOutAttribute", write_attribute=True)
    def MoveOut(self, subcommand):
        subcommand(1)

    # State and status

    @state_attribute(bind=["Error", "Moving", "StatusIn"])
    def state(self, error, moving, status_in):
        if error:
            return DevState.FAULT, "A conflict has been detected"
        elif moving:
            return DevState.MOVING, "The screen is moving"
        elif status_in:
            return DevState.INSERT, "The screen is inserted"
        else:
            return DevState.EXTRACT, "The screen is exctracted"


if __name__ == "__main__":
    CameraScreen.run_server()
