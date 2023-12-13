import network

from ph4_sense_base.adapters import sleep_ms, time
from ph4_sense_base.mods.wifi import WifiMod
from ph4_sense_base.sensei_iface import SenseiIface
from ph4_sense_base.support.consts import Const
from ph4_sense_base.support.typing import Optional
from ph4_sense_base.utils import try_exec_method_cb, try_fnc


class WifiModMp(WifiMod):
    def __init__(
        self,
        base: Optional[SenseiIface] = None,
        has_wifi=True,
        wifi_ssid: Optional[str] = None,
        wifi_passphrase: Optional[str] = None,
        on_wifi_reconnect=None,
    ):
        WifiMod.__init__(
            self,
            base=base,
            has_wifi=has_wifi,
            wifi_ssid=wifi_ssid,
            wifi_passphrase=wifi_passphrase,
            on_wifi_reconnect=on_wifi_reconnect,
        )

        self.base = base
        self.has_wifi = has_wifi
        self.wifi_ssid = wifi_ssid
        self.wifi_passphrase = wifi_passphrase
        self.on_wifi_reconnect = on_wifi_reconnect

        self.sta_if = None
        self.on_wifi_reconnect = None
        self.wifi_reconnect_timeout = 60 * 3
        self.last_wifi_reconnect = 0

    def connect_wifi(self, force=False):
        if not self.has_wifi:
            return

        if force:
            self.sta_if = None

        if not self.sta_if:
            self.sta_if = network.WLAN(network.STA_IF)
            self.sta_if.active(True)

        if not self.wifi_ssid:
            raise ValueError("WiFi is not configured")

        if not self.sta_if.isconnected():
            try_exec_method_cb(self.base, Const.PRINT_CLI, "Not connected, scanning...")
            scan_res = self.sta_if.scan()
            if scan_res:
                for net in scan_res:
                    try_exec_method_cb(self.base, Const.PRINT_CLI, " - ", net)

            try_exec_method_cb(self.base, Const.PRINT_CLI, "Connecting to WiFi: " + self.wifi_ssid)
            self.sta_if.connect(self.wifi_ssid, self.wifi_passphrase)
            while not self.sta_if.isconnected():
                sleep_ms(500)

            try_exec_method_cb(self.base, Const.PRINT, "WiFi connected")

            # Set unlimited WiFi reconnect attempts
            self.sta_if.config(reconnects=-1)

        try_exec_method_cb(self.base, Const.PRINT, "WiFi status:", self.sta_if.status())
        try_exec_method_cb(self.base, Const.PRINT, "WiFi ifconfig:", self.sta_if.ifconfig())

    def check_wifi_ok(self):
        """
        Possible WiFi statuses:
            * ``STAT_IDLE`` -- no connection and no activity,
            * ``STAT_CONNECTING`` -- connecting in progress,
            * ``STAT_WRONG_PASSWORD`` -- failed due to incorrect password,
            * ``STAT_NO_AP_FOUND`` -- failed because no access point replied,
            * ``STAT_CONNECT_FAIL`` -- failed due to other problems,
            * ``STAT_GOT_IP`` -- connection successful.
        :return:
        """
        if not self.has_wifi:
            return

        try:
            if not self.sta_if.isconnected():
                raise ValueError("WiFi not connected")

            wifi_status = self.sta_if.status()
            is_connected = wifi_status == network.STAT_GOT_IP
            if is_connected:
                return

            t = time.time()
            is_connecting = wifi_status == network.STAT_CONNECTING
            if is_connecting and t - self.last_wifi_reconnect < self.wifi_reconnect_timeout:
                return

            try_fnc(lambda: self.sta_if.disconnect())

        except Exception as e:
            try_exec_method_cb(self.base, Const.PRINT, "Network exception: ", e)

        # When control flow gets here - reconnect
        if self.on_wifi_reconnect:
            self.on_wifi_reconnect()
