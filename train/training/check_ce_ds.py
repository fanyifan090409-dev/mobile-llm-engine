#!/usr/bin/env python3
"""check_ce_ds.py — 诊断：为什么 chunked CE 的 loss 恰好是原生 CE 的 gas 倍。

背景：换班上线后训练 loss 从 3.2 跳到 25.6（=3.2×8，8 是 grad_accum）。
smoke 阶梯日志给出了精确规律：chunked loss = 原生 loss × gas（gas=32/16/8 三档全中）。
本脚本用真实管线（PackedDataset + 训练用 ds_zero2.json）各跑 2 个优化步：
  A. 原生 CE（Trainer）
  B. 修复前的旧分块 CE（无任何归一化纠正，对照用：应偏 gas 倍）
  C. 现行生产分块 CE（num_items 归一化 + 双卡 across-devices 缩放）
每个 micro-step 打印 compute_loss 的返回值、num_items_in_batch、gas，
训练日志再给出最终上报 loss 与 grad_norm。三者对照即可定位 gas 从哪一步混入。

用法（训练机，必须双卡——单卡看不到跨卡汇总路径，会漏掉
average_tokens_across_devices 的 num_processes 倍差）：
  torchrun --standalone --nproc_per_node=2 check_ce_ds.py [模型目录] [A|B|C]
不带变体参数时依次跑 A/B/C。
"""
import gc
import os
import sys

import torch
from transformers import AutoModelForCausalLM, Trainer, TrainingArguments

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_pt import PackedDataset
from chunked_ce import ChunkedCrossEntropy, ChunkedCETrainer

MODEL = sys.argv[1] if len(sys.argv) > 1 else "models/Qwen3-0.6B"
WHICH = sys.argv[2].upper() if len(sys.argv) > 2 else "ABC"
BIN = "data/pt/fw2.bin"
SEQ, BS, GAS = 2048, 4, 8
MAX_STEPS = 2


class ProbeNative(Trainer):
    """A：原生 CE。compute_loss 前后打印，训练日志给出上报值。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        print(f"[A init] accepts_loss_kwargs={self.model_accepts_loss_kwargs} "
              f"loss_is_scaled_for_ga={self.loss_is_scaled_for_ga}", flush=True)

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        loss = super().compute_loss(model, inputs, return_outputs=return_outputs,
                                    num_items_in_batch=num_items_in_batch)
        print(f"[A micro] return={loss.item():.4f} num_items={num_items_in_batch} "
              f"gas={self.current_gradient_accumulation_steps}", flush=True)
        return loss


class ProbeChunked(ChunkedCETrainer):
    """B：修复前的旧分块 CE——单 micro-batch 均值，无任何归一化纠正。

    对照用途：双卡下 loss 应偏 gas 倍（×8）且 grad_norm 异常，
    证明探针本身能复现 bug（防止「修复后一切正常」是因为探针失效）。
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        print(f"[B init] accepts_loss_kwargs={self.model_accepts_loss_kwargs} "
              f"loss_is_scaled_for_ga={self.loss_is_scaled_for_ga}", flush=True)

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        labels = inputs.pop("labels")
        hidden = model.model(**inputs, return_dict=True).last_hidden_state
        shift_hidden = hidden[..., :-1, :].contiguous()
        shift_labels = labels[..., 1:].contiguous()
        loss = ChunkedCrossEntropy.apply(
            shift_hidden, shift_labels, model.lm_head.weight,
            getattr(model.lm_head, "bias", None), self.ce_chunk_size,
        )
        print(f"[B micro] return={loss.item():.4f} num_items={num_items_in_batch} "
              f"gas={self.current_gradient_accumulation_steps}", flush=True)
        return loss


class ProbeChunkedFixed(ChunkedCETrainer):
    """C：现行生产分块 CE（直接调 super()，永远与生产代码同源）。

    内含两处归一化修复：① loss 按整个累积周期的 num_items_in_batch 归一化
    （旧代码只按单 micro-batch 均值，差 gas 倍）；② 双卡时
    average_tokens_across_devices 使 num_items 跨卡汇总（×num_processes），
    需按原生 compute_loss 的方式乘 loss_scale 抵消（旧代码漏掉 → 差
    1/num_processes 倍）。
    判定：C 的上报 loss 与 grad_norm 与 A（原生）一致即生产代码通过双卡校验。
    """

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        loss = super().compute_loss(model, inputs, return_outputs=return_outputs,
                                    num_items_in_batch=num_items_in_batch)
        print(f"[C micro] return={loss.item():.4f} num_items={num_items_in_batch} "
              f"gas={self.current_gradient_accumulation_steps}", flush=True)
        return loss


def run(cls, tag):
    model = AutoModelForCausalLM.from_pretrained(
        MODEL, dtype=torch.bfloat16, attn_implementation="sdpa")
    model.gradient_checkpointing_enable()
    ds = PackedDataset([BIN], SEQ)
    ta = TrainingArguments(
        output_dir=f"/tmp/probe_{tag}",
        per_device_train_batch_size=BS,
        gradient_accumulation_steps=GAS,
        learning_rate=0.0,          # lr=0：权重不动，前后对比口径干净
        bf16=True,
        logging_steps=1,
        max_steps=MAX_STEPS,
        save_strategy="no",
        deepspeed="scripts/ds_zero2.json",
        report_to=[],
        disable_tqdm=True,
        seed=20261024,
    )
    print(f"===== 运行 {tag} =====", flush=True)
    tr = cls(model=model, args=ta, train_dataset=ds)
    tr.train()
    del tr, model
    gc.collect()
    torch.cuda.empty_cache()


if __name__ == "__main__":
    variants = {"A": (ProbeNative, "native"), "B": (ProbeChunked, "chunked"),
                "C": (ProbeChunkedFixed, "chunked_fixed")}
    for k in WHICH:
        cls, tag = variants[k]
        run(cls, tag)
