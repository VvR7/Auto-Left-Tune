import mido
import numpy as np
# 读取 MIDI 文件

'''0表示右手，1表示左手，依据note的平均值判断'''
def judge_hand_bynote(track):
    average_note=0
    iter=0
    is_left=False
    for msg in track:
        if msg.type in ['note_on','note_off']:
            iter+=1
            average_note+=msg.note-64
    if average_note<0:
        is_left=True
    return average_note,is_left

def show_tracknum(file,show_hand=False):
    if show_hand==False:
        return len(file.tracks)
    else:
        for i,track in enumerate(file.tracks):
            average_note,is_left=judge_hand_bynote(track)

            if average_note==0:
                print(f"第{i}个track是无音符")
            elif is_left:
                print(f"第{i}个track是左手")
            else:
                print(f"第{i}个track是右手")
        return len(track)

if __name__ == '__main__':
    path = r"D:\Documents\AI训练数据集\钢琴\分风格\古典欢快\[Free-scores.com]_joplin-scott-the-entertainer.midi"
    midi_file = mido.MidiFile(path)  # 替换成你的 MIDI 文件路径
    show_tracknum(midi_file,show_hand=True)







