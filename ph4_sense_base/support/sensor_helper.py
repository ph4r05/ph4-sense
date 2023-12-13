from ph4_sense_base.support.allocator import PreallocatedBuffer


class SensorHelper:
    """
    Generic sensor helper that enables sensor classes access high-level functions,
    such as logging, buffer allocation, etc.
    """

    def __init__(self, logger=None):
        self.logger = logger
        self.buffer = PreallocatedBuffer(max_size=64)

    def log(self, msg, *args):
        if self.logger:
            self.logger.info(msg, *args)
        else:
            print(msg, *args)

    def log_info(self, msg, *args):
        if self.logger:
            self.logger.info(msg, *args)
        else:
            print("Info:", msg, *args)

    def log_error(self, msg, *args, exc_info=None):
        if self.logger:
            self.logger.error(msg, *args, exc_info=exc_info)
        else:
            print("Error:", msg, *args, exc_info)

    def get_buffer(self, size, idx=0):
        if idx > 0:
            return bytearray(size)
        return self.buffer.get(size)
