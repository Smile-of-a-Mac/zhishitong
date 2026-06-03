#!/usr/bin/env python3
"""
MLX LoRA 微调 Qwen3-14B → 山东科技大学事务分类助手

用法:
    cd /Users/wangdaoyu/VSCode/sito
    python training/train_lora_mlx.py
"""

import contextlib, json, os, random, shutil, subprocess, sys, time
from pathlib import Path

import mlx.core as mx
import mlx.optimizers as optim
from mlx_lm import load
from mlx_lm.tuner.callbacks import TrainingCallback
from mlx_lm.tuner import train, TrainingArgs, linear_to_lora_layers
from mlx_lm.tuner.utils import print_trainable_parameters
from tqdm import tqdm

BASE_MODEL_DIR = str(Path(__file__).parent.parent / "models" / "Qwen3-14B")
CORPUS_PATH = Path(__file__).parent.parent / "data" / "sdust_multitask_lora.jsonl"
OUTPUT_DIR = Path(__file__).parent.parent / "lora_output_mlx"
GGUF_OUTPUT = Path(__file__).parent.parent / "models" / "qwen3-14b-lora.gguf"
DATA_DIR = Path(__file__).parent.parent / "data" / "mlx_train"

LORA_R = 8
LORA_ALPHA = 16
LORA_NUM_LAYERS = 16
LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj"]

NUM_EPOCHS = 5
BATCH_SIZE = 1
LEARNING_RATE = 1e-4
MAX_SEQ_LENGTH = 1024
WARMUP = 20
VAL_SPLIT = 0.1
SYSTEM = "你是校园事务表单助手。请根据用户的自然语言描述识别事务类型，并以 JSON 格式提取预填字段。输出纯 JSON，不加解释。"


