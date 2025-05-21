import torch
import mido
from music_transformer import Seq2SeqTransformer
from event_midi import midi_to_event, event_to_midi
from event_num import event_to_num, num_to_event, my_dict, dict_list

# ========== 配置 ==========
MODEL_PATH = r"autodl-tmp/event/music_trans_5_20.pt"
INPUT_MIDI = "autodl-tmp/打上花火右手.mid"
OUTPUT_MIDI = "autodl-tmp/打上花火合奏_sample.mid"
VOCAB_SIZE = 410
BOS_ID = 0
EOS_ID = 1
PAD_ID = 2
MAX_LEN = 4000
TEMPERATURE = 0.9

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ========== Softmax Temperature Sampling ==========
def temperature_sample(logits, temperature=1.0):
    logits = logits / temperature
    probs = torch.softmax(logits, dim=-1)
    token = torch.multinomial(probs, num_samples=1)
    return token.item()

# ========== 逐 token 采样生成 ==========
@torch.no_grad()
def sample_generate(model, src, bos_id, eos_id, pad_id, max_len=8000, temperature=1.0):
    model.eval()
    memory = model.encoder(model.src_pos_encoder(model.src_embedding(src)))
    ys = torch.tensor([[bos_id]], dtype=torch.long).to(src.device)
    generated = []

    for _ in range(max_len):
        tgt_emb = model.tgt_pos_encoder(model.tgt_embedding(ys))
        out = tgt_emb
        for layer in model.decoder_layers:
            out = layer(out, memory, tgt_mask=None, memory_mask=None,
                        tgt_key_padding_mask=(ys == pad_id), memory_key_padding_mask=(src == pad_id))
        logits = model.output_layer(out[:, -1])  # 最后一个位置的预测
        next_token = temperature_sample(logits.squeeze(0), temperature=temperature)

        ys = torch.cat([ys, torch.tensor([[next_token]], device=src.device)], dim=1)
        if next_token == eos_id:
            break
        generated.append(next_token)

    return generated

# ========== 1. 加载模型 ==========
model = Seq2SeqTransformer(vocab_size=VOCAB_SIZE, max_len=MAX_LEN).to(device)
checkpoint = torch.load(MODEL_PATH, map_location=device)
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()

# ========== 2. 加载右手 MIDI ==========
midi_file = mido.MidiFile(INPUT_MIDI)
right_events = midi_to_event(midi_file.tracks[0])
right_tokens = event_to_num(right_events, mydict=my_dict)[:MAX_LEN]
src_tensor = torch.tensor(right_tokens, dtype=torch.long).unsqueeze(0).to(device)

# ========== 3. 生成左手 ==========
generated_tokens = sample_generate(model, src_tensor, bos_id=BOS_ID, eos_id=EOS_ID,
                                   pad_id=PAD_ID, max_len=MAX_LEN, temperature=TEMPERATURE)

# ========== 4. 转换为 MIDI ==========
left_events = num_to_event(generated_tokens, dict_list=dict_list)
left_track = event_to_midi(left_events)

# ========== 5. 合并并保存 ==========
output_midi = mido.MidiFile()
output_midi.ticks_per_beat = midi_file.ticks_per_beat
output_midi.tracks.append(event_to_midi(right_events))  # 右手
output_midi.tracks.append(left_track)                   # 左手
output_midi.save(OUTPUT_MIDI)

print(f"✅ 采样生成完成：{OUTPUT_MIDI}")
