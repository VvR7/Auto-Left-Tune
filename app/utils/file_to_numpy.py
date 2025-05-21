import os

import mido
import numpy as np
from event_midi import midi_to_event,event_to_midi
from event_num import event_to_num,num_to_event,build_vocab

my_dict, dict_list = build_vocab(max_time=1500,quantization=10)
'''
max_time还需斟酌
'''

def file_to_ndarray(file_path):
    '''
    转换成维度为（seq_len）的ndarray
    返回左手&右手 的ndarray
    '''
    midi_file = mido.MidiFile(file_path)
    if len(midi_file.tracks)<2:
        print(f"{midi_file}的track小于2")
        return np.array([]),np.array([])

    right_num = event_to_num(midi_to_event(midi_file.tracks[0]),my_dict)
    right_ndarray = np.array(right_num)
    left_num = event_to_num(midi_to_event(midi_file.tracks[1]), my_dict)
    left_ndarray = np.array(left_num)

    return right_ndarray,left_ndarray

def pad_or_truncate(array, max_len=8000, pad_value=2):
    if len(array) > max_len:
        print("超过最大序列长度，已截断")
        return array[:max_len],len(array)#这里返回一下最大长度用于统计
    elif len(array) < max_len:
        return np.pad(array, (0, max_len - len(array)), constant_values=pad_value),0
    return array,0

def folder_to_np(folder_path, output_file):
    midi_files = []
    # 遍历文件夹中的所有文件
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.mid', '.midi')):
                midi_files.append(os.path.join(root, file))

    right_np = []
    left_np = []
    # 处理每个 MIDI 文件
    total_np=0
    total_truncated=0
    max_seq_len=0
    '''统计被截断的数量'''
    for midi_file in midi_files:

        right_ndarray, left_ndarray =file_to_ndarray(midi_file)
        right_ndarray,seq_len = pad_or_truncate(right_ndarray)
        left_ndarray,seq_len = pad_or_truncate(left_ndarray)
        total_np+=1
        if(seq_len>0):
            total_truncated+=1
            max_seq_len=max(seq_len,max_seq_len)

        right_np.append(right_ndarray)
        left_np.append(left_ndarray)
        '''
        except Exception as e:
            print(f"处理文件 {midi_file} 时出错: {e}")
        '''

    base_name, extension = os.path.splitext(output_file)
    right_output_file = base_name + "_right" + extension
    left_output_file = base_name + "_left" + extension
    right_np = np.stack(right_np)
    left_np = np.stack(left_np)
    np.save(right_output_file,right_np)
    np.save(left_output_file,left_np)
    print(f"处理后的数据已保存到 {output_file}")
    print(f"总共处理{total_np}个数据，其中{total_truncated}被截断，最大序列长度为{max_seq_len}")
    print(right_np.shape)
    print(left_np.shape)





if __name__ == "__main__":
    folder_path = r"D:\Documents\AI训练数据集\钢琴\from_musescore"  # 替换为实际的文件夹路径
    output_file = r"D:\Documents\AI训练数据集\钢琴\ndarray\from_musescore"  # 替换为实际的输出文件名
    folder_to_np(folder_path, output_file)
