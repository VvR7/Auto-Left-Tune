# music_transformer_ddp.py
# 支持单机多卡训练的完整 Music Transformer 脚本

import os
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.distributed as dist
import torch.multiprocessing as mp
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import Dataset, DataLoader, random_split, DistributedSampler
import matplotlib.pyplot as plt
from tqdm import tqdm
from torch.cuda.amp import autocast, GradScaler

# ================== Dataset ===================
class NumpySeq2SeqDataset(Dataset):
    def __init__(self, src_path, tgt_path, max_len=8000):
        self.src = np.load(src_path)[:, :max_len]
        self.tgt = np.load(tgt_path)[:, :max_len]
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

# ================== Relative Position Transformer ===================
class RelativePositionalBias(nn.Module):
    def __init__(self, num_heads, max_relative_position=512):
        super().__init__()
        self.num_heads = num_heads
        self.max_relative_position = max_relative_position
        self.relative_attention_bias = nn.Embedding(2 * max_relative_position + 1, num_heads)
        nn.init.normal_(self.relative_attention_bias.weight, std=0.02)

    def forward(self, qlen, klen):
        device = self.relative_attention_bias.weight.device
        context_position = torch.arange(qlen, dtype=torch.long, device=device)[:, None]
        memory_position = torch.arange(klen, dtype=torch.long, device=device)[None, :]
        relative_position = memory_position - context_position
        relative_position = relative_position.clamp(-self.max_relative_position, self.max_relative_position)
        relative_position += self.max_relative_position
        values = self.relative_attention_bias(relative_position)
        return values.permute(2, 0, 1)

class RelPosSelfAttention(nn.Module):
    def __init__(self, d_model, nhead, dropout=0.1, max_relative_position=512):
        super().__init__()
        self.d_model = d_model
        self.nhead = nhead
        self.head_dim = d_model // nhead
        self.scaling = self.head_dim ** -0.5
        self.qkv_proj = nn.Linear(d_model, 3 * d_model)
        self.out_proj = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)
        self.rel_bias = RelativePositionalBias(nhead, max_relative_position)

    def forward(self, x, attn_mask=None, key_padding_mask=None):
        B, L, _ = x.shape
        qkv = self.qkv_proj(x)
        qkv = qkv.reshape(B, L, 3, self.nhead, self.head_dim).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        attn_scores = torch.matmul(q, k.transpose(-2, -1)) * self.scaling
        rel_pos_bias = self.rel_bias(L, L).unsqueeze(0)
        attn_scores += rel_pos_bias
        if attn_mask is not None:
            attn_scores = attn_scores.masked_fill(attn_mask.bool(), float('-inf'))
        if key_padding_mask is not None:
            mask = key_padding_mask.unsqueeze(1).unsqueeze(2)
            attn_scores = attn_scores.masked_fill(mask, float('-inf'))
        attn_weights = torch.softmax(attn_scores, dim=-1)
        attn_output = torch.matmul(self.dropout(attn_weights), v)
        attn_output = attn_output.transpose(1, 2).reshape(B, L, self.d_model)
        return self.out_proj(attn_output)

class RelativeTransformerDecoderLayer(nn.Module):
    def __init__(self, d_model, nhead, dim_feedforward=2048, dropout=0.1, max_relative_position=512):
        super().__init__()
        self.self_attn = RelPosSelfAttention(d_model, nhead, dropout, max_relative_position)
        self.multihead_attn = nn.MultiheadAttention(d_model, nhead, dropout=dropout, batch_first=True)
        self.linear1 = nn.Linear(d_model, dim_feedforward)
        self.linear2 = nn.Linear(dim_feedforward, d_model)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        self.norm3 = nn.LayerNorm(d_model)
        self.dropout1 = nn.Dropout(dropout)
        self.dropout2 = nn.Dropout(dropout)
        self.dropout3 = nn.Dropout(dropout)
        self.activation = nn.ReLU()

    def forward(self, tgt, memory, tgt_mask=None, memory_mask=None,
                tgt_key_padding_mask=None, memory_key_padding_mask=None):
        tgt2 = self.self_attn(tgt, attn_mask=tgt_mask, key_padding_mask=tgt_key_padding_mask)
        tgt = tgt + self.dropout1(tgt2)
        tgt = self.norm1(tgt)
        tgt2, _ = self.multihead_attn(tgt, memory, memory,
                                      attn_mask=memory_mask,
                                      key_padding_mask=memory_key_padding_mask)
        tgt = tgt + self.dropout2(tgt2)
        tgt = self.norm2(tgt)
        tgt2 = self.linear2(self.dropout3(self.activation(self.linear1(tgt))))
        tgt = tgt + tgt2
        tgt = self.norm3(tgt)
        return tgt

class Seq2SeqTransformer(nn.Module):
    def __init__(self, vocab_size, d_model=512, nhead=8, num_encoder_layers=6, num_decoder_layers=6,
                 dim_feedforward=2048, dropout=0.1, max_len=8000, max_relative_position=512):
        super().__init__()
        self.src_embedding = nn.Embedding(vocab_size, d_model, padding_idx=2)
        self.tgt_embedding = nn.Embedding(vocab_size, d_model, padding_idx=2)
        self.src_pos_encoder = PositionalEncoding(d_model, dropout, max_len)
        self.tgt_pos_encoder = PositionalEncoding(d_model, dropout, max_len)
        encoder_layer = nn.TransformerEncoderLayer(d_model, nhead, dim_feedforward, dropout, batch_first=True)
        self.encoder = nn.TransformerEncoder(encoder_layer, num_encoder_layers)
        self.decoder_layers = nn.ModuleList([
            RelativeTransformerDecoderLayer(d_model, nhead, dim_feedforward, dropout, max_relative_position)
            for _ in range(num_decoder_layers)])
        self.output_layer = nn.Linear(d_model, vocab_size)

    def forward(self, src, tgt, tgt_mask=None, src_padding_mask=None, tgt_padding_mask=None):
        src_emb = self.src_pos_encoder(self.src_embedding(src))
        tgt_emb = self.tgt_pos_encoder(self.tgt_embedding(tgt))
        memory = self.encoder(src_emb, src_key_padding_mask=src_padding_mask)
        out = tgt_emb
        for layer in self.decoder_layers:
            out = layer(out, memory, tgt_mask, None, tgt_padding_mask, src_padding_mask)
        return self.output_layer(out)

