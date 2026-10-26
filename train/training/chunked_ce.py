#!/usr/bin/env python3
"""分块交叉熵：绕过「logits 内存墙」，让 0.6B 续训 batch size 从 4 提到 16。

问题背景
--------
Qwen3-0.6B 词表 152,936。原生 HF 前向会算出完整 logits 张量：
    [batch, seq, vocab] = [16, 2048, 152936]，fp32 下 ≈ 16×2048×152936×4B ≈ 20GB
单卡 32GB 装不下 → 被迫 bs=4（≈5GB）。训练慢的根因就在这里：
bs 小 → 每步有效样本少 → 同样 4197 步吃满 2.2B tokens 就要更多步 → 慢。

解决思路
--------
交叉熵 loss 只依赖「logits 按 label 挑出的那一列」和「整行 logsumexp」，
两者都可以按位置分块计算，永远不需要把完整 logits 落盘。
块内峰值显存：chunk×vocab ≈ 256×152936×4B ≈ 157MB，从 20GB 降到零头。
反向同理：softmax 梯度按块重算（省下整块概率矩阵的激活），
并把 dW/db 累加进 lm_head 的梯度，数学上与原生完全等价。

本文件三个组件：
1. ChunkedCrossEntropy —— 自定义 autograd 函数，分块正反向
2. ChunkedCETrainer     —— 只走 backbone 拿 hidden_states，绕开 logits 计算
3. check_equivalence    —— 上线前自检：分块 loss/梯度 vs 原生 loss/梯度 逐项比对
"""
import torch
from transformers import Trainer


class ChunkedCrossEntropy(torch.autograd.Function):
    """按位置分块算交叉熵 + 梯度。labels 中 -100 位置不计 loss（沿用 HF 约定）。"""

    @staticmethod
    def forward(ctx, hidden, labels, weight, bias, chunk_size):
        # ctx 是 autograd 跨正反向的「背包」，这里塞进反向要用的东西
        ctx.chunk_size = chunk_size
        ctx.save_for_backward(hidden, labels, weight, bias)
        # 显存关键：全程 fp32 累加，但任何时刻只持有「一个块」的 logits
        total = torch.zeros((), device=hidden.device, dtype=torch.float32)
        n_tokens = 0
        for start in range(0, hidden.size(1), chunk_size):
            h = hidden[:, start:start + chunk_size].reshape(-1, hidden.size(-1))
            lbl = labels[:, start:start + chunk_size].reshape(-1)
            # logits = h @ weight^T：矩阵乘保持 bf16 走 tensor core。
            # 不要升 fp32 算矩阵乘——TF32 默认关闭时 fp32 矩阵乘慢约 8 倍，
            # 实测比原配置还慢（18.5s/it），省下的显存全还回时间了
            logits = h @ weight.t()
            if bias is not None:
                logits = logits + bias
            # logsumexp 内部自动把 bf16 升到 fp32 再算，数值稳定（logsumexp - picked 式）
            logsum = torch.logsumexp(logits, dim=-1)
            picked = logits.gather(1, lbl.clamp(min=0).unsqueeze(1)).squeeze(1)
            mask = lbl != -100
            total = total + ((-picked.float() + logsum) * mask.float()).sum()
            n_tokens += int(mask.sum().item())
        # 必须赶在任何提前 return 之前设好，防反向时 AttributeError
        ctx.n_tokens = n_tokens
        if n_tokens == 0:
            return total  # 整批全被掩码：loss=0，梯度也全 0（见 backward）
        return total / n_tokens

    @staticmethod
    def backward(ctx, grad_output):
        hidden, labels, weight, bias = ctx.saved_tensors
        chunk_size, n_tokens = ctx.chunk_size, ctx.n_tokens
        bs, seq, dim = hidden.shape
        # 全掩码批：按规则返回与输入同形的 0 梯度（None 表示该输入不需要梯度）
        if n_tokens == 0:
            return (torch.zeros_like(hidden), None, torch.zeros_like(weight),
                    torch.zeros_like(bias) if bias is not None else None, None)

        # dW/db 累加器按「最终精度」分配（fp32），块梯度只占一小片显存
        dhidden = torch.zeros(bs, seq, dim, device=hidden.device, dtype=torch.float32)
        dweight = torch.zeros_like(weight, dtype=torch.float32)
        dbias = torch.zeros_like(bias, dtype=torch.float32) if bias is not None else None

        for start in range(0, seq, chunk_size):
            h = hidden[:, start:start + chunk_size]
            lbl = labels[:, start:start + chunk_size]
            hf = h.reshape(-1, dim)
            # 反向里重算 softmax（梯度检查点思路：不存激活，用时再算，省显存换时间）
            # logits 矩阵乘同样走 bf16；softmax 内部自动升 fp32
            logits = hf @ weight.t()
            if bias is not None:
                logits = logits + bias
            probs = torch.softmax(logits, dim=-1)
            rows = torch.arange(probs.size(0), device=probs.device)
            # 正确标签那列减 1 → 得到 dCE/dlogits，再乘 label 掩码与 1/n
            probs[rows, lbl.reshape(-1).clamp(min=0)] -= 1.0
            probs *= ((lbl.reshape(-1) != -100).float() / n_tokens).unsqueeze(1)
            # 回传矩阵乘也走 bf16（与原生 CE 反向一致），累加进 fp32 缓冲
            pb = probs.to(hidden.dtype)
            dhidden[:, start:start + chunk_size] = (pb @ weight).reshape(bs, -1, dim)
            dweight += pb.t() @ hf
            if dbias is not None:
                dbias += probs.sum(0)

        dhidden = dhidden * grad_output
        # grad_output 是 Trainer 归一化因子（= n_tokens/num_items）经 autograd 传来的。
        # 三个梯度必须全部乘它：漏乘 dweight/dbias 会让 lm_head 梯度相对 backbone
        # 放大 num_items/n_tokens 倍（DS 探针实测 grad_norm 4.2 vs 原生 1.5，就是它抓的）
        dweight = dweight * grad_output
        if dbias is not None:
            dbias = dbias * grad_output
        # 返回精度与输入一致（bf16），保持与模型其余部分梯度类型统一
        return (dhidden.to(hidden.dtype), None, dweight.to(weight.dtype),
                dbias.to(bias.dtype) if dbias is not None else None, None)


