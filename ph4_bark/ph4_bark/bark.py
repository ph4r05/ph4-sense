import json
import os
import queue
import socket
import time
from queue import Queue
from threading import Thread
from typing import Union

import librosa
import numpy as np
import paho.mqtt.client as mqtt  # paho-mqtt
import sounddevice as sd
from scipy.signal import stft


def get_hostname():
    return socket.gethostname()


def str2bool(value: Union[None, bool, str]) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("yes", "true", "t", "1")
    return False


class Bark:
    BIRTH_TOPIC = "homeassistant/status"

    def __init__(self):
        self.mqtt_client = None
        self.mqtt_broker = os.getenv("MQTT_BROKER", "localhost")
        self.mqtt_port = 1883
        self.mqtt_topic_recv = self.build_mqtt_topic()
        self.mqtt_topic_sub = self.mqtt_topic_recv + "/sub"

        # Parameters
        self.sampling_rate = 44100  # 22050  # Hz
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
        self.discovery_sent = False
        self.add_host_suffix = str2bool(os.getenv("ADD_HOST_SUFFIX", "0"))

    @classmethod
    def build_mqtt_topic(cls) -> str:
        return os.getenv("MQTT_TOPIC", f"bark/{get_hostname()}")

    @classmethod
    def topic_normalize(cls, topic: str) -> str:
        return topic.replace("/", "_").replace("-", "_").replace(".", "_").replace(" ", "_").lower()

    def create_mqtt_client(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, self.mqtt_topic_recv)
        client.on_message = self.mqtt_callback
        client.connect(self.mqtt_broker, self.mqtt_port, keepalive=60)
        client.subscribe(self.mqtt_topic_sub)
        client.subscribe(self.BIRTH_TOPIC)
        return client

    def mqtt_callback(self, client, userdata, message, *args, **kwargs):
        topic = message.topic
        payload = message.payload.decode()
        print(f"Received MQTT message: {client=}, {userdata=}, {message=}, {topic=}, {payload=}")
        if topic == self.BIRTH_TOPIC and payload == "online":
            self.discovery_sent = False

    def publish_msg(self, topic: str, message: str):
        self.mqtt_client.publish(topic, message)
        print(f"Published {topic}:", message)

    def publish_payload(self, topic: str, payload: dict):
        self.send_auto_discovery(topic, payload)
        self.publish_msg(topic, json.dumps(payload))

    def send_auto_discovery(self, topic: str, payload: dict):
        if self.discovery_sent:
            return

        # Published fields descriptors
        desc = (
            [
                ("RMS", "rms"),
                ("ZC", "zero_crossings"),
            ]
            + [(f"MFCC {i}", f"mfccs[{i}]") for i in range(1, 13)]
            + [(f"MelB {i}", f"mel_band_energies[{i}]") for i in range(1, 6)]
            + [(f"Fband {i+1}", f"band_energies_timed[{i}]") for i in range(1, 6)]
        )

        suffix = f" {get_hostname()}" if self.add_host_suffix else ""
        for key, value in desc:
            unique_id = f"{self.topic_normalize(topic)}_{self.topic_normalize(key)}"
            discovery_topic = f"homeassistant/sensor/{unique_id}/config"
            unit = "db"

            discovery_payload = {
                "name": f"Bark {key}{suffix}",
                "state_topic": topic,
                "unit_of_measurement": unit,
                "value_template": "{{ value_json.%s }}" % value,
                "json_attributes_topic": topic,
                "unique_id": unique_id,
                "device": {
                    "identifiers": [get_hostname()],
                    "name": get_hostname(),
                    "manufacturer": "PH4",
                    "model": "Bark",
                },
            }
            self.publish_msg(discovery_topic, json.dumps(discovery_payload))
            print(f"Published auto-discovery to {discovery_topic}: {discovery_payload}")

        self.discovery_sent = True

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
            self.mqtt_topic_recv,
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

    def publisher_thread(self, audio_queue, publish_queue):
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
            publish_queue.put(aggregated_metrics)
            print(f"Published, qsize: {audio_queue.qsize()}, est: {time_total}, comp: {tcomp}")

    def main_loop(self):
        print(
            f"Starting Ph4bark, {self.mqtt_broker=}, {self.mqtt_port=}, {self.mqtt_topic_recv=}, {self.mqtt_topic_sub=}"
        )
        while True:
            try:
                self.mqtt_client = self.create_mqtt_client()
                print("MQTT client connected")
                break
            except Exception as e:
                print(f"Error in MQTT client {e}")
                time.sleep(60)

        audio_queue = Queue(maxsize=self.queue_size)
        publish_queue = Queue(maxsize=10)
        capture_thread = Thread(
            target=self.audio_capture_thread, args=(audio_queue, self.chunk_duration, self.sampling_rate)
        )
        capture_thread.daemon = True
        capture_thread.start()

        publish_thread = Thread(target=self.publisher_thread, args=(audio_queue, publish_queue))
        publish_thread.daemon = True
        publish_thread.start()

        while True:
            tstart = time.time()
            while time.time() - tstart < 60:
                try:
                    self.mqtt_client.loop(timeout=1.0)  # Process network events
                except Exception as e:
                    print(f"Error in MQTT loop {e}")
                    break

                while not publish_queue.empty():
                    try:
                        metrics = publish_queue.get(block=False)
                        self.publish(metrics)
                        print(f"Publish message sent, queue size: {publish_queue.qsize()}")
                    except queue.Empty:
                        continue
                    except Exception as e:
                        print(f"Error while publishing message {e}")
                time.sleep(0.0001)  # Yield to allow other tasks to run


if __name__ == "__main__":
    bark = Bark()
    bark.main_loop()
