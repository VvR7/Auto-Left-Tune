import torch
import mido
import numpy as np
from gpt优化 import Seq2SeqTransformer, beam_search_decode
from event_midi import midi_to_event, event_to_midi
from event_num import event_to_num, num_to_event, my_dict, dict_list

# ========== 配置 ==========
MODEL_PATH = "autodl-tmp/event/5-12.pt"
RIGHT_HAND_MIDI = "autodl-tmp/打上花火右手.mid"
LEFT_HAND_HINT = "autodl-tmp/打上花火左手部分.mid"  # 左手参考，用于前缀
OUTPUT_MIDI = "autodl-tmp/打上花火_自动接续合奏.mid"

VOCAB_SIZE = 410
BOS_ID = 0
EOS_ID = 1
PAD_ID = 2
MAX_LEN = 8000
BEAM_WIDTH = 5


# ========== 加载模型 ==========
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = Seq2SeqTransformer(vocab_size=VOCAB_SIZE, max_len=MAX_LEN).to(device)
checkpoint = torch.load(MODEL_PATH, map_location=device)
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

# ========== 加载右手 ==========
midi_file = mido.MidiFile(RIGHT_HAND_MIDI)
right_events = midi_to_event(midi_file.tracks[0])
right_tokens = event_to_num(right_events, mydict=my_dict)
src_tensor = torch.tensor(right_tokens, dtype=torch.long).unsqueeze(0).to(device)

# ========== 自动处理左手前缀 ==========
left_midi = mido.MidiFile(LEFT_HAND_HINT)
left_events = midi_to_event(left_midi.tracks[1] if len(left_midi.tracks) > 1 else left_midi.tracks[0])
left_tokens = event_to_num(left_events, mydict=my_dict)

# 构造 decoder 起始序列：BOS + 左手前缀（自动裁剪）
left_prefix = [BOS_ID] + left_tokens
if len(left_prefix) > MAX_LEN:
    print(f"⚠️ 左手前缀过长（{len(left_prefix)}），已自动截断为 {MAX_LEN - 1}")
    left_prefix = left_prefix[:MAX_LEN - 1]
tgt_input = torch.tensor(left_prefix, dtype=torch.long).unsqueeze(0).to(device)

# ========== 生成左手后续 ==========
@torch.no_grad()
def continue_generation(model, src, left_prefix_ids, max_len=8000):
    """
    left_prefix_ids: List[int]，包含 <bos> 和用户左手前缀
    """
    device = src.device
    generated = left_prefix_ids.copy()

    while True:
        if len(generated) >= max_len:
            print(f"⛔ 达到最大长度 MAX_LEN={max_len}，停止生成")
            break

        tgt_input = torch.tensor(generated, dtype=torch.long).unsqueeze(0).to(device)
        tgt_mask = torch.triu(torch.ones(tgt_input.size(1), tgt_input.size(1), device=device), 1).bool()
        src_padding_mask = (src == PAD_ID)
        tgt_padding_mask = (tgt_input == PAD_ID)

        out = model(src, tgt_input, tgt_mask, src_padding_mask, tgt_padding_mask)
        next_token_logits = out[:, -1, :]
        next_token = torch.argmax(next_token_logits, dim=-1).item()

        print(f"[Step {len(generated) - len(left_prefix_ids) + 1}] 预测 token: {next_token} -> {dict_list[next_token]}")

        generated.append(next_token)

        if next_token == EOS_ID:
            print("✅ 模型预测出 <eos>，提前终止")
            break

    return generated

generated_tokens = continue_generation(model, src_tensor, left_prefix, max_len=MAX_LEN)



# ========== 去除特殊符号 ==========
if BOS_ID in generated_tokens:
    generated_tokens.remove(BOS_ID)
if EOS_ID in generated_tokens:
    generated_tokens = generated_tokens[:generated_tokens.index(EOS_ID)]

# ========== 保存为 MIDI ==========
left_events = num_to_event(generated_tokens, dict_list=dict_list)
left_track = event_to_midi(left_events)

print(left_events)
output_midi = mido.MidiFile()
output_midi.ticks_per_beat = midi_file.ticks_per_beat
output_midi.tracks.append(event_to_midi(right_events))  # 原右手
output_midi.tracks.append(left_track)                   # 生成左手
output_midi.save(OUTPUT_MIDI)

print(f"✅ 已完成自动接续生成并保存：{OUTPUT_MIDI}")
