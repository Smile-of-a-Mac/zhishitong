"""
智审通 · 模型下载 / 能力检测工具
被 setup.sh / setup.ps1 调用。

模式:
  --check          检测系统能否本地推理和训练，输出 JSON
  --download       下载模型（必须指定 --models-dir）
  --check-and-download  检测 → 通过则下载
"""
import argparse
import json
import os
import platform
import sys
from pathlib import Path


GGUF_REPO = "Qwen/Qwen3-4B-Instruct-GGUF"
HF_REPO = "Qwen/Qwen3-4B-Instruct"

GGUF_QUANTS = [
    ("qwen3-4b-instruct-q4_k_m.gguf", "Q4_K_M  ~2.5GB  推荐"),
    ("qwen3-4b-instruct-q4_0.gguf",   "Q4_0    ~2.3GB  兼容性最佳"),
    ("qwen3-4b-instruct-q5_k_m.gguf", "Q5_K_M  ~3.0GB  精度更高"),
    ("qwen3-4b-instruct-q8_0.gguf",   "Q8_0    ~4.6GB  精度最高"),
]


_SYSTEM_MEM_GB: float | None = None


def _get_total_ram_gb() -> float:
    """Get total system RAM in GB (no external deps)."""
    global _SYSTEM_MEM_GB
    if _SYSTEM_MEM_GB is not None:
        return _SYSTEM_MEM_GB
    try:
        if sys.platform == "darwin":
            import subprocess
            r = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
            _SYSTEM_MEM_GB = int(r.stdout.strip()) / 1_073_741_824
        elif sys.platform.startswith("linux"):
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        _SYSTEM_MEM_GB = int(line.split()[1]) / 1_048_576
                        break
        elif sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            mem = ctypes.c_longlong()
            kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(mem))
            _SYSTEM_MEM_GB = mem.value / 1_048_576
    except Exception:
        pass
    if _SYSTEM_MEM_GB is None:
        _SYSTEM_MEM_GB = 0.0
    return _SYSTEM_MEM_GB


def _get_free_disk_gb(path: str = ".") -> float:
    """Get free disk space at path in GB."""
    try:
        st = os.statvfs(path) if hasattr(os, "statvfs") else None
        if st:
            return st.f_bavail * st.f_frsize / 1_073_741_824
    except Exception:
        pass
    return 0.0


def _check_arch() -> str:
    """Detect architecture string."""
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        return "arm64"
    elif machine in ("x86_64", "amd64"):
        return "x86_64"
    return machine


def _check_huggingface_reachability() -> str | None:
    """Check if HuggingFace is reachable. Returns error string or None."""
    try:
        import urllib.request
        urllib.request.urlopen("https://huggingface.co", timeout=8)
        return None
    except Exception as e:
        return str(e)[:80]


def check_capability() -> dict:
    """
    System capability checks.
    Returns a dict with all check results.
    """
    ram_gb = _get_total_ram_gb()
    disk_gb = _get_free_disk_gb()
    arch = _check_arch()
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    net_err = _check_huggingface_reachability()
    has_gpu, gpu_label, vram_gb = _get_gpu_info()

    # VRAM thresholds
    MIN_VRAM_INFER = 3.0    # Q4_K_M GGUF GPU offloading
    MIN_VRAM_TRAIN = 6.0    # 4B LoRA on GPU

    # Decision thresholds
    ram_ok_infer = ram_gb >= 4.0
    vram_ok_infer = has_gpu and vram_gb >= MIN_VRAM_INFER
    can_infer = ram_ok_infer  # CPU inference is always a fallback

    ram_ok_train_gpu = ram_gb >= 8.0
    vram_ok_train = has_gpu and vram_gb >= MIN_VRAM_TRAIN
    ram_ok_train_cpu = ram_gb >= 12.0
    can_train = (vram_ok_train and ram_ok_train_gpu) or (not has_gpu and ram_ok_train_cpu) or (has_gpu and ram_ok_train_cpu)

    can_download = ram_ok_infer and disk_gb >= 8.0 and net_err is None

    return {
        "ram_gb": round(ram_gb, 1),
        "free_disk_gb": round(disk_gb, 1),
        "arch": arch,
        "python_version": py_ver,
        "network_reachable": net_err is None,
        "network_error": net_err or "",
        "has_gpu_backend": has_gpu,
        "gpu": gpu_label,
        "vram_gb": round(vram_gb, 1) if vram_gb > 0 else 0,
        "thresholds": {
            "min_ram_infer_gb": 4.0,
            "min_ram_train_gb_gpu": 8.0,
            "min_ram_train_gb_cpu": 12.0,
            "min_vram_infer_gb": MIN_VRAM_INFER,
            "min_vram_train_gb": MIN_VRAM_TRAIN,
            "min_free_disk_gb": 8.0,
        },
        "capable": {
            "inference": can_infer,
            "training": can_train,
            "download_model": can_download,
        },
    }


