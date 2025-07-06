import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import mido
from event_midi import midi_to_event,event_to_midi
from event_num import event_to_num,num_to_event,my_dict,dict_list

class NumpySeq2SeqDataset(Dataset):
    def __init__(self, src_path, tgt_path):
        self.src = np.load(src_path)  # shape: [batch, seq_len]
        self.tgt = np.load(tgt_path)
        assert self.src.shape[0] == self.tgt.shape[0], "Mismatched number of samples"

    def __len__(self):
        return self.src.shape[0]

    def __getitem__(self, idx):
        src_seq = torch.tensor(self.src[idx], dtype=torch.long)
        tgt_seq = torch.tensor(self.tgt[idx], dtype=torch.long)
        return src_seq, tgt_seq

# 定义位置编码模块，用于为序列添加位置信息
class PositionalEncoding(nn.Module):
    def __init__(self, d_model, dropout=0.1, max_len=8000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)
        # 创建 [1, max_len, d_model] 大小的位置编码矩阵
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)  # [max_len, 1]
        # 计算频率因子
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-torch.log(torch.tensor(10000.0)) / d_model))
        # 在偶数和奇数维度填充 sin 和 cos
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # [1, max_len, d_model]
        # 将pe注册为缓冲区(buffer)，在模型保存时一同保存，但不作为可训练参数
        self.register_buffer('pe', pe)

    def forward(self, x):
        # x: [batch_size, seq_len, d_model]
        seq_len = x.size(1)
        # 将位置编码加到输入x上（利用广播机制）
        x = x + self.pe[:, :seq_len, :]
        return self.dropout(x)


# 定义序列到序列 Transformer 模型
class Seq2SeqTransformer(nn.Module):
    def __init__(self, vocab_size, d_model=512, nhead=8, num_encoder_layers=6, num_decoder_layers=6,
                 dim_feedforward=2048, dropout=0.1,max_len=8000):
        super(Seq2SeqTransformer, self).__init__()
        self.d_model = d_model
        # 源和目标嵌入层
        self.src_embedding = nn.Embedding(vocab_size, d_model)
        self.tgt_embedding = nn.Embedding(vocab_size, d_model)
        # 位置编码器
        self.pos_encoder = PositionalEncoding(d_model, dropout=dropout,max_len=max_len)
        # Transformer 编码器和解码器模块
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward,
                                                   dropout=dropout,batch_first=True)
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_encoder_layers)
        decoder_layer = nn.TransformerDecoderLayer(d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward,
                                                   dropout=dropout,batch_first=True)
        self.decoder = nn.TransformerDecoder(decoder_layer, num_layers=num_decoder_layers)
        # 输出线性层将隐藏状态转换为词表概率
        self.output_layer = nn.Linear(d_model, vocab_size)

    def forward(self, src, tgt, src_mask=None, tgt_mask=None, src_padding_mask=None, tgt_padding_mask=None):
        # 嵌入并添加位置编码
        # 注意：假设输入 src 和 tgt 形状为 [batch_size, seq_len]
        src_emb = self.pos_encoder(self.src_embedding(src))  # [batch, src_len, d_model]
        tgt_emb = self.pos_encoder(self.tgt_embedding(tgt))  # [batch, tgt_len, d_model]

        # 编码器生成 memory 表示
        memory = self.encoder(src_emb, src_key_padding_mask=src_padding_mask)
        # 解码器根据 memory 和自身输入生成输出
        outs = self.decoder(tgt_emb, memory, tgt_mask=tgt_mask,
                            memory_key_padding_mask=src_padding_mask,
                            tgt_key_padding_mask=tgt_padding_mask)
        # 解码器输出再转换回 [tgt_len, batch, vocab_size]
        outs = self.output_layer(outs)
        return outs.transpose(0, 1)  # 返回 [batch, tgt_len, vocab_size] 方便后续计算



# 假设已经有 DataLoader 提供 (src, tgt) 张量对


