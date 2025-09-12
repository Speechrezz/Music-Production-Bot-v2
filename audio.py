import numpy as np
import io
from pydub import AudioSegment
import time
import pyloudnorm as pyln
from dataclasses import dataclass

from matplotlib import pyplot as plt
from matplotlib import ticker

@dataclass
class Audio:
    data: np.ndarray
    sample_rate: int
    num_channels: int

    def get_mono_audio(self) -> np.ndarray:
        if self.num_channels > 1:
            return np.mean(self.data, axis=1)
        return self.data

def discord_bytes_to_numpy(data: bytes, filename: str):
    extension = filename.split(".")[-1]
    audio_segment = AudioSegment.from_file(io.BytesIO(data), format=extension)

    ref = float(1 << (audio_segment.sample_width * 8 - 1)) - 1.0  # e.g. 32767 for 16-bit
    audio = np.array(audio_segment.get_array_of_samples(), dtype=np.float64) / ref

    if audio_segment.channels > 1:
        audio = audio.reshape((-1, audio_segment.channels))

    return Audio(data=audio, sample_rate=audio_segment.frame_rate, num_channels=audio_segment.channels)

def generate_waveform(audio: Audio, data_stream: io.BytesIO, color: str | tuple[float, float, float]="blue", debug = False):
    y = audio.get_mono_audio()
    t = np.linspace(0, len(y) / audio.sample_rate, len(y))

    bg_color = (0.21176471, 0.22352941, 0.24313725)

    plt.figure(figsize=(8,3), facecolor=bg_color)
    plt.rcParams['xtick.color'] = "white"
    plt.rcParams['ytick.color'] = "white"
    plt.plot(t, y, color=color)
    ax = plt.gca()
    ax.get_yaxis().set_visible(debug)
    ax.set_facecolor(bg_color)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    formatter = ticker.FuncFormatter(lambda s, x: time.strftime('%M:%S', time.gmtime(s)))
    ax.xaxis.set_major_formatter(formatter)
    plt.plot([0, t[-1]], [0, 0], color=bg_color, linewidth=0.5)

    # Save content into the data stream
    plt.tight_layout()
    plt.savefig(data_stream, format='png', bbox_inches="tight", dpi = 100)
    plt.close()
    data_stream.seek(0)

def get_loudness_str(audio: Audio, debug = False):
    y = audio.get_mono_audio()
    max_loudness = np.max(y)
    try:
        # measure the loudness first 
        meter = pyln.Meter(audio.sample_rate) # create BS.1770 meter
        loudness = meter.integrated_loudness(y)
    except ValueError: # is thrown if file is too short
        if debug:
            return f"max_loudness={max_loudness:.2f}"
        return ""
    if debug:
        return f"{loudness:.2f} LUFS, max_loudness={max_loudness:.2f}"
    return f"**Integrated Loudness:** {loudness:.2f} LUFS"