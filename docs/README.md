## Licences and comments

Some licence comments and other comment blocks were moved here from the source files to minimize file transfer to ESP32 as there are memory allocation issues.

[sps30_mp.py](..%2Fph4_sense%2Fsensors%2Fsps30_mp.py):

```
# SPDX-FileCopyrightText: 2021 Kevin J. Walters
#
# SPDX-License-Identifier: MIT
"""
`adafruit_sps30.i2c`
================================================================================

Helper library for the Sensirion SPS30 particulate matter sensor using i2c interface.


* Author(s): Kevin J. Walters

Implementation Notes
--------------------

**Hardware:**

* `Sensirion SPS30
   <https://www.sensirion.com/en/environmental-sensors/particulate-matter-sensors-pm25/>`_

**Software and Dependencies:**

* Adafruit CircuitPython firmware for the supported boards:
  https://github.com/adafruit/circuitpython/releases


 * Adafruit's Bus Device library: https://github.com/adafruit/Adafruit_CircuitPython_BusDevice
 * Adafruit's Register library: https://github.com/adafruit/Adafruit_CircuitPython_Register
"""
```

Class:
```python
"""
CircuitPython helper class for using the Sensirion SPS30 particulate matter sensor
over the i2c interface.

:param i2c: The I2C bus the SPS30 is connected to.
:param int address: The I2C device address for the sensor. Default is :const:`0x69`

**Quickstart: Importing and using the SPS30**

    Here is an example of using the i2c sub-class of the :class:`SPS30` class.
    First you will need to import the libraries to use the sensor

    .. code-block:: python

        import board
        from adafruit_sps30.i2c import SPS30_I2C

    Once this is done you can define your `board.I2C` object and define your sensor object
    using the i2c bus.
    The SPS30 i2c mode is selected by grounding its interface select pin.

    .. code-block:: python

        i2c = board.I2C()   # uses board.SCL and board.SDA
        sps = SPS30_I2C(i2c)

    Now you have access to the air quality data using the class function
    `adafruit_sps30.SPS30.read`

    .. code-block:: python

        aqdata = sps.read()

"""
```
