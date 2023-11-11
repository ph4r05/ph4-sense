import math

# Try importing Micropython const for usage in Mpy, optimization
try:
    from micropython import const
except ImportError:

    def const(x):
        return x


__version__ = "3.2.0"
__docs__ = "https://github.com/Sensirion/gas-index-algorithm"


class GasIndexAlgorithm:
    ALGORITHM_TYPE_VOC = const(0)
    ALGORITHM_TYPE_NOX = const(1)
    DEFAULT_SAMPLING_INTERVAL = const(1.0)
    INITIAL_BLACKOUT = const(45.0)
    INDEX_GAIN = const(230.0)
    SRAW_STD_INITIAL = const(50.0)
    SRAW_STD_BONUS_VOC = const(220.0)
    SRAW_STD_NOX = const(2000.0)
    TAU_MEAN_HOURS = const(12.0)
    TAU_VARIANCE_HOURS = const(12.0)
    TAU_INITIAL_MEAN_VOC = const(20.0)
    TAU_INITIAL_MEAN_NOX = const(1200.0)
    INIT_DURATION_MEAN_VOC = const(3600.0 * 0.75)
    INIT_DURATION_MEAN_NOX = const(3600.0 * 4.75)
    INIT_TRANSITION_MEAN = const(0.01)
    TAU_INITIAL_VARIANCE = const(2500.0)
    INIT_DURATION_VARIANCE_VOC = const(3600.0 * 1.45)
    INIT_DURATION_VARIANCE_NOX = const(3600.0 * 5.70)
    INIT_TRANSITION_VARIANCE = const(0.01)
    GATING_THRESHOLD_VOC = const(340.0)
    GATING_THRESHOLD_NOX = const(30.0)
    GATING_THRESHOLD_INITIAL = const(510.0)
    GATING_THRESHOLD_TRANSITION = const(0.09)
    GATING_VOC_MAX_DURATION_MINUTES = const(60.0 * 3.0)
    GATING_NOX_MAX_DURATION_MINUTES = const(60.0 * 12.0)
    GATING_MAX_RATIO = const(0.3)
    SIGMOID_L = const(500.0)
    SIGMOID_K_VOC = const(-0.0065)
    SIGMOID_X0_VOC = const(213.0)
    SIGMOID_K_NOX = const(-0.0101)
    SIGMOID_X0_NOX = const(614.0)
    VOC_INDEX_OFFSET_DEFAULT = const(100.0)
    NOX_INDEX_OFFSET_DEFAULT = const(1.0)
    LP_TAU_FAST = const(20.0)
    LP_TAU_SLOW = const(500.0)
    LP_ALPHA = const(-0.2)
    VOC_SRAW_MINIMUM = const(20000)
    NOX_SRAW_MINIMUM = const(10000)
    PERSISTENCE_UPTIME_GAMMA = const(3.0 * 3600.0)
    TUNING_INDEX_OFFSET_MIN = const(1)
    TUNING_INDEX_OFFSET_MAX = const(250)
    TUNING_LEARNING_TIME_OFFSET_HOURS_MIN = const(1)
    TUNING_LEARNING_TIME_OFFSET_HOURS_MAX = const(1000)
    TUNING_LEARNING_TIME_GAIN_HOURS_MIN = const(1)
    TUNING_LEARNING_TIME_GAIN_HOURS_MAX = const(1000)
    TUNING_GATING_MAX_DURATION_MINUTES_MIN = const(0)
    TUNING_GATING_MAX_DURATION_MINUTES_MAX = const(3000)
    TUNING_STD_INITIAL_MIN = const(10)
    TUNING_STD_INITIAL_MAX = const(5000)
    TUNING_GAIN_FACTOR_MIN = const(1)
    TUNING_GAIN_FACTOR_MAX = const(1000)
    MEAN_VARIANCE_ESTIMATOR__GAMMA_SCALING = const(64.0)
    MEAN_VARIANCE_ESTIMATOR__ADDITIONAL_GAMMA_MEAN_SCALING = const(8.0)
    MEAN_VARIANCE_ESTIMATOR__FIX16_MAX = const(32767.0)

    def __init__(self, algorithm_type, sampling_interval=DEFAULT_SAMPLING_INTERVAL):
        self.algorithm_type = algorithm_type
        self.sampling_interval = sampling_interval
        self.uptime = 0.0
        self.sraw = 0.0
        self.gas_index = 0.0
        self.mean_variance_estimator_initialized = False
        self.mean = None
        self.sraw_offset = None
        self.std = None
        self.adaptive_lowpass_initialized = None
        self.x1 = None
        self.x2 = None
        self.x3 = None
        self.index_offset = None
        self.sraw_minimum = None
        self.gating_max_duration_minutes = None
        self.init_duration_mean = None
        self.init_duration_variance = None
        self.gating_threshold = None
        self.index_gain = None
        self.tau_mean_hours = None
        self.tau_variance_hours = None
        self.sraw_std_initial = None
        self.mox_model_sraw_mean = None
        self.mox_model_sraw_std = None
        self.scaled_sigmoid_K = None
        self.scaled_sigmoid_X0 = None
        self.scaled_sigmoid_offset_default = None
        self.lowpass_A1 = None
        self.lowpass_A2 = None
        self.scaled_sigmoid_offset_default = None
        self.scaled_sigmoid_offset_default = None

        self.gamma_initial_mean = None
        self.gamma_initial_variance = None
        self.gamma_mean = None
        self.gamma_variance = None
        self.rgamma_mean = None
        self.rgamma_variance = None
        self.sigmoid_X0 = None
        self.sigmoid_K = None
        self.gating_duration_minutes = None
        self.uptime_gating = None
        self.uptime_gamma = None

        self.init_with_sampling_interval(algorithm_type, sampling_interval)

    def init_with_sampling_interval(self, algorithm_type, sampling_interval):  # OK
        self.algorithm_type = algorithm_type
        self.sampling_interval = sampling_interval
        if algorithm_type == self.ALGORITHM_TYPE_NOX:
            self.index_offset = self.NOX_INDEX_OFFSET_DEFAULT
            self.sraw_minimum = self.NOX_SRAW_MINIMUM
            self.gating_max_duration_minutes = self.GATING_NOX_MAX_DURATION_MINUTES
            self.init_duration_mean = self.INIT_DURATION_MEAN_NOX
            self.init_duration_variance = self.INIT_DURATION_VARIANCE_NOX
            self.gating_threshold = self.GATING_THRESHOLD_NOX
        else:
            self.index_offset = self.VOC_INDEX_OFFSET_DEFAULT
            self.sraw_minimum = self.VOC_SRAW_MINIMUM
            self.gating_max_duration_minutes = self.GATING_VOC_MAX_DURATION_MINUTES
            self.init_duration_mean = self.INIT_DURATION_MEAN_VOC
            self.init_duration_variance = self.INIT_DURATION_VARIANCE_VOC
            self.gating_threshold = self.GATING_THRESHOLD_VOC
        self.index_gain = self.INDEX_GAIN
        self.tau_mean_hours = self.TAU_MEAN_HOURS
        self.tau_variance_hours = self.TAU_VARIANCE_HOURS
        self.sraw_std_initial = self.SRAW_STD_INITIAL
        self.reset()  # Reset to initialize other parameters

    def reset(self):  # OK
        # Reset the internal states of the gas index algorithm
        self.uptime = 0.0  # Reset uptime
        self.sraw = 0.0  # Reset the last raw sensor value
        self.gas_index = 0  # Reset the gas index value

        self.init_instances()

    def init_instances(self):  # OK
        # Initialize mean variance estimator parameters
        self.mve_set_parameters()

        # Initialize parameters for the MOX model based on the mean variance estimator's current state
        self.mox_model_set_parameters(
            self.mve_get_std(),
            self.mve_get_mean(),
        )

        # Initialize parameters for the scaled sigmoid function
        if self.algorithm_type == self.ALGORITHM_TYPE_NOX:
            self.scaled_sigmoid_K = self.SIGMOID_K_NOX
            self.scaled_sigmoid_X0 = self.SIGMOID_X0_NOX
            self.scaled_sigmoid_offset_default = self.NOX_INDEX_OFFSET_DEFAULT
        else:  # Assuming VOC is the default algorithm type
            self.scaled_sigmoid_K = self.SIGMOID_K_VOC
            self.scaled_sigmoid_X0 = self.SIGMOID_X0_VOC
            self.scaled_sigmoid_offset_default = self.VOC_INDEX_OFFSET_DEFAULT

        # Initialize adaptive lowpass filter parameters
        self.adaptive_lowpass_set_parameters()

    def process(self, sraw):  # OK
        if self.uptime <= self.INITIAL_BLACKOUT:
            self.uptime += self.sampling_interval
        else:
            if 0 < sraw < 65000:
                if sraw < (self.sraw_minimum + 1):
                    sraw = self.sraw_minimum + 1
                elif sraw > (self.sraw_minimum + 32767):
                    sraw = self.sraw_minimum + 32767
                self.sraw = float(sraw - self.sraw_minimum)

            if self.algorithm_type == self.ALGORITHM_TYPE_VOC or self.mean_variance_estimator_initialized:
                self.gas_index = self.mox_model_process(self.sraw)
                self.gas_index = self.sigmoid_scaled_process(self.gas_index)
            else:
                self.gas_index = self.index_offset

            self.gas_index = self.adaptive_lowpass_process(self.gas_index)
            if self.gas_index < 0.5:
                self.gas_index = 0.5

            if self.sraw > 0.0:
                self.mve_process(self.sraw)
                self.mox_model_set_parameters(self.mve_get_std(), self.mve_get_mean())

        return self.get_gas_index()

    def get_gas_index(self):
        # Return the integer part of gas index by adding 0.5 for rounding
        return int(self.gas_index + 0.5)

    def mve_sigmoid_set_parameters(self, x0, k):  # OK
        self.sigmoid_X0 = x0
        self.sigmoid_K = k

    def mox_model_set_parameters(self, sraw_std, sraw_mean):  # OK
        self.mox_model_sraw_std = sraw_std
        self.mox_model_sraw_mean = sraw_mean

    def mve_get_std(self):  # OK
        return self.std

    def mve_get_mean(self):  # OK
        return self.mean + self.sraw_offset

    def adaptive_lowpass_set_parameters(self):  # OK
        # Set parameters for the adaptive lowpass filter
        self.lowpass_A1 = self.sampling_interval / (self.LP_TAU_FAST + self.sampling_interval)
        self.lowpass_A2 = self.sampling_interval / (self.LP_TAU_SLOW + self.sampling_interval)
        self.adaptive_lowpass_initialized = False

    def mve_set_parameters(self):  # OK
        self.mean_variance_estimator_initialized = False
        self.mean = 0.0
        self.sraw_offset = 0.0
        self.std = self.sraw_std_initial

        self.gamma_mean = (
            self.MEAN_VARIANCE_ESTIMATOR__ADDITIONAL_GAMMA_MEAN_SCALING
            * self.MEAN_VARIANCE_ESTIMATOR__GAMMA_SCALING
            * self.sampling_interval
            / 3600.0
        ) / (self.tau_mean_hours + (self.sampling_interval / 3600.0))

        self.gamma_variance = (self.MEAN_VARIANCE_ESTIMATOR__GAMMA_SCALING * self.sampling_interval / 3600.0) / (
            self.tau_variance_hours + (self.sampling_interval / 3600.0)
        )

        if self.algorithm_type == self.ALGORITHM_TYPE_NOX:
            self.gamma_initial_mean = (
                self.MEAN_VARIANCE_ESTIMATOR__ADDITIONAL_GAMMA_MEAN_SCALING
                * self.MEAN_VARIANCE_ESTIMATOR__GAMMA_SCALING
                * self.sampling_interval
            ) / (self.TAU_INITIAL_MEAN_NOX + self.sampling_interval)
        else:
            self.gamma_initial_mean = (
                self.MEAN_VARIANCE_ESTIMATOR__ADDITIONAL_GAMMA_MEAN_SCALING
                * self.MEAN_VARIANCE_ESTIMATOR__GAMMA_SCALING
                * self.sampling_interval
            ) / (self.TAU_INITIAL_MEAN_VOC + self.sampling_interval)

        self.gamma_initial_variance = (self.MEAN_VARIANCE_ESTIMATOR__GAMMA_SCALING * self.sampling_interval) / (
            self.TAU_INITIAL_VARIANCE + self.sampling_interval
        )
        self.rgamma_mean = 0.0
        self.rgamma_variance = 0.0
        self.uptime_gamma = 0.0
        self.uptime_gating = 0.0
        self.gating_duration_minutes = 0.0

    def mve_process(self, sraw):  # OK
        if not self.mean_variance_estimator_initialized:
            self.mean_variance_estimator_initialized = True
            self.sraw_offset = sraw
            self.mean = 0.0
        else:
            if self.mean >= 100.0 or self.mean <= -100.0:
                self.sraw_offset += self.mean
                self.mean = 0.0

            sraw -= self.sraw_offset
            self.mve_calculate_gamma()

            delta_sgp = (sraw - self.mean) / self.MEAN_VARIANCE_ESTIMATOR__GAMMA_SCALING
            c = self.std + delta_sgp if delta_sgp >= 0 else self.std - delta_sgp
            additional_scaling = 1.0 if c <= 1440.0 else (c / 1440.0) ** 2

            self.std = math.sqrt(
                additional_scaling * (self.MEAN_VARIANCE_ESTIMATOR__GAMMA_SCALING - self.rgamma_variance)
            ) * math.sqrt(
                (self.std**2 / (self.MEAN_VARIANCE_ESTIMATOR__GAMMA_SCALING * additional_scaling))
                + (self.rgamma_variance * delta_sgp**2 / additional_scaling)
            )

            self.mean += (self.rgamma_mean * delta_sgp) / self.MEAN_VARIANCE_ESTIMATOR__ADDITIONAL_GAMMA_MEAN_SCALING

    def mve_calculate_gamma(self):  # OK
        uptime_limit = self.MEAN_VARIANCE_ESTIMATOR__FIX16_MAX - self.sampling_interval
        if self.uptime_gamma < uptime_limit:
            self.uptime_gamma += self.sampling_interval
        if self.uptime_gating < uptime_limit:
            self.uptime_gating += self.sampling_interval

        self.mve_sigmoid_set_parameters(self.init_duration_mean, self.INIT_TRANSITION_MEAN)
        sigmoid_gamma_mean = self.mve_sigmoid__process(self.uptime_gamma)
        gamma_mean = self.gamma_mean + (self.gamma_initial_mean - self.gamma_mean) * sigmoid_gamma_mean

        gating_threshold_mean = self.gating_threshold + (
            self.GATING_THRESHOLD_INITIAL - self.gating_threshold
        ) * self.mve_sigmoid__process(self.uptime_gating)

        self.mve_sigmoid_set_parameters(gating_threshold_mean, self.GATING_THRESHOLD_TRANSITION)
        sigmoid_gating_mean = self.mve_sigmoid__process(self.gas_index)
        self.rgamma_mean = sigmoid_gating_mean * gamma_mean

        self.mve_sigmoid_set_parameters(self.init_duration_variance, self.INIT_TRANSITION_VARIANCE)
        sigmoid_gamma_variance = self.mve_sigmoid__process(self.uptime_gamma)
        gamma_variance = self.gamma_variance + (self.gamma_initial_variance - self.gamma_variance) * (
            sigmoid_gamma_variance - sigmoid_gamma_mean
        )

        gating_threshold_variance = self.gating_threshold + (
            self.GATING_THRESHOLD_INITIAL - self.gating_threshold
        ) * self.mve_sigmoid__process(self.uptime_gating)

        self.mve_sigmoid_set_parameters(gating_threshold_variance, self.GATING_THRESHOLD_TRANSITION)
        sigmoid_gating_variance = self.mve_sigmoid__process(self.gas_index)
        self.rgamma_variance = sigmoid_gating_variance * gamma_variance

        self.gating_duration_minutes += (self.sampling_interval / 60.0) * (
            ((1.0 - sigmoid_gating_mean) * (1.0 + self.GATING_MAX_RATIO)) - self.GATING_MAX_RATIO
        )
        if self.gating_duration_minutes < 0.0:
            self.gating_duration_minutes = 0.0
        if self.gating_duration_minutes > self.gating_max_duration_minutes:
            self.uptime_gating = 0.0

    def mox_model_process(self, sraw):  # OK
        # Adjusts the sensor raw signal based on the MOX model
        if self.algorithm_type == self.ALGORITHM_TYPE_NOX:
            return ((sraw - self.mox_model_sraw_mean) / self.SRAW_STD_NOX) * self.index_gain
        else:  # Assuming VOC is the default type
            return (
                (sraw - self.mox_model_sraw_mean) / (-1 * (self.mox_model_sraw_std + self.SRAW_STD_BONUS_VOC))
            ) * self.index_gain

    def mve_sigmoid__process(self, sample):  # OK
        x = self.sigmoid_K * (sample - self.sigmoid_X0)
        # Preventing overflow in exponential function
        if x < -50.0:
            sigmoid = 1.0
        elif x > 50.0:
            sigmoid = 0.0
        else:
            sigmoid = 1.0 / (1.0 + math.exp(x))
        return sigmoid

    def sigmoid_scaled_process(self, sample):  # OK
        # Calculate the sigmoid function with scaling based on the sample input
        x = self.scaled_sigmoid_K * (sample - self.scaled_sigmoid_X0)

        # Check for extreme values to prevent math range errors
        if x < -50.0:
            return self.SIGMOID_L
        elif x > 50.0:
            return 0.0

        # Apply scaling based on the offset
        if sample >= 0.0:
            if self.scaled_sigmoid_offset_default == 1.0:
                shift = (500.0 / 499.0) * (1.0 - self.index_offset)
            else:
                shift = (self.SIGMOID_L - (5.0 * self.index_offset)) / 4.0

            return ((self.SIGMOID_L + shift) / (1.0 + math.exp(x))) - shift
        else:
            return (self.index_offset / self.scaled_sigmoid_offset_default) * (self.SIGMOID_L / (1.0 + math.exp(x)))

    def adaptive_lowpass_process(self, sample):  # OK
        # Check if initialized, if not, initialize with the current sample
        if not self.adaptive_lowpass_initialized:
            self.x1 = sample
            self.x2 = sample
            self.x3 = sample
            self.adaptive_lowpass_initialized = True

        # Apply the first low pass filter
        self.x1 = (1.0 - self.lowpass_A1) * self.x1 + self.lowpass_A1 * sample
        # Apply the second low pass filter
        self.x2 = (1.0 - self.lowpass_A2) * self.x2 + self.lowpass_A2 * sample

        # Calculate the absolute difference between the filtered values
        abs_delta = abs(self.x1 - self.x2)

        # Calculate the filter factor based on the delta
        f1 = math.exp(self.LP_ALPHA * abs_delta)
        tau_a = (self.LP_TAU_SLOW - self.LP_TAU_FAST) * f1 + self.LP_TAU_FAST
        a3 = self.sampling_interval / (tau_a + self.sampling_interval)

        # Apply the adaptive filter
        self.x3 = (1.0 - a3) * self.x3 + a3 * sample

        return self.x3


class NoxGasIndexAlgorithm(GasIndexAlgorithm):
    def __init__(self, sampling_interval=GasIndexAlgorithm.DEFAULT_SAMPLING_INTERVAL):
        super().__init__(GasIndexAlgorithm.ALGORITHM_TYPE_NOX, sampling_interval)


class VocGasIndexAlgorithm(GasIndexAlgorithm):
    def __init__(self, sampling_interval=GasIndexAlgorithm.DEFAULT_SAMPLING_INTERVAL):
        super().__init__(GasIndexAlgorithm.ALGORITHM_TYPE_VOC, sampling_interval)
