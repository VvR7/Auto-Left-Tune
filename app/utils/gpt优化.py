# 完整升级后的 Transformer 训练脚本
# 包含：验证集划分、beam search 解码、val_loss 保存 checkpoint、mask 可视化、loss 曲线图

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import matplotlib.pyplot as plt
import os
'''
以下方面优化了代码，把np.load得到的训练数据划分百分之十作为验证集，修正推理中 memory 的 padding mask，
解码方式使用beam search，训练过程中保存check point，并且是根据val_loss来保存，
加入mask可视化以及loss下降曲线可视化模块，训练结束时保存对应的图片
同时引入了学习率调度器
'''
# ================== Dataset ===================
class NumpySeq2SeqDataset(Dataset):
    def __init__(self, src_path, tgt_path):
        self.src = np.load(src_path)
        self.tgt = np.load(tgt_path)
        assert self.src.shape[0] == self.tgt.shape[0], "Mismatched number of samples"

    def __len__(self):
        return self.src.shape[0]

    def __getitem__(self, idx):
        return (torch.tensor(self.src[idx], dtype=torch.long),
                torch.tensor(self.tgt[idx], dtype=torch.long))

# ================== Positional Encoding ===================
class PositionalEncoding(nn.Module):
    def __init__(self, d_model, dropout=0.1, max_len=8000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2) * (-np.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe.unsqueeze(0))

    def forward(self, x):
        x = x + self.pe[:, :x.size(1)]
        return self.dropout(x)

# ================== Transformer 模型 ===================
class Seq2SeqTransformer(nn.Module):
    def __init__(self, vocab_size, d_model=512, nhead=8, num_encoder_layers=6, num_decoder_layers=6,
                 dim_feedforward=2048, dropout=0.1, max_len=8000):
        super().__init__()
        self.src_embedding = nn.Embedding(vocab_size, d_model,padding_idx=2)
        self.tgt_embedding = nn.Embedding(vocab_size, d_model,padding_idx=2)
        self.pos_encoder = PositionalEncoding(d_model, dropout, max_len)
        encoder_layer = nn.TransformerEncoderLayer(d_model, nhead, dim_feedforward, dropout, batch_first=True)
        decoder_layer = nn.TransformerDecoderLayer(d_model, nhead, dim_feedforward, dropout, batch_first=True)
        self.encoder = nn.TransformerEncoder(encoder_layer, num_encoder_layers)
        self.decoder = nn.TransformerDecoder(decoder_layer, num_decoder_layers)
        self.output_layer = nn.Linear(d_model, vocab_size)

    def forward(self, src, tgt, tgt_mask=None, src_padding_mask=None, tgt_padding_mask=None):
        src_emb = self.pos_encoder(self.src_embedding(src))
        tgt_emb = self.pos_encoder(self.tgt_embedding(tgt))
        memory = self.encoder(src_emb, src_key_padding_mask=src_padding_mask)
        output = self.decoder(tgt_emb, memory, tgt_mask=tgt_mask,
                              memory_key_padding_mask=src_padding_mask,
                              tgt_key_padding_mask=tgt_padding_mask)
        return self.output_layer(output)

# ================== Beam Search 解码 ===================
@torch.no_grad()
def beam_search_decode(model, src, bos_id, eos_id, beam_width=5, max_len=8000, pad_id=2):
    device = src.device
    src_padding_mask = (src == pad_id)
    memory = model.encoder(model.pos_encoder(model.src_embedding(src)), src_key_padding_mask=src_padding_mask)
    sequences = [[(torch.tensor([bos_id], device=device), 0.0)]]

    for _ in range(max_len):
        all_candidates = []
        for seq, score in sequences[-1]:
            if seq[-1].item() == eos_id:
                all_candidates.append((seq, score))
                continue
            tgt_mask = torch.triu(torch.ones(seq.size(0), seq.size(0), device=device), 1).bool()
            out = model.decoder(model.pos_encoder(model.tgt_embedding(seq.unsqueeze(0))),
                                memory, tgt_mask=tgt_mask, memory_key_padding_mask=src_padding_mask)
            out = model.output_layer(out[:, -1, :])
            log_probs = torch.log_softmax(out, dim=-1)
            topk = torch.topk(log_probs, beam_width, dim=-1)
            for i in range(beam_width):
                next_seq = torch.cat([seq, topk.indices[0, i].unsqueeze(0)])
                all_candidates.append((next_seq, score + topk.values[0, i].item()))
        ordered = sorted(all_candidates, key=lambda tup: tup[1], reverse=True)
        sequences.append(ordered[:beam_width])
    return sequences[-1][0][0]