def find_convert_script() -> Path | None:
    repo_root = Path(__file__).parent.parent
    pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        repo_root / ".venv" / "lib" / pyver / "site-packages" / "bin" / "convert_hf_to_gguf.py",
        Path("/opt/homebrew/opt/llama.cpp/bin/convert_hf_to_gguf.py"),
        Path("/usr/local/opt/llama.cpp/bin/convert_hf_to_gguf.py"),
    ]

    found_in_path = shutil.which("convert_hf_to_gguf.py")
    if found_in_path:
        candidates.append(Path(found_in_path))

    try:
        brew = subprocess.run(
            ["brew", "--prefix", "llama.cpp"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if brew.returncode == 0 and brew.stdout.strip():
            candidates.append(Path(brew.stdout.strip()) / "bin" / "convert_hf_to_gguf.py")
    except Exception:
        pass

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def write_adapter_config():
    config = {
        "fine_tune_type": "lora",
        "num_layers": LORA_NUM_LAYERS,
        "lora_parameters": {
            "keys": LORA_TARGETS,
            "rank": LORA_R,
            "scale": LORA_ALPHA,
            "dropout": 0.05,
        },
    }
    with open(OUTPUT_DIR / "adapter_config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


class TqdmTrainingCallback(TrainingCallback):
    def __init__(self, total_iters: int):
        self.pbar = tqdm(total=total_iters, desc="训练", unit="it", dynamic_ncols=True)
        self.last_iteration = 0
        self.val_loss = None

    def on_train_loss_report(self, train_info: dict):
        iteration = train_info["iteration"]
        self.pbar.update(iteration - self.last_iteration)
        self.last_iteration = iteration

        postfix = {
            "loss": f"{train_info['train_loss']:.3f}",
            "lr": f"{train_info['learning_rate']:.1e}",
            "it/s": f"{train_info['iterations_per_second']:.2f}",
            "mem": f"{train_info['peak_memory']:.1f}GB",
        }
        if self.val_loss is not None:
            postfix["val"] = f"{self.val_loss:.3f}"
        self.pbar.set_postfix(postfix)

    def on_val_loss_report(self, val_info: dict):
        self.val_loss = val_info["val_loss"]
        self.pbar.set_postfix({"val": f"{self.val_loss:.3f}"})

    def close(self):
        self.pbar.close()


def prepare_data():
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        samples = [json.loads(line) for line in f if line.strip()]

    random.shuffle(samples)
    split = int(len(samples) * (1 - VAL_SPLIT))
    train_raw, valid_raw = samples[:split], samples[split:]
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for name, raw in [("train", train_raw), ("valid", valid_raw)]:
        with open(DATA_DIR / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for item in raw:
                user_text = item["input"]
                output_json = item["output"]
                text = (
                    f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
                    f"<|im_start|>user\n{user_text}<|im_end|>\n"
                    f"<|im_start|>assistant\n{output_json}<|im_end|>"
                )
                f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")

    print(f"[数据] 训练: {len(train_raw)} 条, 验证: {len(valid_raw)} 条")


def main():
    print("=" * 60)
    print("MLX LoRA 微调 - 事务分类")
    print("=" * 60)

    prepare_data()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def count_jsonl(p: Path) -> int:
        return sum(1 for l in open(p) if l.strip())

    total_samples = count_jsonl(DATA_DIR / "train.jsonl")
    total_iters = total_samples * NUM_EPOCHS

    print(f"[模型] 加载: {BASE_MODEL_DIR}")
    t0 = time.time()
    model, tokenizer = load(BASE_MODEL_DIR)
    print(f"  耗时: {time.time()-t0:.1f}s")

    linear_to_lora_layers(
        model, LORA_NUM_LAYERS,
        {"keys": LORA_TARGETS, "rank": LORA_R, "scale": LORA_ALPHA, "dropout": 0.05},
    )
    print_trainable_parameters(model)

    optimizer = optim.AdamW(learning_rate=LEARNING_RATE)

    def load_tokenized(path):
        tokens_list = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    tokens = tokenizer.encode(item["text"])
                    if tokens[-1] != tokenizer.eos_token_id:
                        tokens.append(tokenizer.eos_token_id)
                    tokens_list.append((mx.array(tokens, dtype=mx.int32), 0))
        return tokens_list

    train_tokens = load_tokenized(DATA_DIR / "train.jsonl")
    valid_tokens = load_tokenized(DATA_DIR / "valid.jsonl")

    train_args = TrainingArgs(
        batch_size=BATCH_SIZE,
        iters=total_iters,
        val_batches=len(valid_tokens),
        steps_per_report=1,
        steps_per_eval=total_iters // 2,
        steps_per_save=total_iters,
        max_seq_length=MAX_SEQ_LENGTH,
        adapter_file=str(OUTPUT_DIR / "adapters.safetensors"),
        grad_checkpoint=False,
        grad_accumulation_steps=1,
    )

    print(f"\n训练: {total_iters} iters, {len(train_tokens)} 样本, {len(valid_tokens)} 验证")
    progress = TqdmTrainingCallback(total_iters)
    try:
        with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
            train(
                model=model,
                optimizer=optimizer,
                train_dataset=train_tokens,
                val_dataset=valid_tokens,
                args=train_args,
                training_callback=progress,
            )
    finally:
        progress.close()

    print(f"\n融合 LoRA → GGUF ...")
    write_adapter_config()
    merged_dir = OUTPUT_DIR / "merged_f16"
    fuse_result = subprocess.run(
        [
            sys.executable, "-m", "mlx_lm", "fuse",
            "--model", BASE_MODEL_DIR,
            "--adapter-path", str(OUTPUT_DIR),
            "--save-path", str(merged_dir),
            "--dequantize",
        ],
        capture_output=True,
        text=True,
    )
    if fuse_result.returncode != 0:
        print(f"  融合失败:\n{fuse_result.stderr[-2000:]}")
        return

    convert_script = find_convert_script()
    if convert_script:
        print(f"  转换脚本: {convert_script}")
        result = subprocess.run(
            [sys.executable, str(convert_script), str(merged_dir),
             "--outfile", str(GGUF_OUTPUT), "--outtype", "f16"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            size = GGUF_OUTPUT.stat().st_size
            print(f"  GGUF: {GGUF_OUTPUT} ({size/1024**3:.1f}GB)")
        else:
            print(f"  转换失败:\n{result.stderr[-2000:]}")
    else:
        print("  未找到 convert_hf_to_gguf.py。请安装 llama.cpp 或确认 .venv 中包含 gguf 转换脚本。")

    print("\n完成!")


if __name__ == "__main__":
    main()
