import socket


class UdpLogger:
    def __init__(self, host):
        self.host = "localhost", 9999
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.set_host(host)

    def set_host(self, host):
        parts = str(host).rsplit(":", 1)
        if len(parts) == 1:
            self.host = parts[0], 9999
        else:
            self.host = parts[0], int(parts[1])

    def log_msg(self, msg, *args):
        try:
            log_line = msg
            if args:
                log_line += " " + (" ".join(map(str, args)))
            log_line += "\n"

            self.socket.sendto(log_line, self.host)

        except Exception as e:
            print("Could not send", e)
