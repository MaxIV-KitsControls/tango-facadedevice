from facadedevice import Facade, proxy_command


class Commands(Facade):

    reset = proxy_command(
        property_name="ResetCommand")

    echo = proxy_command(
        dtype_in=str,
        dtype_out=str,
        property_name="EchoCommand")

    set_level = proxy_command(
        dtype_in=float,
        property_name="LevelAttribute",
        write_attribute=True)

    @proxy_command(
        dtype_in=int,
        dtype_out=int,
        property_name="EchoCommand")
    def identity(self, subcommand, arg):
        return int(subcommand(str(arg)))


if __name__ == '__main__':
    Commands.run_server()
