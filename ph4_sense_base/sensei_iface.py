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
