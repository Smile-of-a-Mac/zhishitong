#!/usr/bin/env python3
"""
LoRA 微调 Qwen3-4B → 山东科技大学事务流程助手

流程: 基座 GGUF → 训练 LoRA adapter → 合并脚本直接导出 GGUF

依赖: torch, transformers, peft, sentencepiece (无 datasets/accelerate)
支持: Apple MPS / CUDA / CPU

用法:
    cd /Users/wangdaoyu/VSCode/sito
    python training/train_lora.py        # 训练 + 自动合并 GGUF

首次运行会用本地 GGUF 文件（约 2.3GB），无需额外下载。
"""

import json
import math
import os
import sys
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model, TaskType
from tqdm import tqdm

# ========================= 配置 =========================

# 本地模型目录（含 config.json + GGUF 文件，无需下载）
BASE_MODEL_DIR = str(Path(__file__).parent.parent / "models" / "Qwen3-4B")
GGUF_FILE = "qwen3-4b.gguf"

CORPUS_PATH = Path(__file__).parent.parent / "data" / "sdust_process_corpus_lora.jsonl"
OUTPUT_DIR = Path(__file__).parent.parent / "lora_output"

# LoRA
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
                 "gate_proj", "up_proj", "down_proj"]

# 训练
NUM_EPOCHS = 10           # 9条数据，10轮足够，再多容易过拟合
BATCH_SIZE = 1
GRAD_ACCUM = 8            # 等效 batch=8
LEARNING_RATE = 1e-4      # 降低 LR 避免在少量数据上过拟合
MAX_SEQ_LENGTH = 1024
WARMUP_STEPS = 10
LOGGING_STEPS = 5
SAVE_STEPS = 50
WEIGHT_DECAY = 0.01
SEED = 42

# 内存优化（4B+ 模型建议开启）
USE_GRADIENT_CHECKPOINTING = True  # 用计算换内存，降低激活值占用

# ========================= 设备 =========================

def get_device():
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


# ========================= 数据集 =========================

class SFTDataset(Dataset):
    """监督微调数据集：将 instruction/input/output 转为 token IDs"""

    def __init__(self, samples: list[dict], tokenizer, max_length: int = 1024):
        self.input_ids = []
        self.labels = []
        self.attention_masks = []

        SYSTEM = "你是山东科技大学事务流程助手，帮助学生和教职工了解办理各项事务的流程、条件和所需材料。"

        for item in samples:
            instruction = item.get("instruction", "")
            inp = item.get("input", "")
            out = item.get("output", "")

            user_content = f"{instruction}\n\n{inp}" if inp.strip() else instruction

            # 使用 tokenizer 的 chat_template 格式化
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": out},
            ]

            try:
                text = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False
                )
            except Exception:
                # fallback: 手写 ChatML
                text = ""
                for msg in messages:
                    text += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"

            # tokenize
            encoded = tokenizer(
                text,
                truncation=True,
                max_length=max_length,
                padding="max_length",
                return_tensors="pt",
            )

            ids = encoded["input_ids"][0]
            mask = encoded["attention_mask"][0]

            # labels 同 input_ids，但将 padding 部分设为 -100（忽略loss）
            labels = ids.clone()
            labels[mask == 0] = -100

            self.input_ids.append(ids)
            self.attention_masks.append(mask)
            self.labels.append(labels)

    def __len__(self):
        return len(self.input_ids)

    def __getitem__(self, idx):
        return {
            "input_ids": self.input_ids[idx],
            "attention_mask": self.attention_masks[idx],
            "labels": self.labels[idx],
        }


# ========================= 训练循环 =========================