class ChunkedCETrainer(Trainer):
    """重写 compute_loss：模型只算到最后一层 hidden_states，交叉熵走分块函数。

    关键点：model.model(...) 是「裸 backbone」前向（HF 里外层 model 的 lm_head
    挂在 model.lm_head），拿到 last_hidden_state 后自己接分块 CE，
    完整 logits 从头到尾不存在。
    """

    def __init__(self, chunk_size=256, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ce_chunk_size = chunk_size

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        labels = inputs.pop("labels")
        # return_dict=True 拿 BaseModelOutput，.last_hidden_state 就是最后一层输出
        hidden = model.model(**inputs, return_dict=True).last_hidden_state
        # 语言模型是「下一 token 预测」：位置 t 的 hidden 预测标签 t+1。
        # 必须与 HF 原生一致做 shift（logits 去尾、labels 去头），
        # 否则变成「用自己预测自己」，loss 虚低、梯度错位（等价自检就是被它抓出来的）
        shift_hidden = hidden[..., :-1, :].contiguous()
        shift_labels = labels[..., 1:].contiguous()
        loss = ChunkedCrossEntropy.apply(
            shift_hidden, shift_labels, model.lm_head.weight,
            getattr(model.lm_head, "bias", None), self.ce_chunk_size,
        )
        if num_items_in_batch is not None:
            # transformers v5 约定：模型接受 num_items_in_batch 时，loss 必须按
            # 「整个累积周期的有效 token 数」归一化（原生 CE 在模型内部就是
            # Σ_CE/num_items，Trainer 上报时再乘回 gas）。分块 CE 返回的是单
            # micro-batch 均值 Σ_CE/n_tokens，不纠正的话 loss 与梯度整体偏
            # gas 倍——线上首测 loss 25.6 = 3.2×8 就是它（诊断脚本
            # check_ce_ds.py 逐位比对确认，修复后与原生完全一致）
            n_tokens = (shift_labels != -100).sum()
            loss = loss * (n_tokens / num_items_in_batch)
            # v5 默认 average_tokens_across_devices=True：双卡时 num_items 是
            # 跨卡汇总数（= 单卡 × num_processes），原生 compute_loss 最后会乘
            # num_processes 抵消。我们 override 了 compute_loss，这一步必须自己
            # 补——漏掉的话 loss/梯度整体偏 1/num_processes 倍（双卡首测 loss
            # 1.58 = 3.17/2，单卡探针 world_size=1 看不到这个差，双卡才暴露）
            if self.args.average_tokens_across_devices:
                loss_scale = self.accelerator.num_processes // self.get_tp_size()
                loss = loss * (loss_scale if self.args.n_gpu <= 1 else self.args.n_gpu)
        return (loss, None) if return_outputs else loss

    def prediction_step(self, model, inputs, prediction_loss_only, ignore_keys=None):
        """eval 路径自己实现：backbone 前向 + 分块 CE，返回 (loss, None, None)。

        不调父类：transformers 5.20 的 prediction_step 假定 compute_loss 返回
        (loss, tuple(logits,...)) 并对 outputs[1:] 做下标——分块 CE 没有 logits，
        父类路径直接 TypeError（1.7B 冒烟首测抓到的，冒烟必须覆盖 eval 路径）。
        """
        inputs = self._prepare_inputs(inputs)
        with torch.no_grad():
            with self.compute_loss_context_manager():
                loss = self.compute_loss(model, inputs, return_outputs=False)
            loss = loss.mean().detach()
        return (loss, None, None)


def check_equivalence(model_path, chunk_size=256, seed=20261024):
    """上线前自检：同一随机批，分块 CE 与原生 CE 的 loss、lm_head 权重梯度逐项比对。

    通过线（工程容差，bf16 下数值噪声量级）：
      |Δloss| < 2e-2，|Δdw| 相对 < 5e-2
    打印 CE_EQUIVALENCE_OK / CE_EQUIVALENCE_FAIL，供 swap 脚本 grep 判决。
    """
    import os
    from transformers import AutoModelForCausalLM

    torch.manual_seed(seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    def _load():
        m = AutoModelForCausalLM.from_pretrained(
            model_path, dtype=torch.bfloat16, attn_implementation="sdpa"
        ).to(dev)
        m.eval()
        return m

    with torch.no_grad():
        model = _load()
        bs, seq = 2, 128
        ids = torch.randint(0, 1024, (bs, seq), device=dev)
        labels = ids.clone()
        # 一半位置掩码成 -100，验证掩码路径也正确
        labels[:, seq // 2:] = -100
        # 原生参考：标准 lm_head 路径
        ref = model(**{"input_ids": ids, "labels": labels})
        loss_ref = ref.loss
        w_ref = model.lm_head.weight
        # 分块路径：backbone hidden → ChunkedCrossEntropy（同样做 next-token shift）
        hidden = model.model(input_ids=ids).last_hidden_state
        loss_chunk = ChunkedCrossEntropy.apply(
            hidden[:, :-1], labels[:, 1:], w_ref,
            getattr(model.lm_head, "bias", None), chunk_size,
        )
        print(f"loss native={loss_ref.item():.6f}  chunked={loss_chunk.item():.6f}")

    # 梯度比对必须开 grad 单独跑一遍（上面 no_grad 拿不到 .grad）
    model = _load()
    hidden = model.model(input_ids=ids).last_hidden_state
    w = model.lm_head.weight
    hidden.requires_grad_(True)
    w.requires_grad_(True)
    loss = ChunkedCrossEntropy.apply(
        hidden[:, :-1], labels[:, 1:], w,
        getattr(model.lm_head, "bias", None), chunk_size,
    )
    loss.backward()
    g_w = w.grad.float()

    model.zero_grad()
    out = model(**{"input_ids": ids, "labels": labels})
    out.loss.backward()
    g_w_ref = model.lm_head.weight.grad.float()

    dl = abs(loss_ref.item() - loss_chunk.item())
    dw = (g_w - g_w_ref).abs().max().item()
    dw_rel = (dw / g_w_ref.abs().max().item()) if g_w_ref.abs().max().item() > 0 else float("nan")
    print(f"|Δloss|={dl:.6f}  max|Δdw|={dw:.6f}  相对={dw_rel:.6f}")
    if dl < 2e-2 and dw_rel < 5e-2:
        print("CE_EQUIVALENCE_OK")
        return True
    print("CE_EQUIVALENCE_FAIL")
    return False
