#!/usr/bin/env python3
"""SFT：messages 数据 → chat template 化，只对 assistant 回复算 loss（prompt 掩码）。

用法：
  torchrun --nproc_per_node=2 scripts/train_sft.py \
    --model checkpoints/qwen3-0.6b-pt-20261024/final --tokenizer models/Qwen3-0.6B \
    --data data/train/train.jsonl --out checkpoints/qwen3-0.6b-sft-20261024 \
    --deepspeed scripts/ds_zero2.json --epochs 2 --per-device-bs 16 --grad-accum 4
"""
import argparse
import json
import math
import os
import shutil

import torch
from torch.utils.data import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments, set_seed

from chunked_ce import ChunkedCETrainer


class SFTDataset(Dataset):
    """messages → input_ids + labels；__init__ 预计算避免每 epoch 重复模板化。

    no_think=True（SFT3 起）：apply_chat_template 传 enable_thinking=False，
    官方模板在每个 assistant 回合头后注入空思考块 <think>\\n\\n</think>\\n\\n，
    与推理侧 EngineCore.thinkTags 同款注入对齐——模型被钉在「不思考直接答」模式。
    """

    def __init__(self, path, tokenizer, max_len, no_think=False):
        with open(path, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        tmpl_kwargs = {"enable_thinking": False} if no_think else {}
        self.samples = []
        for r in rows:
            msgs = r["messages"]
            prompt_msgs = msgs[:-1] if msgs and msgs[-1]["role"] == "assistant" else msgs
            prompt = tokenizer.apply_chat_template(prompt_msgs, add_generation_prompt=True, tokenize=False, **tmpl_kwargs)
            full = tokenizer.apply_chat_template(msgs, add_generation_prompt=False, tokenize=False, **tmpl_kwargs)
            pid = tokenizer(prompt, add_special_tokens=False)["input_ids"]
            fid = tokenizer(full, add_special_tokens=False)["input_ids"]
            if len(fid) > max_len:
                cut = len(fid) - max_len
                fid = fid[cut:]
                n_prompt = max(len(pid) - cut, 0)
            else:
                n_prompt = len(pid)
            labels = [-100] * n_prompt + fid[n_prompt:]
            self.samples.append((fid, labels))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, i):
        fid, labels = self.samples[i]
        return {
            "input_ids": torch.tensor(fid, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


def make_collator(tok):
    """右对齐 padding collator：input_ids 补 pad id、labels 补 -100、attention_mask 0/1。

    为什么自己写：transformers 5.20 的 DataCollatorWithPadding 走 tokenizer.pad，
    而 base 类的 _pad 只给 model_input_names（input_ids/attention_mask）补长，
    不处理「labels」键——变长样本的 labels 保持原长，堆 batch 时直接抛
    「excessive nesting」。所以 padding 自己做，不依赖库。
    """
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id

    def collate(features):
        max_len = max(len(f["input_ids"]) for f in features)
        input_ids, labels, masks = [], [], []
        for f in features:
            n = len(f["input_ids"])
            p = max_len - n
            input_ids.append(torch.cat([f["input_ids"], torch.full((p,), pad_id, dtype=torch.long)]))
            labels.append(torch.cat([f["labels"], torch.full((p,), -100, dtype=torch.long)]))
            masks.append(torch.cat([torch.ones(n, dtype=torch.long), torch.zeros(p, dtype=torch.long)]))
        return {"input_ids": torch.stack(input_ids),
                "labels": torch.stack(labels),
                "attention_mask": torch.stack(masks)}

    return collate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--tokenizer", default=None, help="不填则用 model 目录的 tokenizer")
    ap.add_argument("--data", required=True)
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--warmup-ratio", type=float, default=0.03)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--per-device-bs", type=int, default=16)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--save-steps", type=int, default=500)
    ap.add_argument("--logging-steps", type=int, default=10)
    ap.add_argument("--deepspeed", default=None)
    ap.add_argument("--overwrite", action="store_true")
    # 与 PT 同一套吞吐优化开关（SFT 数据集 86k 样本，bs 大时同样吃 logits 墙）
    ap.add_argument("--chunked-ce", action="store_true", help="分块交叉熵（bs≥16 时必开）")
    ap.add_argument("--ce-chunk", type=int, default=256, help="分块 CE 每块位置数")
    ap.add_argument("--no-grad-checkpoint", action="store_true", help="关梯度检查点（bs16 显存够时开）")
    ap.add_argument("--torch-compile", action="store_true", help="torch.compile 加速（冒烟验证后开）")
    ap.add_argument("--max-steps", type=int, default=-1, help=">0 时限制步数（冒烟用）")
    ap.add_argument("--no-think", action="store_true", help="模板 enable_thinking=false 空思考块注入（SFT3 起）")
    ap.add_argument("--val", default=None, help="验证集 jsonl（assemble 分层抽出的 val.jsonl），不填则跳过 eval")
    ap.add_argument("--eval-steps", type=int, default=500, help="验证集 loss 评估间隔（与 save-steps 对齐）")
    ap.add_argument("--seed", type=int, default=20261024)
    args = ap.parse_args()

    set_seed(args.seed)
    tok = AutoTokenizer.from_pretrained(args.tokenizer or args.model)
    ds = SFTDataset(args.data, tok, args.max_len, no_think=args.no_think)
    if len(ds) == 0:
        raise SystemExit("数据集为空")
    # 验证集与训练集同一模板化路径；val 分层抽出且 schedule 保留完整轨迹，
    # 训练/验证同分布，eval_loss 才有监视意义（与 PT 线同一口径）
    val_ds = None
    if args.val:
        val_ds = SFTDataset(args.val, tok, args.max_len, no_think=args.no_think)
        if len(val_ds) == 0:
            raise SystemExit("验证集为空")
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, attn_implementation="sdpa",
    )
    if not args.no_grad_checkpoint:
        model.gradient_checkpointing_enable()
    # 双卡并发下只允许 rank 0 清目录，避免竞争删除；ignore_errors 兜底残留
    if args.overwrite and os.path.exists(args.out) and int(os.environ.get("LOCAL_RANK", "0")) == 0:
        shutil.rmtree(args.out, ignore_errors=True)
    # transformers 5.x：warmup_ratio → warmup_steps；Trainer 的 tokenizer → processing_class
    world = int(os.environ.get("WORLD_SIZE", "1"))
    total_steps = math.ceil(
        math.ceil(len(ds) / (world * args.per_device_bs * args.grad_accum)) * args.epochs
    )
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
        eval_strategy="steps" if val_ds is not None else "no",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=args.save_steps,
        save_total_limit=3,
        deepspeed=args.deepspeed,
        report_to=["mlflow"],
        ddp_find_unused_parameters=False,
        seed=args.seed,
        run_name=os.path.basename(args.out),
        torch_compile=args.torch_compile,
    )
    trainer_cls = ChunkedCETrainer if args.chunked_ce else Trainer
    kwargs = {"chunk_size": args.ce_chunk} if args.chunked_ce else {}
    trainer = trainer_cls(model=model, args=ta, train_dataset=ds, eval_dataset=val_ds,
                          processing_class=tok, data_collator=make_collator(tok), **kwargs)
    trainer.train()
    trainer.save_model(os.path.join(args.out, "final"))
    tok.save_pretrained(os.path.join(args.out, "final"))
    print("TRAINING_FINISHED")


if __name__ == "__main__":
    main()
