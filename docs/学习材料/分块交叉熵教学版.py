#!/usr/bin/env python3
# ============================================================================
# 分块交叉熵 · 教学版（供学习，非生产文件）
# ----------------------------------------------------------------------------
# 这份文件的功能代码和 scripts/chunked_ce.py 完全一样，
# 区别在于：每一段都配了「给人看」的讲解备注。
# 建议按顺序读：先看故事 → 再看 forward → 再看 backward → 最后看 Trainer。
# ============================================================================

# ----------------------------------------------------------------------------
# 第 0 章：故事的起点——为什么训练这么慢？
# ----------------------------------------------------------------------------
# 我们的 Qwen3-0.6B 词表有 152,936 个词（token）。
# 模型每算一步，最后都要回答一个问题：
#   「当前位置，这 15 万个词里每一个的可能性各是多少？」
# 这 15 万个分数组成的向量，就叫做 logits（还没归一化的「原始得分」）。
#
# 常规做法（HuggingFace 原生）：一口气把整批数据的 logits 全算出来，存进显存：
#   [batch=16, seq=2048, vocab=152936] 个浮点数
#   = 16 × 2048 × 152936 × 4 字节（fp32）≈ 20GB
# 单卡只有 32GB，光这一张表就吃掉 20GB，剩下的装不下模型和梯度了。
# 所以之前被迫把 batch 降到 4（≈5GB）——batch 越小，同样多的数据就要更多步，
# 训练就慢。这就是「logits 内存墙」。
#
# 破墙的思路其实很简单，一句话：
#   「交叉熵这个 loss，数学上根本不需要完整的 logits 表，
#     它只需要按位置一小块一小块地算。」
# 每一块只有 256 个位置 × 15 万词表 ≈ 157MB，算完即扔。
# 下面就是这套「分块」的实现。
# ----------------------------------------------------------------------------
import torch
from torch.nn import CrossEntropyLoss
from transformers import Trainer


# ----------------------------------------------------------------------------
# 第 1 章：什么是交叉熵 loss？（30 秒版）
# ----------------------------------------------------------------------------
# 交叉熵（Cross Entropy）衡量「模型猜的分布」和「正确答案」差多远。
# 一个位置的真实标签是词 t，模型给出的 logits 是向量 z，那么：
#
#   CE = -z[t] + log( Σ_k exp(z[k]) )
#       └─正确词得分─┘   └─全部词得分的「总和大小」─┘
#
# 直觉：z[t] 越大（正确词得分越高）→ loss 越小，模型越好。
# 后面那项 logΣexp（数学上叫 logsumexp）是「分母」，保证 loss 不会因为
# 所有得分一起变大而作弊变小。
# 直接算 Σexp 会溢出（exp(1000) = 无穷大），所以工程上统一用
# torch.logsumexp——它内部先减掉最大值再算 exp，数值稳定。
# ----------------------------------------------------------------------------


