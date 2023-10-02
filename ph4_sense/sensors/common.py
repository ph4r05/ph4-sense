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
