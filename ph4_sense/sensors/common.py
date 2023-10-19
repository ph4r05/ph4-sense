def ccs811_err_to_str(err: int) -> str:
    ret = ""
    err = err or 0
    if err & 0x1:
        ret += "Wi "  # WRITE_REG_INVALID
    if err & 0x2:
        ret += "Ri "  # READ_REG_INVALID
    if err & 0x4:
        ret += "Mi "  # MEASMODE_INVALID
    if err & 0x8:
        ret += "Mr "  # MAX_RESISTANCE
    if err & 0x10:
        ret += "Hf "  # HEATER_FAULT
    if err & 0x20:
        ret += "Hs "  # HEATER_SUPPLY
    return ret


def ccs811_status_to_str(status: int) -> str:
    ret = ""
    if status & 0x1:
        ret += "Er "  # Error
    if status & 0x8:
        ret += "Dr "  # Data ready
    if status & 0x10:
        ret += "F+ "  # Valid Fw loaded
    else:
        ret += "F- "  # Valid Fw loaded
    if status & 0x80:
        ret += "R+ "  # FW_MODE, 1 = ready to measure
    else:
        ret += "R- "  # FW_MODE, 1 = ready to measure
    return ret


def get_ordering(offset, length, msb_first=True):
    return range(offset, offset + length) if msb_first else range(offset + length - 1, offset - 1, -1)


def buf2int(buff, offset=0, length=None, msb_first=True):
    length = length if length is not None else len(buff) - offset
    reg = 0
    for i in get_ordering(offset, length, msb_first):
        reg = (reg << 8) | buff[i]
    return reg


def int2buf(value, buff, offset, length, msb_first=True):
    buff = buff if buff is not None else bytearray(offset + length)
    for i in reversed(get_ordering(offset, length, msb_first)):
        buff[i] = value & 0xFF
        value >>= 8
    return buff