def _get_gpu_info() -> tuple[bool, str, float]:
    """
    Detect GPU and VRAM.
    Returns: (has_gpu, label, vram_gb)
    VRAM is 0 if not detectable (Apple Silicon returns system RAM).
    """
    if sys.platform == "darwin":
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            ram = _get_total_ram_gb()
            return True, "Apple Silicon (MPS, Unified Memory)", ram
        return False, "", 0.0

    try:
        import subprocess
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            lines = r.stdout.strip().splitlines()
            if lines:
                parts = lines[0].rsplit(", ", 1)
                name = parts[0]
                vram_mb = 0
                if len(parts) > 1:
                    vram_str = parts[1].lower().replace("mib", "").strip()
                    try:
                        vram_mb = float(vram_str)
                    except ValueError:
                        pass
                return True, f"NVIDIA {name}", round(vram_mb / 1024, 1)
    except Exception:
        pass
    return False, "", 0.0


# ---------- Download with progress ----------

def _download_file(url: str, dest: Path, desc: str = "", expected_mb: int = 0) -> None:
    """Download a file with tqdm progress bar showing %, speed, and ETA."""
    import shutil
    import tempfile
    import requests as _requests
    from tqdm import tqdm

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".part", dir=dest.parent)
    tmp_path = Path(tmp.name)

    try:
        headers = {}
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN") or ""
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"

        resp = _requests.get(url, stream=True, headers=headers, timeout=30)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        label = desc or dest.name

        with tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=label,
            leave=True,
            bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}  [{rate_fmt}{postfix}]",
        ) as pbar:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    tmp.write(chunk)
                    pbar.update(len(chunk))
        tmp.close()

        if dest.exists():
            dest.unlink()
        shutil.move(str(tmp_path), str(dest))
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


# ---------- Download functions ----------

def download_gguf(models_dir: Path):
    gguf_dir = models_dir
    gguf_dir.mkdir(parents=True, exist_ok=True)

    print("\n[INFO] 正在查询可下载的量化版本...")
    try:
        from huggingface_hub import list_repo_files
        all_files = list_repo_files(GGUF_REPO)
        gguf_files = [f for f in all_files if f.endswith(".gguf")]
    except Exception as e:
        print(f"[ERROR] 无法查询模型文件列表: {e}")
        sys.exit(1)

    if not gguf_files:
        print("[ERROR] 远程仓库中未找到 GGUF 文件")
        sys.exit(1)

    print(f"  找到 {len(gguf_files)} 个量化版本:")
    for f in sorted(gguf_files):
        print(f"    {f.split('/')[-1]}")

    detected = None
    for good_name, _ in GGUF_QUANTS:
        matches = [f for f in gguf_files if good_name in f]
        if matches:
            detected = matches[0]
            break
    if not detected:
        detected = gguf_files[0]

    dest = gguf_dir / "qwen3-4b.gguf"
    if dest.exists():
        mb = dest.stat().st_size / 1_048_576
        print(f"[✓] GGUF 模型已存在 ({mb:.0f} MB)")
        return

    url = f"https://huggingface.co/{GGUF_REPO}/resolve/main/{detected}"
    print(f"\n[INFO] 开始下载 GGUF 模型 ({detected})...")
    print(f"  目标: {dest}")
    try:
        _download_file(url, dest, desc="Qwen3-4B GGUF (q4_k_m)", expected_mb=2500)
    except Exception as e:
        print(f"[ERROR] 下载失败: {e}")
        print("  请手动下载后放到 models/qwen3-4b.gguf")
        sys.exit(1)

    downloaded = gguf_dir / detected
    if downloaded.exists() and downloaded.name != "qwen3-4b.gguf":
        downloaded.rename(dest)
    print(f"[✓] GGUF 模型下载完成: {dest}")