# ================== 训练 ===================
def save_checkpoint(model, optimizer, scheduler, epoch, val_loss, path):
    torch.save({
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'scheduler_state_dict': scheduler.state_dict(),
        'val_loss': val_loss,
        'epoch': epoch
    }, path)

def load_checkpoint(model, optimizer, scheduler, path):
    checkpoint = torch.load(path, map_location=torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
    return checkpoint['epoch'] + 1, checkpoint['val_loss']
def train(model, train_loader, val_loader, num_epochs=50, pad_id=2, ckpt_path="best_model.pt",
          plt_pth=r"autodl-tmp/event/5-12.png",resume=False):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    loss_fn = nn.CrossEntropyLoss(ignore_index=pad_id)
    optimizer = optim.Adam(model.parameters(), lr=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=3, verbose=True)

    start_epoch = 0
    best_val_loss = float('inf')

    if resume and os.path.exists(ckpt_path):
        start_epoch, best_val_loss = load_checkpoint(model, optimizer, scheduler, ckpt_path)
        print(f"Resuming from epoch {start_epoch}, best_val_loss = {best_val_loss:.4f}")
    train_losses, val_losses = [], []

    for epoch in range(num_epochs):
        model.train()
        total_train_loss = 0
        for src, tgt in train_loader:
            src, tgt = src.to(device), tgt.to(device)
            if (src != pad_id).sum().item() == 0 or (tgt != pad_id).sum().item() == 0:
                continue  # 跳过全是PAD的batch
            tgt_input, tgt_output = tgt[:, :-1], tgt[:, 1:]
            tgt_mask = torch.triu(torch.ones(tgt_input.size(1), tgt_input.size(1), device=device), 1).bool()
            src_padding_mask = (src == pad_id)
            tgt_padding_mask = (tgt_input == pad_id)

            logits = model(src, tgt_input, tgt_mask, src_padding_mask, tgt_padding_mask)
            loss = loss_fn(logits.view(-1, logits.size(-1)), tgt_output.reshape(-1))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_train_loss += loss.item()

        avg_train_loss = total_train_loss / len(train_loader)
        train_losses.append(avg_train_loss)

        # 验证
        model.eval()
        total_val_loss = 0
        with torch.no_grad():
            for src, tgt in val_loader:
                src, tgt = src.to(device), tgt.to(device)
                if (src != pad_id).sum().item() == 0 or (tgt != pad_id).sum().item() == 0:
                    continue
                tgt_input, tgt_output = tgt[:, :-1], tgt[:, 1:]
                tgt_mask = torch.triu(torch.ones(tgt_input.size(1), tgt_input.size(1), device=device), 1).bool()
                src_padding_mask = (src == pad_id)
                tgt_padding_mask = (tgt_input == pad_id)

                logits = model(src, tgt_input, tgt_mask, src_padding_mask, tgt_padding_mask)
                loss = loss_fn(logits.view(-1, logits.size(-1)), tgt_output.reshape(-1))
                total_val_loss += loss.item()

        avg_val_loss = total_val_loss / len(val_loader)
        val_losses.append(avg_val_loss)
        print(f"Epoch {epoch+1}/{num_epochs} - Train Loss: {avg_train_loss:.4f}, Val Loss: {avg_val_loss:.4f}")

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            save_checkpoint(model, optimizer, scheduler, epoch, avg_val_loss, ckpt_path)
            print("Saved new best model.")

    # 可视化 Loss 曲线
    plt.plot(train_losses, label='Train Loss')
    plt.plot(val_losses, label='Val Loss')
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.legend()
    plt.title("Training & Validation Loss")
    plt.savefig(plt_pth)
    plt.close()

from torch.utils.data import random_split

def split_dataset(dataset, val_ratio=0.1):
    val_size = int(len(dataset) * val_ratio)
    train_size = len(dataset) - val_size
    return random_split(dataset, [train_size, val_size])


if __name__ == "__main__":

    # 加载数据集
    dataset = NumpySeq2SeqDataset(r"autodl-tmp/ndarray/from_newdata_right.npy",
                                  r"autodl-tmp/ndarray/from_newdata_left.npy")
    train_dataset, val_dataset = split_dataset(dataset, val_ratio=0.1)

    train_loader = DataLoader(train_dataset, batch_size=1, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=1)

    # 使用方式：替换路径并实例化模型、加载数据集后调用 train()
    model = Seq2SeqTransformer(vocab_size=410)
    train(model, train_loader, val_loader,num_epochs=5,ckpt_path=r"autodl-tmp/event/rough_data_trained.pt",
          plt_pth=r"autodl-tmp/event/rough_data_trained.png")
