import torch
import mido
import numpy as np
from music_transformer import Seq2SeqTransformer
from event_midi import midi_to_event, event_to_midi
from event_num import event_to_num, num_to_event, my_dict, dict_list

# ========== 配置 ==========
MODEL_PATH =  r"autodl-tmp/event/music_trans_5_20.pt"
INPUT_MIDI = "autodl-tmp/打上花火右手.mid"
OUTPUT_MIDI = "autodl-tmp/打上花火合奏_beam.mid"
VOCAB_SIZE = 410
BOS_ID = 0
EOS_ID = 1
PAD_ID = 2
MAX_LEN = 4000
BEAM_WIDTH = 5

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ========== Beam Search 解码 ==========
@torch.no_grad()
def beam_search_generate(model, src, bos_id, eos_id, pad_id, max_len=8000, beam_width=5):
    model.eval()
    memory = model.encoder(model.src_pos_encoder(model.src_embedding(src)))
    sequences = [[[], 0.0, torch.tensor([[bos_id]], device=src.device)]]  # [tokens, score, ys]

    for _ in range(max_len):
        all_candidates = []
        for seq, score, ys in sequences:
            tgt_emb = model.tgt_pos_encoder(model.tgt_embedding(ys))
            out = tgt_emb
            for layer in model.decoder_layers:
                out = layer(out, memory, tgt_mask=None, memory_mask=None,
                            tgt_key_padding_mask=(ys == pad_id), memory_key_padding_mask=(src == pad_id))
            logits = model.output_layer(out[:, -1])
            log_probs = torch.log_softmax(logits, dim=-1).squeeze(0)

            topk_log_probs, topk_tokens = torch.topk(log_probs, beam_width)

            for log_prob, token in zip(topk_log_probs, topk_tokens):
                token_id = token.item()
                new_seq = seq + [token_id]
                new_score = score + log_prob.item()
                new_ys = torch.cat([ys, token.view(1, 1)], dim=1)
                all_candidates.append([new_seq, new_score, new_ys])

        # 选 top beam_width 个得分最高的序列
        sequences = sorted(all_candidates, key=lambda x: x[1], reverse=True)[:beam_width]

        # 如果 beam 内所有序列都以 EOS 结尾，可以提前结束
        if all((len(seq) > 0 and seq[-1] == eos_id) for seq, _, _ in sequences):
            break

    best_seq = sequences[0][0]
    if eos_id in best_seq:
        best_seq = best_seq[:best_seq.index(eos_id)]
    return best_seq

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
generated_tokens = beam_search_generate(model, src_tensor, bos_id=BOS_ID, eos_id=EOS_ID,
                                        pad_id=PAD_ID, max_len=MAX_LEN, beam_width=BEAM_WIDTH)

# ========== 4. 转换为 MIDI ==========
left_events = num_to_event(generated_tokens, dict_list=dict_list)
left_track = event_to_midi(left_events)

# ========== 5. 合并并保存 ==========
output_midi = mido.MidiFile()
output_midi.ticks_per_beat = midi_file.ticks_per_beat
output_midi.tracks.append(event_to_midi(right_events))  # 右手
output_midi.tracks.append(left_track)                   # 左手
output_midi.save(OUTPUT_MIDI)

print(f"✅ Beam Search 生成完成：{OUTPUT_MIDI}")
