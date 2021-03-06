import os
import shutil
import time

import librosa
import numpy as np
from tqdm import tqdm


def corrected_length(clean_y, noise_y):
    """
    合成带噪语音前的长度矫正，使 len(clean_y) == len(noise_y)
    """
    if len(clean_y) < len(noise_y):
        return clean_y, noise_y[:len(clean_y)]
    elif len(clean_y) > len(noise_y):
        pad_factor = (len(clean_y) // len(noise_y))  # 拓展系数为需要拓展的次数，不是总数
        padded_noise_y = noise_y
        for i in range(pad_factor):
            padded_noise_y = np.concatenate((padded_noise_y, noise_y))
        noise_y = padded_noise_y
        return clean_y, noise_y[:len(clean_y)]
    else:
        return clean_y, noise_y

def cal_lps(y, pad=0):
    D = librosa.stft(y, n_fft=512, hop_length=256, window='hamming')
    mag = np.abs(D)
    lps = np.log(np.power(mag, 2))
    if (pad != 0):
        lps = np.concatenate((np.zeros((257, pad)), lps, np.zeros((257, pad))), axis=1)
    return lps

def lps_to_mag(lps):
    return np.power(np.exp(lps), 1 / 2)

def rebuild_waveform(mag, noisy_phase):
    return librosa.istft(mag * noisy_phase, hop_length=256, win_length=512, window='hamming')

def phase(y):
    D = librosa.stft(y, n_fft=512, hop_length=256, window='hamming')
    _, phase = librosa.magphase(D)
    return phase

class ExecutionTime:
    """
    Usage:
        timer = ExecutionTime()
        <Something...>
        print(f'Finished in {timer.duration()} seconds.')
    """


    def __init__(self):
        self.start_time = time.time()


    def duration(self):
        return time.time() - self.start_time


def find_aligned_wav_files(dir_a, dir_b, limit=0, offset=0):
    """
    搜索 dir_A 与 dir_B 根目录下的 wav 文件，要求：
        - 两个目录中的 wav 文件数量相等
        - 索引相同，文件名也相同，排序方式按照 Python 內建的 .sort() 函数
    Args:
        dir_a:  目录 A
        dir_b: 目录 B
        limit: 加载 wav 文件的数量限制
        offset: 开始位置的偏移索引
    Notes:
        length:
            1. limit == 0 and limit > len(wav_paths_in_dir_a) 时，length 为 目录下所有文件
            2. limit <= len(wav_paths_in_dir_a) 时，length = limit
    """

    if limit == 0:
        # 当 limit == None 时，librosa 会加载全部文件
        limit = None

    wav_paths_in_dir_a = librosa.util.find_files(dir_a, ext="wav", limit=limit, offset=offset)
    wav_paths_in_dir_b = librosa.util.find_files(dir_b, ext="wav", limit=limit, offset=offset)

    length = len(wav_paths_in_dir_a)

    # 两个目录数量相等，且文件数量 > 0
    assert len(wav_paths_in_dir_a) == len(wav_paths_in_dir_b) > 0, f"目录 {dir_a} 和目录 {dir_b} 文件数量不同或目录为空"

    # 两个目录中的 wav 文件应当文件名一一对应
    for wav_path_a, wav_path_b in zip(wav_paths_in_dir_a, wav_paths_in_dir_b):
        assert os.path.basename(wav_path_a) == os.path.basename(wav_path_b), \
            f"{wav_path_a} 与 {wav_path_a} 不对称，这可能由于两个目录文件数量不同"

    return wav_paths_in_dir_a, wav_paths_in_dir_b, length


def set_requires_grad(nets, requires_grad=False):
    """
    修改多个网络梯度
    Args:
        nets: list of networks
        requires_grad: 是否需要梯度
    """

    if not isinstance(nets, list):
        nets = [nets]
    for net in nets:
        if net is not None:
            for param in net.parameters():
                param.requires_grad = requires_grad


def sample_fixed_length_data_aligned(data_a, data_b, sample_length):
    """
    对 data_a 与 data_b 进行对齐采样
    Args:
        data_a:
        data_b:
        sample_length: 采样的点数
    """
    assert len(data_a) == len(data_b), "数据长度不一致，无法完成定长采样"
    assert len(data_a) >= sample_length, f"len(data_a) is {len(data_a)}, sample_length is {sample_length}."

    frames_total = len(data_a)

    start = np.random.randint(frames_total - sample_length + 1)
    print(f"Random crop from: {start}")
    end = start + sample_length

    return data_a[start:end], data_b[start:end]


def sample_dataset_aligned(dataset_A, dataset_B, n_frames=128):
    """
    将变长的数据样本采样为定长的数据样本
    Args:
        dataset_A: 数据集 A，内部元素为变长，比如为 [[128, 325], [128, 356], ...]
        dataset_B: 数据集 B，内部元素为变长, 比如为 [[128, 325], [128, 356], ...]
        n_frames: 采样的帧数，默认为 128
    Returns:
        采样后的数据集 A，内部元素为定长: [[128, 128], [128, 128], ...]
        采样后的数据集 B，内部元素为定长: [[128, 128], [128, 128], ...]
    """

    data_A_idx = np.arange(len(dataset_A))
    data_B_idx = np.arange(len(dataset_B))

    sampling_dataset_A = list()
    sampling_dataset_B = list()

    for idx_A, idx_B in zip(data_A_idx, data_B_idx):
        # 获取样本
        data_A = dataset_A[idx_A]
        data_B = dataset_B[idx_B]

        # 样本中的帧数
        frames_A_total = data_A.shape[1]
        frames_B_total = data_B.shape[1]
        assert frames_A_total == frames_B_total, "A 样本和 B 样本的帧数不同，样本的索引为 {}.".format(idx_A)

        # 确定采样的起止位置，将变长样本采样为定长样本
        assert frames_A_total >= n_frames
        start = np.random.randint(frames_A_total - n_frames + 1)
        end = start + n_frames
        sampling_dataset_A.append(data_A[:, start: end])
        sampling_dataset_B.append(data_B[:, start: end])

    sampling_dataset_A = np.array(sampling_dataset_A)
    sampling_dataset_B = np.array(sampling_dataset_B)

    return sampling_dataset_A, sampling_dataset_B


def prepare_empty_dirs(dirs: list):
    """
    建立空目录。若已经存在，则删除后创建。
    parents=True

    Args:
        dirs: Path list

    Returns:
        dirs 中各个目录的句柄
    """
    result = []
    for d in dirs:
        if d.exists():
            shutil.rmtree(d.as_posix())
        d.mkdir(parents=True, exist_ok=False)
        result.append(d)
    return result


def load_wavs(file_paths, limit=None, sr=16000, minimum_sampling=0):
    """
    根据 file_paths 逐个加载 wav 文件

    可以指定：
    - wav 文件需要满足的最小采样点数
    - 需要加载的 wav 文件数量，直到遍历完整个 list 或 满足了 limit 指定的数量要求

    Args:
        file_paths: 候选集合，其中采样点数大于 minimum_sampling 的 wav 才能被加载成功
        limit: 要求加载的数量上限
        sr: 采样率
        minimum_sampling: 最小采样点数

    """
    wavs = []
    i = 0

    if not limit:
        limit = len(file_paths)

    p_bar = tqdm(total=limit, desc="Loading WAV files")

    while i < limit:
        wav, _ = librosa.load(file_paths[i], sr=sr)
        if len(wav) >= minimum_sampling:
            p_bar.update(1)
            wavs.append(wav)
            i += 1

    p_bar.close()
    return wavs

def get_name_and_ext(path):
    name, ext = os.path.splitext(os.path.basename(path))
    return name, ext


def load_noises(noise_wav_paths):
    """
    根据噪声列表加载噪声
    Args:
        noise_wav_paths (list): 噪声文件的路径列表

    Returns:
        dict: {"babble": [signals]}
    """
    out = {}
    for noise_path in tqdm(noise_wav_paths, desc="Loading noises: "):
        name, _ = get_name_and_ext(noise_path)
        wav, _ = librosa.load(noise_path, sr=16000)
        out[name] = wav

    return out


def add_noise_for_waveform(s, n, db):
    """
    为语音文件叠加噪声
    ----
    para:
        s：原语音的时域信号
        n：噪声的时域信号
        db：信噪比
    ----
    return:
        叠加噪声后的语音
    """
    alpha = np.sqrt(
        np.sum(s ** 2) / (np.sum(n ** 2) * 10 ** (db / 10))
    )
    mix = s + alpha * n
    return mix
