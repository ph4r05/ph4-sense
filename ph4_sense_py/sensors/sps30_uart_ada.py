"""
Library to read data from Sensirion SPS30 particulate matter sensor

by
Szymon Jakubiak
Twitter: @SzymonJakubiak
LinkedIn: https://pl.linkedin.com/in/szymon-jakubiak

MIT License

Copyright (c) 2018 Szymon Jakubiak

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Units for measurements:
    PM1, PM2.5, PM4 and PM10 are in ug/m^3, number concentrations are in #/cm^3
"""

import struct
import time

import serial

from ph4_sense.sensors.sps30_base import SPS30


class SPS30AdaUart(SPS30):
    # TODO: unify interface with i2c
    def __init__(self, port, **kwargs):
        super().__init__()
        self.port = port
        self.ser = serial.Serial(self.port, baudrate=115200, stopbits=1, parity="N", timeout=2)

    def start(self):
        self.ser.write([0x7E, 0x00, 0x00, 0x02, 0x01, 0x03, 0xF9, 0x7E])

    def stop(self):
        self.ser.write([0x7E, 0x00, 0x01, 0x00, 0xFE, 0x7E])

    @property
    def data_available(self):
        return True

    @staticmethod
    def reverse_byte_stuffing(raw: bytes) -> bytes:
        if b"\x7d\x5e" in raw:
            raw = raw.replace(b"\x7d\x5e", b"\x7e")
        if b"\x7d\x5d" in raw:
            raw = raw.replace(b"\x7d\x5d", b"\x7d")
        if b"\x7d\x31" in raw:
            raw = raw.replace(b"\x7d\x31", b"\x11")
        if b"\x7d\x33" in raw:
            raw = raw.replace(b"\x7d\x33", b"\x13")
        return raw

    def read(self):
        vals = self.read_values()
        for key, val in zip(self.FIELD_NAMES, vals):
            self.aqi_reading[key] = val
        return self.aqi_reading

    def read_values(self):
        self.ser.flushInput()
        # Ask for data
        self.ser.write([0x7E, 0x00, 0x03, 0x00, 0xFC, 0x7E])
        toRead = self.ser.inWaiting()
        # Wait for full response
        # (may be changed for looking for the stop byte 0x7E)
        while toRead < 47:
            toRead = self.ser.inWaiting()
            time.sleep(0.1)
        raw = self.ser.read(toRead)

        # Reverse byte-stuffing
        raw = SPS30AdaUart.reverse_byte_stuffing(raw)

        # Discard header and tail
        rawData = raw[5:-2]

        try:
            data = struct.unpack(">ffffffffff", rawData)
        except struct.error:
            data = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        return data

    def read_serial_number(self):
        self.ser.flushInput()
        self.ser.write([0x7E, 0x00, 0xD0, 0x01, 0x03, 0x2B, 0x7E])
        toRead = self.ser.inWaiting()
        while toRead < 24:
            toRead = self.ser.inWaiting()
            time.sleep(0.1)
        raw = self.ser.read(toRead)

        # Reverse byte-stuffing
        raw = SPS30AdaUart.reverse_byte_stuffing(raw)

        # Discard header, tail and decode
        serial_number = raw[5:-3].decode("ascii")
        return serial_number

    def read_firmware_version(self):
        self.ser.flushInput()
        self.ser.write([0x7E, 0x00, 0xD1, 0x00, 0x2E, 0x7E])
        toRead = self.ser.inWaiting()
        while toRead < 7:
            toRead = self.ser.inWaiting()
            time.sleep(0.1)
        raw = self.ser.read(toRead)

        # Reverse byte-stuffing
        raw = SPS30AdaUart.reverse_byte_stuffing(raw)

        # Discard header and tail
        data = raw[5:-2]
        # Unpack data
        data = struct.unpack(">bbbbbbb", data)
        firmware_version = str(data[0]) + "." + str(data[1])
        return firmware_version

    def close_port(self):
        self.ser.close()
