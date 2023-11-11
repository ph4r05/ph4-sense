try:
    from typing import Optional
except ImportError:
    pass


class PreallocatedBuffer:
    """
    Static buffer allocator
    Minimizes number of allocations by pre-allocating given buffer.

    If caller requires buffer of a specific size (e.g., cannot use offsetting, caller
    expects buffer to be of a certain size so it can be read into), allocator creates memoryviews
    from the underlying buffer.
    """

    def __init__(self, max_size: int = 1):
        self.buffer = bytearray(max_size)
        self.max_size = max_size

    def get_raw(self) -> bytearray:
        """
        Returns underlying allocated buffer
        """
        return self.buffer

    def get(self, size: Optional[int] = None):
        """
        Returns buffer of a given size backed by pre-allocated buffer.
        If asked size
        """
        size = size if size is not None else self.max_size
        if size == self.max_size:
            return self.buffer
        elif size > self.max_size:
            raise ValueError(f"Max capacity {self.max_size} is lower than required size {size}")
        elif size <= 0:
            raise ValueError("Required size has to be greater than 0")
        return memoryview(self.buffer)[:size]

    def write(self, buffer, offset=0, length: Optional[int] = None, offset_dst=0):
        """
        Writes buffer to the underlying buffer
        """
        length = length if length is not None else len(buffer) - offset
        for i in range(length):
            self.buffer[offset_dst + i] = buffer[offset + i]
        return self.buffer
