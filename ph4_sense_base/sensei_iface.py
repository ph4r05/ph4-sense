class SenseiIface:
    def __init__(
        self,
    ):
        pass

    def log_fnc(self, level, msg, *args, **kwargs):
        pass

    def print(self, msg, *args):
        pass

    def print_cli(self, msg, *args):
        print(msg, *args)

    def try_measure(self, fnc):
        return fnc()

    def get_uart_builder(self, desc):
        raise NotImplementedError()

    def get_temp_humd(self):
        return 0, 0  # TODO: implement
