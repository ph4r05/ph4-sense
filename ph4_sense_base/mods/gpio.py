from ph4_sense_base.mods import BaseMod


class GpioMod(BaseMod):
    def __init__(self, *args, **kwargs):
        super().__init__()

    def set_val(self, pin, val):
        pass

    def get_val(self, pin):
        pass