def download_hf_format(models_dir: Path):
    hf_dir = models_dir / "Qwen3-4B"
    config_file = hf_dir / "config.json"
    tok_file = hf_dir / "tokenizer.json"

    if config_file.exists() and tok_file.exists():
        print(f"[✓] HuggingFace 格式模型文件已存在")
        return

    hf_dir.mkdir(parents=True, exist_ok=True)
    needed = ["config.json", "tokenizer.json", "tokenizer_config.json",
              "vocab.json", "merges.txt", "added_tokens.json",
              "special_tokens_map.json"]

    print(f"\n[INFO] 下载 HuggingFace 格式文件 (tokenizer/config)...")
    for fname in needed:
        dest = hf_dir / fname
        if dest.exists():
            continue
        url = f"https://huggingface.co/{HF_REPO}/resolve/main/{fname}"
        try:
            _download_file(url, dest, desc=f"  {fname}", expected_mb=1)
            print(f"  [✓] {fname}")
        except Exception:
            pass  # optional files may not exist

    if not config_file.exists():
        print("[WARN] config.json 下载失败，创建最小配置...")
        config_file.write_text(json.dumps({
            "_name_or_path": "Qwen/Qwen3-4B-Instruct",
            "architectures": ["Qwen3ForCausalLM"],
            "model_type": "qwen3",
            "hidden_size": 2560,
            "num_attention_heads": 20,
            "num_hidden_layers": 36,
            "vocab_size": 152064,
            "torch_dtype": "bfloat16",
        }))
        print("  [✓] config.json (最小配置)")
    print(f"[✓] HF 格式模型文件就绪")


# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(description="智审通 · 模型工具")
    parser.add_argument("--check", action="store_true", help="检测系统能力并输出 JSON")
    parser.add_argument("--download", action="store_true", help="下载模型")
    parser.add_argument("--check-and-download", action="store_true", help="检测后下载")
    parser.add_argument("--models-dir", default="models", help="模型目录")
    parser.add_argument("--quant", default=None, help="指定量化版本 (默认自动选择)")
    parser.add_argument("--json", action="store_true", help="--check 时输出 JSON")
    args = parser.parse_args()

    if args.check or args.check_and_download:
        cap = check_capability()
        if args.json:
            print(json.dumps(cap, ensure_ascii=False))
            sys.exit(0 if cap["capable"]["inference"] else 1)
        else:
            print()
            print("═══════════════════════════════════════")
            print("  系统能力检测")
            print("═══════════════════════════════════════")
            print(f"  系统架构:      {cap['arch']}")
            print(f"  Python 版本:   {cap['python_version']}")
            print(f"  总内存:        {cap['ram_gb']:.1f} GB")
            print(f"  空闲磁盘:      {cap['free_disk_gb']:.0f} GB")
            print(f"  GPU 后端:      {'有' if cap['has_gpu_backend'] else '无'}"
                  + (f" ({cap['gpu']}, VRAM: {cap['vram_gb']:.0f} GB)" if cap['has_gpu_backend'] and cap['vram_gb'] > 0 else ""))
            print(f"  网络连通:      {'✓' if cap['network_reachable'] else '✗ ' + cap['network_error']}")
            print(f"  ─────────────────────────────────")
            inf_reason = "✓ 可以" if cap['capable']['inference'] else f"✗ 系统 RAM {cap['ram_gb']}GB < 4GB"
            train_reason = "✓ 可以"
            if not cap['capable']['training']:
                if cap['has_gpu_backend'] and cap['vram_gb'] < cap['thresholds']['min_vram_train_gb']:
                    train_reason = f"✗ VRAM {cap['vram_gb']:.0f}GB < {cap['thresholds']['min_vram_train_gb']:.0f}GB"
                elif cap['ram_gb'] < cap['thresholds']['min_ram_train_gb_cpu']:
                    train_reason = f"✗ 系统 RAM {cap['ram_gb']}GB < {cap['thresholds']['min_ram_train_gb_cpu']}GB"
            print(f"  本地推理:      {inf_reason}")
            print(f"  LoRA 训练:     {train_reason}")
            print(f"  模型下载:      {'✓ 可以' if cap['capable']['download_model'] else '✗ 见上'}")
            print()

            if not cap["capable"]["inference"]:
                print("  ⚠ 本机内存不足，无法运行本地推理和 LoRA 训练。")
                print("    推荐使用外部 LLM API (Pro 模式) 或升级硬件。")
                print()

        if args.check_and_download:
            if not cap["capable"]["download_model"]:
                print("[INFO] 跳过模型下载：本机未能满足最低要求")
                sys.exit(0)
            # Fall through to download

    if args.download or args.check_and_download:
        models_dir = Path(args.models_dir).resolve()
        print(f"[INFO] 模型目录: {models_dir}")
        try:
            from huggingface_hub import hf_hub_download, list_repo_files
        except ImportError:
            print("[ERROR] 缺少 huggingface_hub，请先运行: pip install huggingface_hub")
            sys.exit(1)

        download_gguf(models_dir)
        download_hf_format(models_dir)
        print("\n[✓] 模型下载完成！")
        print(f"  GGUF: {models_dir / 'qwen3-4b.gguf'}")
        print(f"  HF:   {models_dir / 'Qwen3-4B' / ''}")


if __name__ == "__main__":
    main()
