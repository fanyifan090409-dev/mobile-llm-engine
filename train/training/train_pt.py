#!/usr/bin/env python3
"""续训（继续预训练）：packed token bins → 因果 LM。双卡 torchrun + DeepSpeed + MLflow。

用法：
  torchrun --nproc_per_node=2 scripts/train_pt.py --model models/Qwen3-0.6B \
    --data data/pt/fw2.bin,data/pt/belle.bin --seq-len 4096 \
    --out checkpoints/qwen3-0.6b-pt-20261024 --deepspeed scripts/ds_zero2.json \
    --epochs 1 --per-device-bs 16 --grad-accum 8 --save-steps 2000 --logging-steps 10
"""
import argparse
import math
import os
import shutil

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import AutoModelForCausalLM, Trainer, TrainingArguments, set_seed

from chunked_ce import ChunkedCETrainer


class WSDTrainer(ChunkedCETrainer):
    """WSD 调度（MiniCPM, COLM 2024）：warmup → 长稳定期（峰值 lr 恒定）→ 末段线性衰减。

    为什么不用 cosine：cosine 从第一步就开始衰减 lr，末段 lr≈0 造成「人为平台期」
    （loss 不再降不是数据饱和，是旋钮已关死）。WSD 稳定期 lr 一直开着，
    模型持续学习，最后 15% 才收尾定型。衰减到峰值的 1/20（wsd-end-frac）。
    """

    def __init__(self, *args, wsd_decay_ratio=0.15, wsd_end_frac=0.05, **kwargs):
        self.wsd_decay_ratio = wsd_decay_ratio
        self.wsd_end_frac = wsd_end_frac
        super().__init__(*args, **kwargs)

    def create_scheduler(self, num_training_steps, optimizer=None, **kwargs):
        # transformers 5.x 契约：必须赋给 self.lr_scheduler（调用方忽略返回值），
        # optimizer 参数恒为 None，用 Trainer 自建的 self.optimizer 兜底
        optimizer = optimizer or self.optimizer
        warmup = max(1, int(self.args.warmup_steps))
        decay_from = int(num_training_steps * (1 - self.wsd_decay_ratio))
        end_frac = self.wsd_end_frac

        def lr_lambda(step):
            if step < warmup:
                return step / warmup
            if step < decay_from:
                return 1.0
            frac = min(1.0, (step - decay_from) / max(1, num_training_steps - decay_from))
            return 1.0 - frac * (1.0 - end_frac)

        self.lr_scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)
        self._created_lr_scheduler = True
        return self.lr_scheduler