def train(model,num_epochs,dataloader,PAD_ID=2):
    model.train()
    loss_fn = nn.CrossEntropyLoss(ignore_index=PAD_ID)  # 可选：ignore_index 用于忽略 PAD 的损失
    optimizer = optim.Adam(model.parameters(), lr=1e-4)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    for epoch in range(num_epochs):
        total_loss = 0
        for src, tgt in dataloader:
            # 将数据移动到训练设备（如 GPU）
            src = src.to(device)        # [batch, src_len]
            tgt = tgt.to(device)        # [batch, tgt_len]
            # 准备解码器输入和期望输出
            tgt_input = tgt[:, :-1]     # 去掉最后一个EOS作为解码器输入:contentReference[oaicite:12]{index=12}
            target_y = tgt[:, 1:]       # 去掉第一个SOS，得到期望输出序列:contentReference[oaicite:13]{index=13}
            # 生成掩码
            tgt_seq_len = tgt_input.size(1)
            tgt_mask = torch.triu(torch.ones(tgt_seq_len, tgt_seq_len, device=device), diagonal=1).bool().to(device)  # :contentReference[oaicite:14]{index=14}
            # 如果存在PAD填充，生成padding mask
            src_padding_mask = (src == PAD_ID).to(device)   # [batch, src_len]
            tgt_padding_mask = (tgt_input == PAD_ID).to(device)  # [batch, tgt_len]
            # 前向计算得到模型输出 logits
            logits = model(src, tgt_input, tgt_mask=tgt_mask,
                           src_padding_mask=src_padding_mask, tgt_padding_mask=tgt_padding_mask)
            # 计算交叉熵损失（将输出和目标序列展平）:contentReference[oaicite:15]{index=15}
            loss = loss_fn(logits.reshape(-1, logits.size(-1)), target_y.reshape(-1))
            # 反向传播和参数更新
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        avg_loss = total_loss / len(dataloader)
        print(f"Epoch {epoch+1}, Average Loss: {avg_loss:.4f}")


dataset = NumpySeq2SeqDataset(r"autodl-tmp/ndarray/from_musescore_right.npy",
                              r"autodl-tmp/ndarray/from_musescore_left.npy")
dataloader = DataLoader(dataset, batch_size=1, shuffle=True)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = Seq2SeqTransformer(vocab_size=410,max_len=8000).to(device)
train(model,num_epochs=50,dataloader=dataloader,PAD_ID=2)

def greedy_decode(model, src, max_len, bos_id, eos_id):
    model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    src = src.to(device)
    # 禁用梯度计算
    with torch.no_grad():
        # 1. 获得编码器输出的 memory 表示
        memory = model.encoder(model.pos_encoder(model.src_embedding(src)))
        # 准备解码器输入序列（初始化为 BOS）
        batch_size = src.size(0)
        ys = torch.ones(batch_size, 1, dtype=torch.long).fill_(bos_id).to(device)  # [batch, 1]
        for i in range(max_len):
            # 生成当前序列的掩码（大小为当前长度）
            tgt_mask = torch.triu(torch.ones(ys.size(1), ys.size(1), device=device), diagonal=1).bool()
            # 用当前已生成序列通过解码器预测下一个 token:contentReference[oaicite:22]{index=22}
            out = model.decoder(model.pos_encoder(model.tgt_embedding(ys)),
                                 memory, tgt_mask=tgt_mask)
            out = model.output_layer(out)  # [tgt_len, batch, vocab_size]
            # 取最后一个时间步的输出(logits)，选择概率最高的token
            next_token_logits = out[:, -1, :]        # 取解码器输出序列最后一个元素的预测分布
            next_token = next_token_logits.argmax(dim=-1)  # [batch]
            # 将新 token 拼接到已生成序列 `ys` 后
            ys = torch.cat([ys, next_token.unsqueeze(1)], dim=1)
            # 检查是否生成了EOS（对于batch中的每个序列）。这里简单处理为如果批中所有序列都生成EOS则停止。
            if (next_token == eos_id).all():
                break
    # 返回生成的完整序列（包括SOS和EOS）
    return ys

src_file_path = r"autodl-tmp/打上花火右手.mid"
mido_file = mido.MidiFile(src_file_path)
right_events = midi_to_event(mido_file.tracks[0])
right_numlist = event_to_num(right_events,mydict=my_dict)
right_tensor = torch.tensor(right_numlist).unsqueeze(0)
print(right_tensor.shape)


# 使用示例：
# src_example 为准备好的输入序列（batch_size可以是1）张量
generated_left = greedy_decode(model, right_tensor, max_len=8000, bos_id=0, eos_id=1)
print(generated_left.shape)
generated_left = generated_left.reshape(-1)
print(generated_left.shape)
generated_left = generated_left.tolist()
left_events = num_to_event(generated_left,dict_list=dict_list)
left_track = event_to_midi(left_events)
generate_file = mido.MidiFile()
generate_file.ticks_per_beat = mido_file.ticks_per_beat
generate_file.tracks.append(event_to_midi(right_events))
generate_file.tracks.append(left_track)
generate_file.save(r"autodl-tmp/打上花火合奏.mid")



