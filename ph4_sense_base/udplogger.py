import socket


class UdpLogger:
    def __init__(self, host, is_esp32=True):
        self.host = "localhost", 9999
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.set_host(host)
        self.is_esp32 = is_esp32

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

            if self.is_esp32:
                self.socket.sendto(log_line, self.host)
            else:
                self.socket.sendto(log_line.encode("utf8"), self.host)

        except Exception as e:
            print("Could not send", e)