class PackedDataset(Dataset):
    """多个 uint32 bins 拼接的窗口数据集：无 padding、无浪费，窗口不跨 bin 边界。"""

    def __init__(self, bin_paths, seq_len):
        self.seq_len = seq_len
        self.bins = [np.memmap(p, dtype=np.uint32, mode="r") for p in bin_paths]
        self.windows = [len(b) // seq_len for b in self.bins]
        self.offsets = np.cumsum([0] + self.windows)

    def __len__(self):
        return int(self.offsets[-1])

    def __getitem__(self, i):
        b = int(np.searchsorted(self.offsets, i, side="right") - 1)
        j = i - self.offsets[b]
        s = self.bins[b][j * self.seq_len:(j + 1) * self.seq_len].astype(np.int64)
        return {"input_ids": torch.from_numpy(s), "labels": torch.from_numpy(s)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/Qwen3-0.6B")
    ap.add_argument("--data", required=True, help="逗号分隔的 tokens.bin 路径")
    ap.add_argument("--seq-len", type=int, default=4096)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--warmup-ratio", type=float, default=0.03)
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--per-device-bs", type=int, default=16)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--save-steps", type=int, default=2000)
    ap.add_argument("--logging-steps", type=int, default=10)
    ap.add_argument("--deepspeed", default=None)
    ap.add_argument("--max-steps", type=int, default=-1)
    ap.add_argument("--overwrite", action="store_true", help="冒烟重跑用")
    # 吞吐优化开关：分块 CE 破 logits 内存墙；bs 提到 16 后关梯度检查点省重算
    ap.add_argument("--chunked-ce", action="store_true", help="分块交叉熵（bs≥16 时必开）")
    ap.add_argument("--ce-chunk", type=int, default=256, help="分块 CE 每块位置数")
    ap.add_argument("--no-grad-checkpoint", action="store_true", help="关梯度检查点（bs16 显存够时开）")
    ap.add_argument("--torch-compile", action="store_true", help="torch.compile 加速（冒烟验证后开）")
    ap.add_argument("--resume-from-checkpoint", default=None, help="从指定 checkpoint 目录续训")
    ap.add_argument("--wsd", action="store_true", help="WSD 调度（续训推荐：稳定期恒定 lr，末 15% 衰减）")
    ap.add_argument("--wsd-decay-ratio", type=float, default=0.15, help="WSD 衰减段占比")
    ap.add_argument("--wsd-end-frac", type=float, default=0.05, help="WSD 衰减终点 lr = 峰值 × 此值（默认 1/20）")
    ap.add_argument("--seed", type=int, default=20261024)
    args = ap.parse_args()

    set_seed(args.seed)
    ds = PackedDataset(args.data.split(","), args.seq_len)
    if len(ds) == 0:
        raise SystemExit("数据集为空，检查 bins")
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    # bs16 时激活 ≈12.6GB 装得下，关检查点省掉重算；bs4 显存紧时仍默认开启
    if not args.no_grad_checkpoint:
        model.gradient_checkpointing_enable()
    # 双卡并发下只允许 rank 0 清目录，避免竞争删除；ignore_errors 兜底残留
    if args.overwrite and os.path.exists(args.out) and int(os.environ.get("LOCAL_RANK", "0")) == 0:
        shutil.rmtree(args.out, ignore_errors=True)
    # transformers 5.x 移除 warmup_ratio，改 warmup_steps（按总步数 3% 折算）
    world = int(os.environ.get("WORLD_SIZE", "1"))
    steps_per_epoch = math.ceil(len(ds) / (world * args.per_device_bs * args.grad_accum))
    total_steps = args.max_steps if args.max_steps > 0 else math.ceil(steps_per_epoch * args.epochs)
    ta = TrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.per_device_bs,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_steps=max(1, int(total_steps * args.warmup_ratio)),
        lr_scheduler_type="cosine",
        num_train_epochs=args.epochs,
        max_steps=args.max_steps if args.max_steps > 0 else -1,
        bf16=True,
        logging_steps=args.logging_steps,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=3,
        deepspeed=args.deepspeed,
        report_to=["mlflow"],
        ddp_find_unused_parameters=False,
        seed=args.seed,
        run_name=os.path.basename(args.out),
        torch_compile=args.torch_compile,
        # 注意：compile 会把 chunked CE 的分块循环融合成完整 logits（seq4096×bs16×152k≈20GB）
        # 内存墙回归直接 OOM；PT2 路线不用 compile（见 run_pt2_wsd.sh 头注）
        torch_compile_mode="default",
    )
    trainer_cls = WSDTrainer if args.wsd else (ChunkedCETrainer if args.chunked_ce else Trainer)
    kwargs = {"chunk_size": args.ce_chunk} if args.chunked_ce else {}
    if args.wsd:
        kwargs.update({"wsd_decay_ratio": args.wsd_decay_ratio, "wsd_end_frac": args.wsd_end_frac})
    trainer = trainer_cls(model=model, args=ta, train_dataset=ds, **kwargs)
    # 续训：resume_from_checkpoint 恢复 optimizer/scheduler/数据位置，
    # 步数续接 → 余弦 LR 按剩余步继续走，等价于没中断
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint or False)
    # ZeRO 分片状态由 save_model 聚合后落盘，SFT 直接从此目录加载
    trainer.save_model(os.path.join(args.out, "final"))
    print("TRAINING_FINISHED")


if __name__ == "__main__":
    main()
