class MpLogger:
    """
    Levels:

    CRITICAL = 50
    FATAL = CRITICAL
    ERROR = 40
    WARNING = 30
    WARN = WARNING
    INFO = 20
    DEBUG = 10
    NOTSET = 0
    """

    def __init__(self, log_fnc):
        self.log_fnc = log_fnc

    def critical(self, msg, *args, **kwargs):
        self.log_fnc(50, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.log_fnc(40, msg, *args, **kwargs)

    def exception(self, msg, *args, exc_info=True, **kwargs):
        self.log_fnc(40, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.log_fnc(30, msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        self.log_fnc(30, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.log_fnc(20, msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self.log_fnc(10, msg, *args, **kwargs)
