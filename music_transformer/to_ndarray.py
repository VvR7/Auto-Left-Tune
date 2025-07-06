import mido
import matplotlib.pyplot as plt


import mido
import numpy as np
import mido
import numpy as np
from collections import defaultdict


def midi_to_ndarray(track, quantization=10):
    """
    将 MIDI 文件转换为一个序列，每个最小时间单位对应一个序列元素，元素格式为 ((type, note), bool_pause)。

    转换规则：
      1. 处理 note_on 和 note_off：
         - note_on 且 velocity > 0 记为 ("note_on", note)
         - note_on 且 velocity == 0 视作 note_off 记为 ("note_off", note)
         - note_off 记为 ("note_off", note)
      2. 将每个事件根据其绝对时间（tick）量化到时间步： quantized_time = int(absolute_time // quantization)
      3. 构造返回序列时：
         - 遍历从 time_step = 0 到最后事件的量化时间；
         - 如果某个时间步没有事件，则置入 (( "padding", None ), False)；
         - 如果某个时间步内有一个或多个事件，则按事件出现顺序添加：
             * 同一时间步内，第一个事件 bool_pause 设为 False，
             * 后续事件设为 True（表示和上一个事件在同一时间按下）。

    参数：
      filepath: MIDI 文件路径。
      quantization: 每个最小时间步对应的 tick 数，默认值为10。

    返回：
      一个 numpy.ndarray 序列，每个元素为 ((type, note), bool_pause)。
      例如：[ (("note_on", 60), False), (("note_on", 64), True), (("padding", None), False), ... ]
    """

    events = []  # 用于存储 (absolute_time, token) 的元组，其中 token 为 ("note_on", note) 或 ("note_off", note)

    # 遍历所有 track 计算绝对时间并筛选 note_on / note_off 事件

    absolute_time = 0
    for msg in track:
        absolute_time += msg.time  # 累加 delta time 得到绝对时间
        if msg.type == 'note_on':
            if msg.velocity > 0:
                token = ("note_on", msg.note)
                events.append((absolute_time, token))
            else:
                # velocity==0 按作 note_off
                token = ("note_off", msg.note)
                events.append((absolute_time, token))
        elif msg.type == 'note_off':
            token = ("note_off", msg.note)
            events.append((absolute_time, token))

    if not events:
        return np.array([])

    # 对所有事件按绝对时间排序，便于后续处理
    events.sort(key=lambda x: x[0])

    # 将事件按量化时间分组
    events_by_timestep = defaultdict(list)
    for abs_time, token in events:
        t_step = int(abs_time // quantization)
        events_by_timestep[t_step].append(token)

    # 确定序列的总时间步（从 0 到最后一个事件时间步）
    max_timestep = max(events_by_timestep.keys())

    result = []  # 每个元素为 ((type, note), bool_pause)
    # 遍历所有时间步0 ... max_timestep，缺失的时间步填充 padding
    for t in range(0, max_timestep + 1):
        if t in events_by_timestep:
            tokens = events_by_timestep[t]
            # 对同一时间步中的多个事件，依次添加，首个事件 bool_pause = False，其余设为 True
            for i, token in enumerate(tokens):
                if i == 0:
                    result.append((token, False))
                else:
                    result.append((token, True))
        else:
            # 没有事件的时间步，用 padding 填充
            result.append((("padding", None), False))

    return np.array(result, dtype=object)


def ndarray_to_track(seq, quantization=10, default_velocity=64):
    """
    将由 midi_to_ndarray 得到的序列转换回 MIDI Track。

    转换规则：
      - 序列中每个元素对应一个最小时间步（即 quantization 个 tick）。
      - 遍历序列，如果元素为 note 事件：
            若 bool_pause 为 False，则 delta time = (当前索引与上一个事件索引间隔)*quantization；
            若 bool_pause 为 True，则说明与前一事件同刻发生，此时 delta time = 0。
      - padding 元素不生成 MIDI 消息（仅用于表示无事件的时间步）。

    参数：
      seq: numpy.ndarray 序列，每个元素形如 ((type, note), bool_pause)。
      quantization: 最小时间步对应的 tick 数，与构造序列时一致。
      default_velocity: 对于 note_on 生成消息时使用的默认 velocity（note_off 时 velocity 固定为 0）。

    返回：
      一个 mido.MidiTrack 对象，其中包含根据序列生成的 MIDI 消息。
    """
    track = mido.MidiTrack()
    prev_event_index = None  # 用于记录上一个事件在序列中的索引

    # 遍历序列，索引 i 对应的时刻为 i * quantization
    for i, element in enumerate(seq):
        (token_type, note), bool_pause = element

        if token_type == "padding":
            # padding 不生成消息
            continue

        # 计算当前事件消息的 delta time
        if prev_event_index is None or bool_pause is False:
            # 如果与上一个事件间隔 >= 1 个最小时间步，则 delta = (i - prev_event_index)*quantization
            # 对于第一个事件，prev_event_index 为 None，则 delta = i * quantization
            if prev_event_index is None:
                delta_time = i * quantization
            else:
                delta_time = (i - prev_event_index) * quantization
        else:
            # 如果与上一个事件在同一时刻（bool_pause 为 True），则 delta time = 0
            delta_time = 0

        # 构造 MIDI 消息
        if token_type == "note_on":
            msg = mido.Message('note_on', note=note, velocity=default_velocity, time=delta_time)
        elif token_type == "note_off":
            msg = mido.Message('note_off', note=note, velocity=0, time=delta_time)
        else:
            # 不认识的类型，跳过
            continue

        track.append(msg)
        # 更新上一个事件的索引（注意：padding 不计入事件序列）
        prev_event_index = i

    # 最后添加 End Of Track 信息
    track.append(mido.MetaMessage('end_of_track', time=0))
    return track


# ---------------------------
# 示例：假设有一个 MIDI 文件，请先修改路径，再运行以下代码进行测试。
if __name__ == '__main__':
    midi_path = r"D:\Documents\AI训练数据集\钢琴\from_musescore\打上花火.mid"  # 替换成你的 MIDI 文件路径

    midi_file=mido.MidiFile(midi_path)

    track_right=midi_file.tracks[0]
    track_left=midi_file.tracks[1]


    # 将 MIDI 转换为新的 ndarray 序列，元素格式 ((type, note), bool_pause)
    seq_array_right = midi_to_ndarray(track_right, quantization=10)
    seq_array_left=midi_to_ndarray(track_left,quantization=10)



    # 利用序列重构 MIDI Track
    new_track_right = ndarray_to_track(seq_array_right, quantization=10, default_velocity=64)
    new_track_left = ndarray_to_track(seq_array_left,quantization=10,default_velocity=64)

    # 创建新的 MIDI 文件，并加入该 track
    new_mid = mido.MidiFile()
    new_mid.tracks.append(new_track_right)
    new_mid.tracks.append(new_track_left)
    new_mid.save(r"D:\Documents\AI训练数据集\钢琴\explore\test.mid")
    print("生成了 test.mid 文件。")









