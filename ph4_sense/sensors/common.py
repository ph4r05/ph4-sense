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
