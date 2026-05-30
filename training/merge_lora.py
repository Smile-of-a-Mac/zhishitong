#!/usr/bin/env python3
"""
合并 LoRA adapter 到基座模型，直接输出 GGUF 文件。

流程: 基座 GGUF + LoRA adapter → 合并 → 直接导出为 GGUF
无需额外执行 convert_hf_to_gguf.py。

用法:
    python training/merge_lora.py

输出:
    ./models/qwen3-4b-lora.gguf  合并后的完整 GGUF 模型
    ./lora_output_merged/         中间 HF 格式（自动清理）
"""

import shutil
import subprocess
import sys
import torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# ========================= 配置 =========================

# 本地模型目录（含 config.json + GGUF 文件）
BASE_MODEL_DIR = str(Path(__file__).parent.parent / "models" / "Qwen3-4B")
GGUF_FILE = "qwen3-4b.gguf"

LORA_ADAPTER_PATH = Path(__file__).parent.parent / "lora_output" / "final"
HF_MERGE_DIR = Path(__file__).parent.parent / "lora_output_merged"     # 中间 HF 格式
OUTPUT_GGUF = Path(__file__).parent.parent / "models" / "qwen3-4b-lora.gguf"  # 最终 GGUF

# llama.cpp 转换脚本（Homebrew 安装路径）
CONVERT_SCRIPT = "/tmp/convert_hf_to_gguf_fixed.py"
CONVERT_SCRIPT_FALLBACK = "/opt/homebrew/bin/convert_hf_to_gguf.py"


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _find_convert_script() -> Path:
    """查找可用的 convert_hf_to_gguf.py"""
    for p in [Path(CONVERT_SCRIPT), Path(CONVERT_SCRIPT_FALLBACK),
              Path("/opt/homebrew/Cellar/llama.cpp/5450/bin/convert_hf_to_gguf.py")]:
        if p.exists():
            return p
    print("[ERROR] 未找到 convert_hf_to_gguf.py")
    print("  请安装 llama.cpp: brew install llama.cpp")
    sys.exit(1)


def merge(auto_clean: bool = False) -> bool:
    """合并 LoRA 到 GGUF，auto_clean=True 时不询问直接清理 HF 中间文件。"""
    if not LORA_ADAPTER_PATH.exists():
        print(f"[ERROR] LoRA adapter 不存在: {LORA_ADAPTER_PATH}")
        print("请先运行 training/train_lora.py 完成训练")
        return False

    convert_script = _find_convert_script()
    device = get_device()

    print(f"[INFO] 使用设备: {device}")
    print(f"[INFO] 基座模型: {BASE_MODEL_DIR}/{GGUF_FILE}")
    print(f"[INFO] LoRA:     {LORA_ADAPTER_PATH}")
    print(f"[INFO] 输出:     {OUTPUT_GGUF}")
    print()

    # ---- 1. 加载并合并 ----
    torch_dtype = torch.float16 if device in ("cuda", "mps") else torch.float32

    print("[1/3] 加载基座模型...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_DIR,
        gguf_file=GGUF_FILE,
        torch_dtype=torch_dtype,
        local_files_only=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_DIR, local_files_only=True)

    print("[2/3] 加载 LoRA 并合并...")
    model = PeftModel.from_pretrained(model, str(LORA_ADAPTER_PATH))
    model = model.merge_and_unload()

    # ---- 2. 暂存 HF 格式 ----
    HF_MERGE_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(HF_MERGE_DIR), safe_serialization=True)
    tokenizer.save_pretrained(str(HF_MERGE_DIR))
    hf_size = sum(f.stat().st_size for f in HF_MERGE_DIR.rglob("*") if f.is_file())
    print(f"  HF 临时模型: {HF_MERGE_DIR} ({hf_size / 1024**3:.1f}GB)")

    # ---- 3. 转换为 GGUF ----
    print(f"[3/3] 转换为 GGUF -> {OUTPUT_GGUF}")
    cmd = [
        sys.executable, str(convert_script),
        str(HF_MERGE_DIR),
        "--outfile", str(OUTPUT_GGUF),
        "--outtype", "f16",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] GGUF 转换失败:\n{result.stderr}")
        print(f"  HF 中间文件保留在: {HF_MERGE_DIR}")
        return False

    for line in result.stdout.strip().split("\n")[-3:]:
        print(f"  {line}")

    gguf_size = OUTPUT_GGUF.stat().st_size
    print(f"\n[SUCCESS] 合并完成！")
    print(f"  输出:    {OUTPUT_GGUF} ({gguf_size / 1024**3:.1f}GB)")
    print(f"  HF 缓存: {HF_MERGE_DIR} ({hf_size / 1024**3:.1f}GB)")

    # ---- 4. 清理 HF 中间文件 ----
    if auto_clean:
        shutil.rmtree(HF_MERGE_DIR, ignore_errors=True)
        print("  HF 中间文件已自动清理")
    else:
        keep_hf = input("\n是否保留 HF 中间文件？[y/N]: ").strip().lower()
        if keep_hf != "y":
            shutil.rmtree(HF_MERGE_DIR, ignore_errors=True)
            print("  HF 中间文件已清理")
        else:
            print(f"  HF 中间文件保留在: {HF_MERGE_DIR}")

    print(f"\n模型就绪！推理服务将自动检测: {OUTPUT_GGUF}")
    return True


def main():
    merge(auto_clean=False)


if __name__ == "__main__":
    main()
