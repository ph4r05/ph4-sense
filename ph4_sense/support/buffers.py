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