class ChunkedCrossEntropy(torch.autograd.Function):
    """按位置分块算交叉熵 + 梯度。labels 中 -100 的位置不计 loss（沿用 HF 约定）。"""

    # ==========================================================================
    # 第 2 章：forward——把 loss 算出来，但一小块一小块地算
    # ==========================================================================
    # 先认识 autograd.Function：PyTorch 允许你自定义「一个运算」。
    # 规则很简单，就是一对函数：
    #   forward ：拿到输入，算出输出（这里是 loss 数字）
    #   backward：拿到「输出的梯度」，算出「每个输入的梯度」
    # 训练时 PyTorch 会自动先调 forward 再调 backward，中间的状态靠 ctx 传递。
    # -------------------------------------------------------------------------
    @staticmethod
    def forward(ctx, hidden, labels, weight, bias, chunk_size):
        # hidden : [batch, seq, 隐藏维度]，模型最后一层的输出（每个位置一个向量）
        # labels : [batch, seq]，每个位置的正确答案 token id；-100 表示「这个位置不算」
        # weight : [vocab, 隐藏维度]，lm_head 的权重——logits = hidden @ weight^T
        # bias   : [vocab]，可选偏置项
        # chunk_size : 一次算多少个位置（256）
        #
        # ctx 是 autograd 给的「背包」，正反向之间传东西全靠它。
        ctx.chunk_size = chunk_size
        ctx.save_for_backward(hidden, labels, weight, bias)  # 反向时从背包取回

        # 总 loss 用 fp32 累加（精度稳）；关键点：任何时刻显存里只有「一个块」的 logits
        total = torch.zeros((), device=hidden.device, dtype=torch.float32)
        n_tokens = 0  # 实际参与计分的 token 数（-100 的位置不算）

        # 核心循环：把 seq 那一维切成一段段 256，逐段算完就扔
        for start in range(0, hidden.size(1), chunk_size):
            # 取出这一块的所有位置，摊平成 [块内位置数, 隐藏维度]
            h = hidden[:, start:start + chunk_size].reshape(-1, hidden.size(-1))
            lbl = labels[:, start:start + chunk_size].reshape(-1)

            # logits = h @ weight^T：就是矩阵乘法，得到 [块内位置数, 152936]
            # ★第二个大坑（第一版踩过）★：矩阵乘保持 bf16，别升 fp32！
            # GPU 的 tensor core 专跑 bf16/fp16 矩阵乘；纯 fp32 矩阵乘
            # （PyTorch 默认不开 TF32）要慢大约 8 倍。
            # 第一版图省事全用 fp32 算，实测每步 18.5 秒——比优化前还慢。
            logits = h @ weight.t()
            if bias is not None:
                logits = logits + bias

            # 对应第 1 章的公式，逐行拆开：
            # 数值精度怎么保证？logsumexp 和 softmax 内部会自动把 bf16
            # 升成 fp32 再算，所以「矩阵乘用快精度、求和用稳精度」两不耽误
            logsum = torch.logsumexp(logits, dim=-1)          # log Σexp(z)  每行一个数
            # gather：从每行 15 万个分数里，挑出「正确答案」那一个
            # clamp(min=0)：防止 -100 变成负数下标报错（先随便取第 0 列，反正会被掩码掉）
            picked = logits.gather(1, lbl.clamp(min=0).unsqueeze(1)).squeeze(1)
            mask = lbl != -100                                  # 哪些位置要算
            # -picked + logsum = 该位置的 CE；×mask 把 -100 位置清零；sum 累加
            # （picked 是 bf16，.float() 升精度后再与 fp32 的 logsum 相加）
            total = total + ((-picked.float() + logsum) * mask.float()).sum()
            n_tokens += int(mask.sum().item())

        # 必须赶在任何提前 return 之前设好：backward 要读这个数
        ctx.n_tokens = n_tokens
        if n_tokens == 0:
            return total  # 整批全被掩码：loss=0，梯度也全 0（见 backward 开头）
        return total / n_tokens  # 平均到每个 token，这就是最终 loss


    # ==========================================================================
    # 第 3 章：backward——梯度也分块算，而且「现用现算」
    # ==========================================================================
    # 训练要的梯度有三个：
    #   dhidden  → 传回模型主体，更新前面的所有层
    #   dweight  → 更新 lm_head 权重
    #   dbias    → 更新 lm_head 偏置
    # 数学上，CE 对 logits 的梯度是「softmax 概率 - 正确答案的 one-hot」。
    # 如果走常规路线，要先把整批的 softmax 概率存下来（又是 20GB），
    # 所以我们在这里「现用现算」：每个块现场重算一次 softmax。
    # 这其实是「梯度检查点」思想的袖珍版：省显存，代价是重复计算。
    # -------------------------------------------------------------------------
    @staticmethod
    def backward(ctx, grad_output):
        hidden, labels, weight, bias = ctx.saved_tensors  # 从背包取出
        chunk_size, n_tokens = ctx.chunk_size, ctx.n_tokens
        bs, seq, dim = hidden.shape

        # 全掩码批（所有位置都是 -100）：按 autograd 规矩，每个输入都返回梯度，
        # 数值全 0；None 表示「这个输入不需要梯度」（labels、chunk_size 就是 None）
        if n_tokens == 0:
            return (torch.zeros_like(hidden), None, torch.zeros_like(weight),
                    torch.zeros_like(bias) if bias is not None else None, None)

        # 累加器：dweight/dbias 是整个词表的大小，这里一次分配到位（fp32 精度）
        # dhidden 和输入同形状——这个才是真正的显存大头，但它是 bf16 级别的量级，
        # 比 20GB 的 logits 表小一个数量级
        dhidden = torch.zeros(bs, seq, dim, device=hidden.device, dtype=torch.float32)
        dweight = torch.zeros_like(weight, dtype=torch.float32)
        dbias = torch.zeros_like(bias, dtype=torch.float32) if bias is not None else None

        for start in range(0, seq, chunk_size):
            h = hidden[:, start:start + chunk_size]
            lbl = labels[:, start:start + chunk_size]
            hf = h.reshape(-1, dim)

            # 现场重算这块的 logits 和 softmax（省显存的代价：多算一遍）
            # 矩阵乘同样走 bf16（和第 2 章的坑是同一个道理：fp32 慢 8 倍）
            logits = hf @ weight.t()
            if bias is not None:
                logits = logits + bias
            probs = torch.softmax(logits, dim=-1)   # 内部自动升 fp32，精度有保障

            # 数学核心一步：dCE/dlogits = probs - one_hot(正确答案)
            rows = torch.arange(probs.size(0), device=probs.device)
            probs[rows, lbl.reshape(-1).clamp(min=0)] -= 1.0   # 正确那列减 1
            # 掩码位置梯度清零；整体 ×1/n（因为 loss 平均过 n 个 token）
            probs *= ((lbl.reshape(-1) != -100).float() / n_tokens).unsqueeze(1)

            # 链式法则三连（dCE/dlogits = probs 已算好）：
            # 回传矩阵乘也用 bf16（与 PyTorch 原生 CE 反向的做法一致），
            # 结果累加进 fp32 缓冲，精度损失可以忽略
            pb = probs.to(hidden.dtype)
            dhidden[:, start:start + chunk_size] = (pb @ weight).reshape(bs, -1, dim)
            dweight += pb.t() @ hf    # dW = probs^T @ h，跨块累加
            if dbias is not None:
                dbias += probs.sum(0)    # db = 每列概率之和（fp32 直接累加）

        dhidden = dhidden * grad_output  # 乘上游传来的梯度（loss 对 loss 的导数，=1 但保持链完整）
        # ★第四个坑（归一化修复后冒出来的）★：grad_output 是 Trainer 的归一化
        # 因子（= n_tokens/num_items，见第 4 章第三个坑）。三个梯度必须全都乘它！
        # 第一版只乘了 dhidden，漏了 dweight/dbias——lm_head 的梯度就比 backbone
        # 大了 num_items/n_tokens 倍，实测 grad_norm 4.2 vs 原生 1.5。
        # 记住一条铁律：backward 返回的每一个梯度都要乘 grad_output。
        dweight = dweight * grad_output
        if dbias is not None:
            dbias = dbias * grad_output
        # 返回的精度和输入一致（bf16），保持与模型其余部分梯度类型统一
        return (dhidden.to(hidden.dtype), None, dweight.to(weight.dtype),
                dbias.to(bias.dtype) if dbias is not None else None, None)


