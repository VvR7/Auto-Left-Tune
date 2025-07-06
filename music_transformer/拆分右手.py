import mido
import numpy as np
# 读取 MIDI 文件
midi_pth = r"D:\Documents\AI训练数据集\钢琴\分风格\135律动和弦\[Free-scores.com]_fiona-mcl-exercise-number-1-20960.mid"
new_pth = r"D:\Documents\AI训练数据集\钢琴\explore\右手[Free-scores.com]_anonymous-canaries-144954.mid"
midi_file = mido.MidiFile(midi_pth)
new_midi = mido.MidiFile()
right_track = midi_file.tracks[0]
new_midi.tracks.append(right_track)
new_midi.save(new_pth)

print(f"saved{new_pth}")