from ph4_sense.sensors.common import buf2int, get_ordering, int2buf


def test_main():
    assert True


def test_ordering():
    assert list(get_ordering(0, 1, True)) == [0]
    assert list(get_ordering(0, 4, True)) == [0, 1, 2, 3]
    assert list(get_ordering(0, 4, False)) == [3, 2, 1, 0]
    assert list(get_ordering(0, 1, False)) == [0]
    assert list(get_ordering(5, 4, True)) == [5, 6, 7, 8]
    assert list(get_ordering(5, 4, False)) == [8, 7, 6, 5]


def test_buf2int():
    assert buf2int([0xFF, 0xAA]) == (0xFF << 8) | 0xAA
    assert buf2int([0xFF, 0xAA], 0, 2, False) == 0xFF | (0xAA << 8)


def test_int2buf():
    assert int2buf((0xFF << 8) | 0xAA, None, 0, 2) == bytearray([0xFF, 0xAA])
    assert int2buf((0xFF << 8) | 0xAA, None, 0, 2, False) == bytearray([0xAA, 0xFF])