# ----------------------------------------------------------------------------
# 第 4 章：怎么接进 Trainer？
# ----------------------------------------------------------------------------
# HuggingFace 的 Trainer 负责「取数据 → 喂模型 → 算 loss → 反向 → 更新」，
# 其中「算 loss」这一步留了个后门：重写 compute_loss 就行。
# 常规流程是 model(...) 一次走完 backbone + lm_head（logits 就诞生在这里），
# 我们改成：只让模型算到 backbone 最后一层（hidden_states），
# 然后自己接分块 CE。完整 logits 表从头到尾不存在 → 内存墙消失。
# ----------------------------------------------------------------------------
class ChunkedCETrainer(Trainer):

    def __init__(self, chunk_size=256, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ce_chunk_size = chunk_size

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        labels = inputs.pop("labels")   # 把 labels 从输入里拿走（不能喂进前向）
        # model.model 是「裸 backbone」：HF 包装里，外层 model 挂着 model.lm_head，
        # 内层 model.model 只算 transformer 主体。return_dict=True 拿结构化输出，
        # .last_hidden_state 就是最后一层的隐藏状态
        hidden = model.model(**inputs, return_dict=True).last_hidden_state

        # ↓↓↓ 第一个大坑（第一版就在这翻车了）↓↓↓
        # 语言模型训练的是「下一 token 预测」：位置 t 的 hidden 要预测标签 t+1。
        # HF 原生在算 loss 前会做一次「错位」：logits 去掉最后一个位置、labels 去掉第一个位置。
        # 忘了错位会怎样？模型会变成「用位置 t 预测位置 t 自己的标签」——
        # 因为 hidden[t] 里就含着 input[t] 的残差信息，这种自预测分数虚高，
        # loss 看着比正常低一大截（实测 9.46 vs 原生 11.55），梯度也全错位。
        # 等价自检（第 5 章）存在的意义，就是上线前拦住这种错误。
        shift_hidden = hidden[..., :-1, :].contiguous()   # 去掉最后一个位置
        shift_labels = labels[..., 1:].contiguous()       # 去掉第一个位置
        # apply 是调用自定义 autograd.Function 的标准姿势
        loss = ChunkedCrossEntropy.apply(
            shift_hidden, shift_labels, model.lm_head.weight,
            getattr(model.lm_head, "bias", None), self.ce_chunk_size,
        )

        # ↓↓↓ 第三个大坑（前两个都修完后，上线训练又翻车了）↓↓↓
        # 分块 CE 返回的是「这一个 micro-batch 的平均 loss」= Σ_CE / n_tokens。
        # 但 transformers v5 的约定不一样：它会给原生 CE 传一个
        # num_items_in_batch，等于「整个梯度累积周期」的有效 token 数
        # （= n_tokens × grad_accum，比如 2047×4×8 = 65504），原生 CE 在
        # 模型内部按 Σ_CE / num_items 归一化，Trainer 上报时再乘回 gas。
        # 我们的分块 CE 少了这一步，loss 和梯度就整体偏了 gas 倍——
        # 上线首测 loss 25.6，而正确值是 3.2，恰好 8 倍（gas=8）。
        # 更早的冒烟阶梯其实早就暴露了规律：gas=32/16/8 三档，分块 loss
        # 恰好都是原生 loss 的 32/16/8 倍（127.0 vs 3.97 等），精确到小数。
        # 这种「精确整数倍」反过来也帮我们排除了「权重损坏」之类的猜测。
        # 修复：乘上 n_tokens / num_items_in_batch，把口径对齐原生。
        if num_items_in_batch is not None:
            n_tokens = (shift_labels != -100).sum()   # 本 micro-batch 的有效 token 数
            loss = loss * (n_tokens / num_items_in_batch)
            # 坑里还有坑：v5 默认 average_tokens_across_devices=True，双卡时
            # num_items 是「跨卡汇总」的（= 单卡数 × 卡数）。原生 compute_loss
            # 最后会乘 num_processes 抵消这个放大；我们 override 了 compute_loss，
            # 这一步必须自己补上——漏掉的话 loss/梯度整体偏 1/卡数 倍
            # （双卡首测 loss 1.58 = 3.17/2，恰好一半；单卡自检永远发现不了，
            # 只有双卡环境才暴露。教训：自检必须用和生产一样的卡数跑）
            if self.args.average_tokens_across_devices:
                loss_scale = self.accelerator.num_processes // self.get_tp_size()
                loss = loss * (loss_scale if self.args.n_gpu <= 1 else self.args.n_gpu)
        return (loss, None) if return_outputs else loss


# ----------------------------------------------------------------------------
# 第 5 章：怎么证明它没错？——上线前的等价自检
# ----------------------------------------------------------------------------
# 自建 loss 最大的风险是「你以为等价，其实算错了」。
# 防法是：同一批数据，用原生 CE 算一遍，再用分块 CE 算一遍，逐项比对：
#   |Δloss| < 2e-2         （loss 差小于 0.02）
#   |Δdw| 相对 < 5e-2      （lm_head 权重梯度差小于 5%）
# 两个都过 → CE_EQUIVALENCE_OK，换班脚本才敢用分块方案。
# ----------------------------------------------------------------------------
def check_equivalence(model_path, chunk_size=256, seed=20261024):
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

    with torch.no_grad():  # 第一阶段只比 loss，不开梯度（快）
        model = _load()
        bs, seq = 2, 128
        ids = torch.randint(0, 1024, (bs, seq), device=dev)
        labels = ids.clone()
        labels[:, seq // 2:] = -100  # 一半位置掩码，验证 -100 路径也正确
        # 原生参考：标准 lm_head 路径
        ref = model(**{"input_ids": ids, "labels": labels})
        loss_ref = ref.loss
        w_ref = model.lm_head.weight
        # 分块路径：backbone hidden → ChunkedCrossEntropy
        # （同样要做 next-token 错位，见第 4 章的坑；错位后两者才对得上）
        hidden = model.model(input_ids=ids).last_hidden_state
        loss_chunk = ChunkedCrossEntropy.apply(
            hidden[:, :-1], labels[:, 1:], w_ref,
            getattr(model.lm_head, "bias", None), chunk_size,
        )
        print(f"loss native={loss_ref.item():.6f}  chunked={loss_chunk.item():.6f}")

    # 第二阶段比梯度，必须开 grad 单独跑一遍（no_grad 下拿不到 .grad）
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


# 直接 python 运行本文件时，用训练机上的模型跑一遍自检（学习用）
if __name__ == "__main__":
    import sys
    sys.exit(0 if check_equivalence("models/Qwen3-0.6B") else 1)