def train():
    device = get_device()
    print(f"[设备] {device}")
    print(f"[LoRA] r={LORA_R}, alpha={LORA_ALPHA}")
    print(f"[训练] epochs={NUM_EPOCHS}, batch={BATCH_SIZE}×{GRAD_ACCUM}, lr={LEARNING_RATE}")

    # ---- 加载数据 ----
    if not CORPUS_PATH.exists():
        print(f"[ERROR] 语料不存在: {CORPUS_PATH}")
        print("请先运行: cd data && python build_corpus_local.py")
        sys.exit(1)

    samples = []
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    print(f"[数据] {len(samples)} 条语料")

    # ---- 加载模型 ----
    print(f"[模型] 加载本地模型: {BASE_MODEL_DIR}")
    print(f"[模型] 使用 GGUF: {GGUF_FILE}")

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_DIR, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # GGUF 须先 float32 加载到 CPU，反量化后才能安全移到 MPS
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_DIR,
        gguf_file=GGUF_FILE,
        torch_dtype=torch.float32,
        local_files_only=True,
    )

    # ---- 梯度检查点（用计算换内存）----
    if USE_GRADIENT_CHECKPOINTING:
        model.gradient_checkpointing_enable()
        print("[内存] 梯度检查点已启用")

    # ---- 应用 LoRA（在 CPU 上，再移 MPS）----
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=LORA_TARGETS,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 移到目标设备
    model = model.to(device)
    model.config.use_cache = False
    model.enable_input_require_grads()

    # ---- 数据集 ----
    dataset = SFTDataset(samples, tokenizer, max_length=MAX_SEQ_LENGTH)
    dataloader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        pin_memory=(str(device) == "cuda"),
    )

    total_steps = (len(dataloader) // GRAD_ACCUM) * NUM_EPOCHS
    print(f"[训练] 总步数 ≈ {total_steps}")

    # ---- 优化器 & 调度器 ----
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
    )

    def cosine_schedule(step: int) -> float:
        if step < WARMUP_STEPS:
            return step / max(1, WARMUP_STEPS)
        progress = (step - WARMUP_STEPS) / max(1, total_steps - WARMUP_STEPS)
        return max(0.0, 0.5 * (1.0 + math.cos(math.pi * progress)))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, cosine_schedule)

    # ---- 训练 ----
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    global_step = 0
    best_loss = float("inf")

    print("\n" + "=" * 60)
    print("开始训练")
    print("=" * 60)

    steps_per_epoch = math.ceil(len(dataloader) / GRAD_ACCUM)

    epoch_bar = tqdm(
        range(NUM_EPOCHS),
        desc="Epoch",
        unit="ep",
        position=0,
    )

    for epoch in epoch_bar:
        model.train()
        epoch_loss = 0.0
        accum_loss = 0.0

        batch_bar = tqdm(
            dataloader,
            desc=f"  Step",
            unit="batch",
            leave=False,
            position=1,
        )

        for batch_idx, batch in enumerate(batch_bar):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels,
            )
            loss = outputs.loss / GRAD_ACCUM
            loss.backward()

            accum_loss += loss.item()

            if (batch_idx + 1) % GRAD_ACCUM == 0 or (batch_idx + 1) == len(dataloader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                global_step += 1

                if global_step % LOGGING_STEPS == 0:
                    avg_loss = accum_loss * GRAD_ACCUM / LOGGING_STEPS
                    lr = scheduler.get_last_lr()[0]
                    batch_bar.set_postfix(loss=f"{avg_loss:.4f}", lr=f"{lr:.2e}")
                    epoch_loss += accum_loss * GRAD_ACCUM
                    accum_loss = 0.0

                # 保存检查点
                if global_step % SAVE_STEPS == 0:
                    ckpt = OUTPUT_DIR / f"checkpoint-{global_step}"
                    model.save_pretrained(str(ckpt))
                    tokenizer.save_pretrained(str(ckpt))
                    print(f"\n  [save] {ckpt}")

        # 更新 epoch bar 的 loss
        epoch_bar.set_postfix(loss=f"{epoch_loss / max(1, steps_per_epoch):.4f}")

        avg_epoch_loss = epoch_loss / max(1, len(dataloader) // GRAD_ACCUM)
        print(f"--- epoch {epoch+1}/{NUM_EPOCHS}  avg_loss={avg_epoch_loss:.4f} ---")

        if avg_epoch_loss < best_loss:
            best_loss = avg_epoch_loss

    # ---- 保存最终模型 ----
    final_path = OUTPUT_DIR / "final"
    model.save_pretrained(str(final_path))
    tokenizer.save_pretrained(str(final_path))
    print(f"\n[完成] LoRA adapter 已保存: {final_path}")

    # 打印下一步指令
    print(f"""
{'='*60}
训练完成！自动合并 LoRA → GGUF...
{'='*60}
""")

    # 自动合并
    sys.path.insert(0, str(Path(__file__).parent))
    from merge_lora import merge
    merge(auto_clean=True)


if __name__ == "__main__":
    train()
