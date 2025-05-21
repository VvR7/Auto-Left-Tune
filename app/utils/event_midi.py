import mido
import matplotlib.pyplot as plt


import mido
import numpy as np
import mido
import numpy as np
from collections import defaultdict


def midi_to_event(track, quantization=10,max_time=1500):
    """
        将 MIDI 文件转换为一个列表，列表中的每个元素为(type,val)
        type为"time_shift"时val表示相对时间间隔（基于quantization量化的）
        type为“note_on”或“note_off”时，val表示note的值
        type还可以是"bos" 或“eos”,"pad"
    """
    events=[]
    events.append(("bos",0))
    shift_time=0
    for msg in track:
        if msg.type in ["note_on","note_off"]:
            shift_time+=msg.time
            shift_time=min(shift_time//quantization,max_time//quantization)
            events.append(("shift_time",shift_time))
            if msg.velocity==0:
                events.append(("note_off", msg.note))
                shift_time = 0
            else:
                events.append((msg.type,msg.note))
                shift_time = 0

        else:
            shift_time+=msg.time
    events.append(("eos",0))
    return events

def event_to_midi(events,quantization=10):
    '''
    末尾加上end_of_track
    '''
    time=0
    track=mido.MidiTrack()
    for event in events:
        msg_type=event[0]
        msg_note=event[1]
        if msg_type=="shift_time":
            time=msg_note
        elif msg_type in ["bos","eos","pad"]:
            if msg_type=="eos":
                track.append(mido.MetaMessage("end_of_track",time=1))
                break
        else:
            if msg_type=="note_on":
                track.append(mido.Message(msg_type,note=msg_note,velocity=64,time=time*quantization))
            else:
                track.append(mido.Message(msg_type, note=msg_note, velocity=0, time=time*quantization))

    return track





# ---------------------------
# 示例：假设有一个 MIDI 文件，请先修改路径，再运行以下代码进行测试。
if __name__ == '__main__':
    midi_path = r"D:\Documents\AI训练数据集\钢琴\from_musescore\【进击的巨人】红莲的弓矢-钢琴版.mid"  # 替换成你的 MIDI 文件路径

    midi_file=mido.MidiFile(midi_path)

    list_events=midi_to_event(midi_file.tracks[0])
    print(len(list_events))
    new_track=event_to_midi(list_events)
    new_file=mido.MidiFile()
    new_file.tracks.append(new_track)
    new_file.ticks_per_beat=midi_file.ticks_per_beat
    new_file.save(r"D:\Documents\AI训练数据集\钢琴\restruct.mid")
    print(midi_file.tracks[0][:50])
    print(new_track[:20])










