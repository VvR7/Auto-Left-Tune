from event_midi import event_to_midi,midi_to_event
import mido
import numpy as np


def build_vocab(max_time=1500,quantization=10):
    '''
    第0个是<bos>第1个是<eos>,2是<pad>
    dict键是元组（type，val），值是对应映射的整数（从0开始）
    list是列表，整数索引对应映射的元组
    max_time可能还需斟酌
    词表大小为410
    '''
    dict={}
    num_list=[]
    dict[("bos",0)]=0
    num_list.append(("bos",0))
    dict[("eos",0)]=1
    num_list.append(("eos",0))
    dict[("pad", 0)] = 2
    num_list.append(("pad", 0))
    id=3
    for i in range(max_time//quantization+1):
        t = ("shift_time",i)
        dict[t] = id
        num_list.append(t)
        id+=1
    for i in range(128):
        t = ("note_on",i)
        dict[t] = id
        num_list.append(t)
        id += 1
    for i in range(128):
        t = ("note_off",i)
        dict[t] = id
        num_list.append(t)
        id += 1
    return dict,num_list

def event_to_num(events,mydict):
    list_num=[]
    for t in events:
        list_num.append(mydict[t])
    return list_num
def num_to_event(list_num,dict_list):
    events=[]
    for num in list_num:
        events.append(dict_list[num])
    return events



my_dict, dict_list = build_vocab()


if __name__ == '__main__':
    midi_path = r"D:\Documents\AI训练数据集\钢琴\from_musescore\打上花火.mid"  # 替换成你的 MIDI 文件路径

    midi_file=mido.MidiFile(midi_path)
    print(f"词表大小为{len(dict_list)}")

    events=midi_to_event(midi_file.tracks[0])
    num_list = event_to_num(events,my_dict)
    events = num_to_event(num_list,dict_list)

    new_track=event_to_midi(events)
    new_file=mido.MidiFile()
    new_file.tracks.append(new_track)
    new_file.ticks_per_beat=midi_file.ticks_per_beat
    new_file.save(r"D:\Documents\AI训练数据集\钢琴\restruct.mid")
    print(midi_file.tracks[0][:50])
    print(new_track[:20])


