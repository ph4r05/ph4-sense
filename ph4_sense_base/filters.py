def compute_median(arr, ln=None):
    arr.sort()
    length = ln if ln is not None else len(arr)

    if length % 2 == 0:
        mid1 = length // 2
        mid2 = mid1 - 1
        median = (arr[mid1] + arr[mid2]) / 2
    else:
        mid = length // 2
        median = arr[mid]

    return median


class Deque:
    def __init__(self, iterable, maxlen: int):
        self._deque = [None] * maxlen
        self._maxlen = maxlen
        self._front = 0
        self._size = 0
        if iterable:
            if len(iterable) > maxlen:
                raise ValueError("Iterable bigger than maxlen")
            for ix, val in enumerate(iterable):
                self._deque[ix] = val
            self._size = len(iterable)

    def append(self, item):
        self._deque[(self._front + self._size) % self._maxlen] = item
        if self._maxlen is not None and self._size >= self._maxlen:
            self._front = (self._front + 1) % self._maxlen
        self._size = min(self._size + 1, self._maxlen)

    def popleft(self):
        if self._size == 0:
            raise IndexError("deque is empty")
        item = self._deque[self._front]
        self._deque[self._front] = None
        self._front = (self._front + 1) % self._maxlen
        self._size = max(self._size - 1, 0)
        return item

    def __iter__(self):
        for i in range(self._size):
            yield self._deque[(self._front + i) % self._maxlen]

    def __len__(self):
        return self._size


class ExpAverage:
    def __init__(self, alpha=0.1, default=None):
        self.alpha = alpha
        self.average = default

    def update(self, value):
        if self.average is None:
            self.average = value
        else:
            self.average = self.alpha * value + (1 - self.alpha) * self.average
        return self.average

    @property
    def cur(self):
        return self.average


class FloatingMedian:
    def __init__(self, window_size=5):
        self.window_size = window_size
        self.data = Deque((), window_size)  # deque((), window_size)
        self.buffer = [0] * window_size
        self._median = None

    def add(self, value):
        if value is None:
            return
        self._median = None
        self.data.append(value)

    def update(self, value):
        self.add(value)
        return self.median()

    def median(self):
        ldata = len(self.data)
        if self._median is None and ldata > 0:
            # As deque on micropython is not iterable, we just repull elements. Custom deque implementation would be better
            # for ix in range(ldata):
            #    self.buffer[ix] = self.data.popleft()
            # for ix in range(ldata):
            #    self.data.append(self.buffer[ix])
            for ix, x in enumerate(self.data):
                self.buffer[ix] = x

            self._median = compute_median(self.buffer, ldata)

        return self._median

    @property
    def cur(self):
        return self.median()


class SensorFilter:
    def __init__(self, median_window=5, alpha=0.1):
        self.floating_median = FloatingMedian(median_window)
        self.exp_average = ExpAverage(alpha)

    def update(self, value):
        r = self.floating_median.update(value)
        if r is not None:
            return self.exp_average.update(r)
        return None

    @property
    def cur(self):
        return self.exp_average.cur

    @property
    def cur_median(self):
        return self.floating_median.cur
