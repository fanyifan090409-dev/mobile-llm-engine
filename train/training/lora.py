#!/usr/bin/env python3
"""极简 LoRA：不依赖 peft，冻结基座，只训低秩 A/B；训练后合并回基座权重。

只替换 Transformer 的线性层（q/k/v/o/gate/up/down），lm_head 与 embedding 不动。
"""
import json
import math

import torch
import torch.nn as nn

TARGETS = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")


class LoRALinear(nn.Module):
    def __init__(self, base: nn.Linear, r: int, alpha: int, dropout: float):
        super().__init__()
        self.base = base
        self.r = r
        self.scaling = alpha / r
        self.drop = nn.Dropout(dropout)
        self.A = nn.Parameter(torch.empty(r, base.in_features, dtype=torch.float32))
        self.B = nn.Parameter(torch.zeros(base.out_features, r, dtype=torch.float32))
        nn.init.kaiming_uniform_(self.A, a=math.sqrt(5))
        for p in self.base.parameters():
            p.requires_grad = False

    def forward(self, x):
        y = self.base(x)
        a = self.A.to(x.dtype)
        b = self.B.to(x.dtype)
        return y + self.drop(x) @ a.t() @ b.t() * self.scaling


def apply_lora(model, r=16, alpha=32, dropout=0.05):
    for p in model.parameters():
        p.requires_grad = False
    replaced = 0
    for name, module in list(model.named_modules()):
        if not isinstance(module, nn.Linear):
            continue
        if name.rsplit(".", 1)[-1] not in TARGETS:
            continue
        parent_name, _, child = name.rpartition(".")
        parent = model.get_submodule(parent_name) if parent_name else model
        setattr(parent, child, LoRALinear(module, r, alpha, dropout))
        replaced += 1
    return replaced


def trainable_params(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def enable_input_require_grads(model):
    """梯度检查点 + 冻结 embedding 时，让输入图带 requires_grad。"""
    def hook(module, inputs, output):
        if isinstance(output, torch.Tensor):
            output.requires_grad_(True)
    model.get_input_embeddings().register_forward_hook(hook)


def merge_lora(model):
    """把 B@A*scaling 加回 base.weight，并用 base 替换 LoRALinear。"""
    for name, module in list(model.named_modules()):
        if not isinstance(module, LoRALinear):
            continue
        with torch.no_grad():
            delta = (module.B.float() @ module.A.float()) * module.scaling
            module.base.weight.data += delta.to(module.base.weight.dtype)
        parent_name, _, child = name.rpartition(".")
        parent = model.get_submodule(parent_name) if parent_name else model
        setattr(parent, child, module.base)
    return model


def save_config(path, r, alpha, dropout):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"r": r, "alpha": alpha, "dropout": dropout,
                   "targets": list(TARGETS)}, f, ensure_ascii=False, indent=2)
