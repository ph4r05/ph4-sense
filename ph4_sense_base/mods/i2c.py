from ph4_sense_base.mods import BaseMod


class I2CMod(BaseMod):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.i2c = None

    def start_bus(self):
        pass
