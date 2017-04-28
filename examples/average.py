from facadedevice import Facade, combined_attribute


class Average(Facade):

    @combined_attribute(
        dtype=float,
        property_name='AttributesToAverage')
    def average(self, *args):
        return sum(args) / len(args)

if __name__ == '__main__':
    Average.run_server()
