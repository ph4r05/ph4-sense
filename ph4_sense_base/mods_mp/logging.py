def log_fnc(self, level, msg, *args, **kwargs):
    if level < 20:  # do not log debug events
        return

    msg_use = msg if not args else msg % args
    self.print("log[{}]: {}".format(level, msg_use))