# ================== DDP 训练 ===================
# music_transformer_ddp.py with AMP support
# 支持单机多卡训练 + 自动混合精度 AMP



# ================== DDP 训练 ===================
def setup_ddp(rank, world_size):
    os.environ['MASTER_ADDR'] = 'localhost'
    os.environ['MASTER_PORT'] = '12355'
    dist.init_process_group("nccl", rank=rank, world_size=world_size)
    torch.cuda.set_device(rank)

def cleanup_ddp():
    dist.destroy_process_group()

def train(model, train_loader, val_loader, num_epochs, pad_id, ckpt_path, plt_pth, resume):
    rank = dist.get_rank()
    device = torch.device(f"cuda:{rank}")
    model.to(device)
    loss_fn = nn.CrossEntropyLoss(ignore_index=pad_id)
    optimizer = optim.Adam(model.parameters(), lr=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=3)
    scaler = GradScaler()
    best_val_loss = float('inf')
    train_losses, val_losses = [], []

    for epoch in range(num_epochs):
        model.train()
        total_train_loss = 0
        data_iter = tqdm(train_loader, desc=f"Epoch {epoch+1}") if rank == 0 else train_loader
        for src, tgt in data_iter:
            src, tgt = src.to(device), tgt.to(device)
            tgt_input, tgt_output = tgt[:, :-1], tgt[:, 1:]
            tgt_mask = torch.triu(torch.ones(tgt_input.size(1), tgt_input.size(1), device=device), 1).bool()
            src_padding_mask = (src == pad_id)
            tgt_padding_mask = (tgt_input == pad_id)

            with autocast():
                logits = model(src, tgt_input, tgt_mask, src_padding_mask, tgt_padding_mask)
                loss = loss_fn(logits.reshape(-1, logits.size(-1)), tgt_output.reshape(-1))

            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            total_train_loss += loss.item()

        avg_train_loss = total_train_loss / len(train_loader)
        train_losses.append(avg_train_loss)

        model.eval()
        total_val_loss = 0
        val_iter = tqdm(val_loader, desc=f"Val {epoch+1}") if rank == 0 else val_loader
        with torch.no_grad():
            for src, tgt in val_iter:
                src, tgt = src.to(device), tgt.to(device)
                tgt_input, tgt_output = tgt[:, :-1], tgt[:, 1:]
                tgt_mask = torch.triu(torch.ones(tgt_input.size(1), tgt_input.size(1), device=device), 1).bool()
                src_padding_mask = (src == pad_id)
                tgt_padding_mask = (tgt_input == pad_id)

                with autocast():
                    logits = model(src, tgt_input, tgt_mask, src_padding_mask, tgt_padding_mask)
                    loss = loss_fn(logits.reshape(-1, logits.size(-1)), tgt_output.reshape(-1))

                total_val_loss += loss.item()

        avg_val_loss = total_val_loss / len(val_loader)
        val_losses.append(avg_val_loss)
        scheduler.step(avg_val_loss)
        if rank == 0:
            print(f"Epoch {epoch+1} - Train: {avg_train_loss:.4f}, Val: {avg_val_loss:.4f}")
            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                torch.save(model.module.state_dict(), ckpt_path)

    if rank == 0:
        plt.plot(train_losses, label="Train")
        plt.plot(val_losses, label="Val")
        plt.legend()
        plt.title("Loss Curve")
        plt.savefig(plt_pth)

# ================== 主程序入口 ===================
def ddp_main(rank, world_size):
    setup_ddp(rank, world_size)
    dataset = NumpySeq2SeqDataset(src_path="5_24_massive_data_right.npy",
                                  tgt_path="5_24_massive_data_left.npy", max_len=4000)
    train_dataset, val_dataset = random_split(dataset, [int(len(dataset) * 0.9), len(dataset) - int(len(dataset) * 0.9)])
    train_sampler = DistributedSampler(train_dataset, num_replicas=world_size, rank=rank)
    val_sampler = DistributedSampler(val_dataset, num_replicas=world_size, rank=rank)
    train_loader = DataLoader(train_dataset, batch_size=2, sampler=train_sampler)
    val_loader = DataLoader(val_dataset, batch_size=2, sampler=val_sampler)
    model = Seq2SeqTransformer(vocab_size=410, max_len=4000).to(rank)
    model = DDP(model, device_ids=[rank])
    train(model, train_loader, val_loader, num_epochs=30, pad_id=2,
          ckpt_path="autodl-tmp/event/ddp_model.pt",
          plt_pth="autodl-tmp/event/ddp_loss.png",
          resume=False)
    cleanup_ddp()

if __name__ == "__main__":
    world_size = torch.cuda.device_count()
    mp.spawn(ddp_main, args=(world_size,), nprocs=world_size, join=True)


