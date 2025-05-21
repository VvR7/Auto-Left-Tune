import torch
import mido
import numpy as np
from gpt优化 import Seq2SeqTransformer, beam_search_decode
from event_midi import midi_to_event, event_to_midi
from event_num import event_to_num, num_to_event, my_dict, dict_list

# ========== 配置 ==========
MODEL_PATH = "autodl-tmp/event/5-12.pt"   # 训练好的checkpoint
INPUT_MIDI = "autodl-tmp/打上花火右手.mid"              # 右手MIDI输入文件
OUTPUT_MIDI = "autodl-tmp/打上花火合奏.mid"             # 输出文件路径
VOCAB_SIZE = 410
BOS_ID = 0
EOS_ID = 1
PAD_ID = 2
MAX_LEN = 8000
BEAM_WIDTH = 5

# ========== 1. 加载模型 ==========
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = Seq2SeqTransformer(vocab_size=VOCAB_SIZE).to(device)
checkpoint = torch.load(MODEL_PATH, map_location=device)
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

# ========== 2. 加载右手 MIDI 并转 token ==========
midi_file = mido.MidiFile(INPUT_MIDI)
right_events = midi_to_event(midi_file.tracks[0])
right_tokens = event_to_num(right_events, mydict=my_dict)
src_tensor = torch.tensor(right_tokens, dtype=torch.long).unsqueeze(0).to(device)  # [1, seq_len]

# ========== 3. 解码生成左手 token ==========
generated = beam_search_decode(model, src_tensor, bos_id=BOS_ID, eos_id=EOS_ID,
                               beam_width=BEAM_WIDTH, max_len=MAX_LEN, pad_id=PAD_ID)
generated = generated.tolist()

# 去除BOS与EOS
if BOS_ID in generated: generated.remove(BOS_ID)
if EOS_ID in generated:
    idx = generated.index(EOS_ID)
    generated = generated[:idx]

# ========== 4. 转换为 MIDI ==========
left_events = num_to_event(generated, dict_list=dict_list)
left_track = event_to_midi(left_events)

# 合并左右手轨道
output_midi = mido.MidiFile()
output_midi.ticks_per_beat = midi_file.ticks_per_beat
output_midi.tracks.append(event_to_midi(right_events))  # 保留原右手
output_midi.tracks.append(left_track)
output_midi.save(OUTPUT_MIDI)

print(f"✅ 生成完成：{OUTPUT_MIDI}")
