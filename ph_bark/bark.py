import json
import time
from queue import Queue
from threading import Thread

import librosa
import numpy as np
import paho.mqtt.client as mqtt  # paho-mqtt
import sounddevice as sd
from scipy.signal import stft


class Bark:
    def __init__(self):
        self.mqtt_client = None
        self.mqtt_broker = "localhost"
        self.mqtt_port = 1883
        self.mqtt_topic_sub = "bark"

        # Parameters
        self.sampling_rate = 22050  # Hz
        self.strip_duration = 0.05  # Duration to strip from the beginning in seconds
        self.frame_length = 2048
        self.hop_length = 512
        self.n_mels = 128  # Number of Mel bands
        self.bands = [0, 500, 1000, 2000, 4000, 8000]  # Hz
        mel_bands_spec = [0, 20, 40, 60, 80, 100, 128]
        self.mel_bands = [(mel_bands_spec[i], mel_bands_spec[i + 1]) for i in range(len(mel_bands_spec) - 1)]
        self.aggregation_type = "mean"  # Can be 'mean' or 'max'
        self.chunk_duration = 5  # Duration of each audio chunk in seconds
        self.queue_size = 300  # Maximum number of chunks to store in the queue

    def create_mqtt_client(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, "bark/liv")
        client.on_message = self.mqtt_callback
        client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
        client.subscribe(self.mqtt_topic_sub)
        return client

    def mqtt_callback(self, topic=None, msg=None):
        print("Received MQTT message:", topic, msg)

    def publish_msg(self, topic: str, message: str):
        self.mqtt_client.publish(topic, message)
        print(f"Published {topic}:", message)

    def publish_payload(self, topic: str, payload: dict):
        self.publish_msg(topic, json.dumps(payload))

    def publish(self, metrics):
        # Convert numpy arrays to lists and numpy types to native Python types for JSON serialization
        def convert_metrics(value):
            if isinstance(value, np.ndarray):
                return value.tolist()
            elif isinstance(value, (np.float32, np.float64, np.int32, np.int64)):
                return value.item()
            elif isinstance(value, list):
                return [convert_metrics(item) for item in value]
            elif isinstance(value, dict):
                return {k: convert_metrics(v) for k, v in value.items()}
            else:
                return value

        metrics_serializable = convert_metrics(metrics)
        self.publish_payload(
            "bark/liv",
            metrics_serializable,
        )

    def compute_metrics(self, audio):
        # Strip the first 0.2 seconds from the recording
        strip_samples = int(self.strip_duration * self.sampling_rate)
        audio = audio[strip_samples:]

        # Compute loudness (RMS energy)
        rms = librosa.feature.rms(y=audio, frame_length=self.frame_length, hop_length=self.hop_length)[0]

        # Compute zero-crossing rate
        zero_crossings = librosa.feature.zero_crossing_rate(
            y=audio, frame_length=self.frame_length, hop_length=self.hop_length
        )[0]

        # Compute MFCCs
        mfccs = librosa.feature.mfcc(y=audio, sr=self.sampling_rate, n_mfcc=13, hop_length=self.hop_length)

        # Compute mel spectrogram
        mel_spectrogram = librosa.feature.melspectrogram(
            y=audio, sr=self.sampling_rate, hop_length=self.hop_length, n_mels=self.n_mels
        )

        # Compute the energy for each mel band as a function of time
        mel_band_energies = []
        for band in self.mel_bands:
            band_energy = np.sum(mel_spectrogram[band[0] : band[1], :], axis=0)
            mel_band_energies.append(band_energy)

        # Compute Short-Time Fourier Transform (STFT)
        frequencies, times, Zxx = stft(audio, fs=self.sampling_rate, nperseg=1024)

        # Compute the energy for each frequency band as a function of time
        band_energies_timed = []
        for i in range(len(self.bands) - 1):
            band_indices = np.where((frequencies >= self.bands[i]) & (frequencies < self.bands[i + 1]))[0]
            band_energy2 = np.sum(np.abs(Zxx[band_indices, :]) ** 2, axis=0)
            band_energies_timed.append(band_energy2)

        return {
            "rms": rms,
            "zero_crossings": zero_crossings,
            "mfccs": mfccs,
            "mel_band_energies": mel_band_energies,
            "band_energies_timed": band_energies_timed,
            "times": times,
        }

    def aggregate_metrics(self, metrics_list, aggregation_type):
        aggregated_metrics = {
            "rms": [],
            "zero_crossings": [],
            "mfccs": None,
            "mel_band_energies": [],
            "band_energies_timed": [],
        }

        for metrics in metrics_list:
            for key in aggregated_metrics.keys():
                if key == "mfccs":
                    if aggregated_metrics[key] is None:
                        aggregated_metrics[key] = metrics[key]
                    else:
                        aggregated_metrics[key] = np.hstack((aggregated_metrics[key], metrics[key]))
                else:
                    aggregated_metrics[key].append(metrics[key])

        for key, value in aggregated_metrics.items():
            if key == "mfccs":
                if aggregation_type == "mean":
                    aggregated_metrics[key] = np.mean(aggregated_metrics[key], axis=1)
                else:
                    aggregated_metrics[key] = np.max(aggregated_metrics[key], axis=1)
            else:
                if isinstance(value[0], list):
                    aggregated_metrics[key] = [
                        np.mean(v) if aggregation_type == "mean" else np.max(v) for v in zip(*value)
                    ]
                else:
                    if key == "rms" or key == "zero_crossings":
                        aggregated_metrics[key] = np.mean(value) if aggregation_type == "mean" else np.max(value)
                    else:
                        aggregated_metrics[key] = (
                            np.mean(value, axis=0) if aggregation_type == "mean" else np.max(value, axis=0)
                        )

        return aggregated_metrics

    def audio_capture_thread(self, audio_queue, duration, sampling_rate):
        while True:
            audio = sd.rec(int(duration * sampling_rate), samplerate=sampling_rate, channels=1, dtype="float32")
            sd.wait()
            audio = audio.flatten()
            if audio_queue.qsize() < self.queue_size:
                audio_queue.put(audio)
            else:
                time.sleep(duration)

    def main_loop(self):
        self.mqtt_client = self.create_mqtt_client()

        audio_queue = Queue(maxsize=self.queue_size)
        capture_thread = Thread(
            target=self.audio_capture_thread, args=(audio_queue, self.chunk_duration, self.sampling_rate)
        )
        capture_thread.start()
        exp_list_size = 60 // self.chunk_duration

        while True:
            metrics_list = []

            tstart = time.time()
            tcomp = 0
            while len(metrics_list) < exp_list_size:
                if not audio_queue.empty():
                    audio = audio_queue.get()

                    tmet_stat = time.time()
                    metrics = self.compute_metrics(audio)
                    metrics_list.append(metrics)
                    tcomp += time.time() - tmet_stat
                else:
                    time.sleep(0.01)

            time_total = time.time() - tstart
            aggregated_metrics = self.aggregate_metrics(metrics_list, self.aggregation_type)
            self.publish(aggregated_metrics)
            print(f"Published, qsize: {audio_queue.qsize()}, est: {time_total}, comp: {tcomp}")


if __name__ == "__main__":
    bark = Bark()
    bark.main_loop()
