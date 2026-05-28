#!/usr/bin/env python3
"""
合并 LoRA adapter 到基座模型，输出完整模型。

用法:
    python merge_lora.py

输出:
    ./lora_output_merged/  合并后的完整模型（HuggingFace 格式）
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from pathlib import Path

BASE_MODEL_DIR = str(Path(__file__).parent.parent / "models" / "qwen2.5-0.5b-local")
GGUF_FILE = "qwen2.5-0.5b.gguf"
LORA_ADAPTER_PATH = Path(__file__).parent.parent / "lora_output" / "final"
OUTPUT_PATH = Path(__file__).parent.parent / "lora_output_merged"


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main():
    if not LORA_ADAPTER_PATH.exists():
        print(f"[ERROR] LoRA adapter 不存在: {LORA_ADAPTER_PATH}")
        print("请先运行 train_lora.py 完成训练")
        return

    device = get_device()
    print(f"[INFO] 使用设备: {device}")
    print(f"[INFO] 加载本地基座模型: {BASE_MODEL_DIR}")

    torch_dtype = torch.float16 if device in ("cuda", "mps") else torch.float32

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_DIR,
        gguf_file=GGUF_FILE,
        torch_dtype=torch_dtype,
        local_files_only=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(
        BASE_MODEL_DIR,
        local_files_only=True,
    )

    print(f"[INFO] 加载 LoRA adapter: {LORA_ADAPTER_PATH}")
    model = PeftModel.from_pretrained(model, str(LORA_ADAPTER_PATH))

    print("[INFO] 合并 LoRA 权重到基座模型...")
    model = model.merge_and_unload()

    print(f"[INFO] 保存合并模型到: {OUTPUT_PATH}")
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUTPUT_PATH))
    tokenizer.save_pretrained(str(OUTPUT_PATH))

    print("\n[SUCCESS] 合并完成！")
    print(f"  合并模型: {OUTPUT_PATH}")
    print(f"""
[下一步] 转换为 GGUF（给 llama.cpp 使用）:

  # 方法1: 使用 llama.cpp 的 convert_hf_to_gguf.py
  python /path/to/llama.cpp/convert_hf_to_gguf.py \\
    {OUTPUT_PATH} \\
    --outfile {Path(__file__).parent / 'models' / 'qwen2.5-0.5b-lora.gguf'} \\
    --outtype f16

  # 方法2: 如果需要量化
  python /path/to/llama.cpp/convert_hf_to_gguf.py \\
    {OUTPUT_PATH} \\
    --outfile {Path(__file__).parent / 'models' / 'qwen2.5-0.5b-lora-f16.gguf'} \\
    --outtype f16
""")


if __name__ == "__main__":
    main()
