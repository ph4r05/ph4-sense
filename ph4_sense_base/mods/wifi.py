from ph4_sense_base.mods import BaseMod


class WifiMod(BaseMod):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def connect_wifi(self, force=False):
        pass

    def check_wifi_ok(self):
        pass
