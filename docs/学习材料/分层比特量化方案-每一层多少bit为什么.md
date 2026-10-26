# 分层比特量化方案：每一层多少 bit、为什么（日常任务目的性版）

> 背景：Qwen3-0.6B（28 层、hidden 1024、词表 15.2 万、tied embedding），GGUF 经 llama.cpp 跑在手机端。用途是日常任务：中英翻译、会议记录整理、日程安排、消息代写、文本摘要（中文为主）。
> 本文档回答三个问题：每类张量给多少 bit？为什么？跟"日常生活"有什么关系？

## 零、先看我们已经实测的数据

| 量化 | 大小 | PPL | 速度（M5 Mac） | 备注 |
|---|---|---|---|---|
| Q8_0 | 805MB | 6.33 | 5422 t/s | 参考上限 |
| Q6_K | 623MB | 6.37 | 5306 t/s | |
| **Q5_K_M** | **551MB** | **6.42** | 5064 t/s | 质量/体积最优点 |
| LAYERED（自研分层 v1） | 567MB | 6.56 | **6808 t/s** | 速度最快，质量不占优 |
| LAYERED2（分层+imatrix IQ） | 523MB | 6.54 | — | 两头不沾 |
| Q4_K_M_emb8（embedding+输出层单独 q8_0） | 600MB | 6.79 | 6219 t/s | 只改两层 PPL 改善有限 |
| Q4_K_M | 484MB | 6.81 | 5177 t/s | 全 4-bit 基准 |
| **IQ4_XS**（imatrix 重要性校准） | **450MB** | 6.69 | 4702 t/s | 体积最优点 |

两个信号：①只把 embedding/输出层提到 8-bit 有效果但很小（−0.02 PPL）；②按"重要性"分配精度（imatrix 思路）比均匀 4-bit 好（IQ4_XS 更小还更好 0.12 PPL）。**但第三个信号更重要：我们自己按文献规律做的逐张量分层方案（v1/v2），没能打赢均匀 Q5_K_M。**原因见第六节。

## 一、为什么要分层：每层"犯错"的代价不一样

模型不是一块均匀的铁板，它有 28 层、每层好几类矩阵。量化 = 每个权重砍掉若干 bit 的精度，等于在每层引入一点"噪声"。问题是：**同样的噪声，落在不同地方，伤害差一个数量级。**

已发表的正式研究（不是预印本）给出的三条规律：

1. **首末层比中间层敏感（U 形曲线）**。输入层要把词转成向量，输出层要决定下一个词，两头错了全盘皆错（LLM-MQ，NeurIPS 2023 Workshop；HAWQ，CVPR 2020 在 CNN 上就发现了同样规律）。
2. **注意力比 FFN 敏感**。注意力决定"该看哪里"，FFN 是冗余度最高的大块参数（APTQ，DAC 2024；SqueezeLLM，ICML 2024）。
3. **激活异常值集中在特定维度**，主导量化误差，需要重点保护（LLM.int8()，NeurIPS 2022；AWQ，MLSys 2024 最佳论文；SpQR，ICLR 2024）。

再加一条和我们直接相关的：**中文对量化比英文更敏感**——自动指标掉 ~1.7% 看着不大，人工评估退化达 16%（Findings of EMNLP 2024）。以及：**模型越小越不耐量化**，0.6B 没有 70B 那种冗余（ZeroQuant-V2；LLaMA3 量化实证研究，Visual Intelligence 2024）。

## 二、llama.cpp 自己怎么分的（现成的工程经验）

llama.cpp 的 k-quants 系列（PR #1684）内部就是分层的，拿 Q4_K_M 举例：

| 张量 | k-quants 的默认处理 |
|---|---|
| token_embd | Q4_K（不升） |
| attn_q / attn_k | Q4_K（不升） |
| **attn_v** | **Q6_K**（首末 1/8 层 + 每隔 3 层） |
| attn_output | Q4_K |
| ffn_gate / ffn_up | Q4_K |
| **ffn_down** | **Q6_K**（同上的首末+间隔规则） |
| **output.weight** | **Q6_K** |

它的经验结论：**V 投影、FFN 的 down 投影、输出层最值得加 bit**——这三者对困惑度影响最大。我们可以在这个骨架上按文献规律做更细的调整。

## 三、我们的分层方案（每层多少 bit）

总原则：0.6B 冗余小，目标平均 4.5-5 bpw（约 430-460MB），比统一 Q4_K_M（484MB、4.5bpw 但分配不聪明）更聪明地花钱。

| 张量 | bit 档 | 为什么 |
|---|---|---|
| **token_embd**（词表层） | **Q6_K** | 词表 15.2 万，embedding 占全模型权重 ~26%；它的误差会注入每一层输入；中文 token 保真是命根子。k-quants 默认只给 Q4，对小模型+中文太激进 |
| **output.weight**（输出层，与 embedding 共享权重） | **Q6_K** | 逐 token 决定生成分布，翻译选词、摘要用词直接看它。llama.cpp 默认就升它 |
| **attn_v**（V 投影） | **Q6_K** | V 承载"要写出的内容"；llama.cpp 经验 + APTQ/LLM-MQ 的"注意力敏感"结论。V 很小（每层仅 13 万参数），升 bit 几乎不花体积 |
| **attn_q / attn_k** | **Q5_K_M** | 比 V 低一档（llama.cpp 不升 Q/K）；但我们的任务有长对话/长文，Q/K 管上下文检索，别压到 4-bit |
| **attn_output**（O 投影） | **Q5_K_M** | 层间信息传递的关口，SpQR 显示输出投影的列很敏感 |
| **ffn_gate / ffn_up** | **Q4_K_M** | 文献一致认为 FFN 冗余最高，是压缩的主要来源（这两块占参数大头） |
| **ffn_down** | **Q5_K_M** | FFN 的信息瓶颈，llama.cpp 显式升它 |
| **首末各 1/8 层（blk 0-3、24-27）整体** | **+1 档** | U 形敏感度（LLM-MQ/HAWQ），首末层全张量升一档 |
| **norm 层** | **F32 不量化** | 参数极少（每层几千个），量化它纯属找麻烦 |

预期：翻译/记录整理/消息代写/摘要这类生成任务接近无损（MobileQuant 在 0.5B 级模型上的结论一致），并显著优于统一 Q4_K_M——后者把中文 embedding 压到 4-bit 是主要风险点。

## 四、"日常任务"目的性：为什么这个分法贴合我们的生活场景

每个日常任务都有一个最怕出错的环节，分层方案就是给这些环节保精度：

- **翻译**：逐 token 选词决定忠实度 → 输出层 + embedding 高 bit（Q6_K）。
- **会议记录整理**：要准确抓人名、数字、事项 → token 保真（embedding 高 bit），不能把"35 块"记成"35 万"。
- **消息代写**：要稳定输出礼貌语体和格式（包括工具调用的 JSON 结构）→ 输出分布稳定（output 高 bit）。
- **长文摘要**：跨段落连贯、不丢要点 → 上下文检索（attn_q/k 不能太低）+ V 承载生成内容。⚠️ 文献明确警告：长文生成/对话是量化最敏感的任务（ICML 2024 量化评估研究），摘要要单独重点评测。

一句话版本：**日常任务的钱花在"词认得准、上下文记得住、句子写得顺"上；FFN 那些占体积大头的中间计算，砍到 4-bit 没人感觉得到。**

## 五、落地方式与风险

**落地**：llama-quantize（b11857）支持 `--tensor-type <张量名>=<类型>` 逐张量指定（选项必须在位置参数前），或用 `--tensor-type-file` 读映射表。Qwen3 GGUF 张量名：`token_embd.weight`、`output.weight`、`blk.N.attn_q.weight`、`attn_k`、`attn_v`、`attn_output`、`ffn_gate`、`ffn_up`、`ffn_down`、`attn_norm`、`ffn_norm`。写个小脚本生成 28 层映射表即可。

**两个进阶项**：
1. imatrix 校准 + IQ 系类型：我们实测 IQ4_XS（450MB）PPL 6.69，比 Q4_K_M 又小又好。分层方案可以叠 imatrix——用**中文校准集**跑重要性矩阵，再对 FFN 用 IQ4_XS。
2. 校准语料必须中文日常任务语料，别用英文默认集（EMNLP 2024 的教训）。

**风险清单**：
- 中文人工评估退化可能大于自动指标（PPL 会低估真实伤害）——必须跑生成评测，别只看 PPL；
- 长文摘要最易退化，单独设评测；
- 0.6B 容量本身有限，如果量化不是瓶颈（内存预算允许），别为了省 50MB 过度压缩。

## 六、我们实测后的结论：分层方案为什么没赢

我们按第三节的映射表实际量化了两版（v1=上表；v2=FFN 改用 imatrix 的 IQ4_XS、去掉边缘层升级，523MB/PPL 6.54），结论如下：

1. **均匀 Q5_K_M（551MB/PPL 6.42）打赢了我们所有的逐张量分层方案**。原因：k-quants 配方内部已经做了分层（attn_v/ffn_down/output 升 Q6_K、首末层升档），我们在此基础上再"微调"属于重复造轮子——把 embedding 提到 Q6_K 花了 20MB+ 却只换来可忽略的 PPL 改善（emb8 实验同样证明：embedding 升到 q8_0 只值 −0.02 PPL）。
2. **真正值得花钱的是 imatrix**：IQ4_XS 用重要性矩阵做非均匀量化，450MB 拿到 6.69，比它大 150MB 的 emb8 才 6.79。校准数据决定一切，一定要用中文日常语料校准（EMNLP 2024：中文对量化更敏感）。
3. **LAYERED v1 的唯一价值是速度**（6808 t/s，全场最快）——如果手机端热控吃紧、要最快的每字生成，v1 的混合形状对 Metal 更友好。但质量上它没有理由赢过 Q5_K_M。
4. **0.6B 的实际推荐**（按用途二选一）：
   - 内存预算 550MB 档 → **Q5_K_M**（质量最优、体积适中）；
   - 内存预算 450MB 档 → **IQ4_XS + 中文 imatrix**（体积最小且 PPL 优于 Q4_K_M）。
   - 分层逐张量方案：**不建议**，实测不占优。

换句话说：文献说的每一条规律（首末层敏感、注意力敏感、中文敏感、小模型不耐压）都是对的，但 llama.cpp 的 k-quants 已经把这几条规律内建进配方了。我们的分层实验证明：手工再叠一层分配，在 0.6B 这个体量上打不过"整体抬一档"（Q5_K_M）和"数据驱动的逐权重重要性"（imatrix）。这本身就是这次实验的目的性答案——**日常任务要的词保真和上下文连贯，k-quants 默认已保护；把省下来的钱换成整体精度，比手工挑层更划算。**

## 七、引用清单（正式发表文献）

| 文献 | 会议/期刊 |
|---|---|
| LLM.int8(): 8-bit Matrix Multiplication for Transformers at Scale | NeurIPS 2022 |
| GPTQ: Accurate Post-Training Quantization for Generative Pre-trained Transformers | ICLR 2023 |
| SpQR: A Sparse-Quantized Representation for Near-Lossless LLM Weight Compression | ICLR 2024 |
| AWQ: Activation-aware Weight Quantization for LLM Compression and Acceleration | MLSys 2024（最佳论文） |
| SqueezeLLM: Dense-and-Sparse Quantization | ICML 2024 |
| Any-Precision LLM: Low-Cost Deployment of Multiple, Diverse LLMs | ICML 2024（Oral） |
| APTQ: Attention-aware Post-Training Mixed-Precision Quantization | DAC 2024（CCF-A） |
| LLM-MQ: Mixed-precision Quantization for Efficient LLM Deployment | NeurIPS 2023 Workshop |
| Evaluating Quantized Large Language Models | ICML 2024 |
| A Comprehensive Evaluation of Quantization Strategies for Large Language Models | Findings of ACL 2024 |
| How Does Quantization Affect Multilingual LLMs? | Findings of EMNLP 2024 |
| MobileQuant: Mobile-friendly Quantization for On-device Language Models | Findings of EMNLP 2024 |
| MobileLLM: Optimizing Sub-billion Parameter Language Models for On-Device Use Cases | ICLR 2024 |
| HAWQ: Hessian AWare Quantization of Neural Networks | CVPR 2020 |
| An Empirical Study of LLaMA3 Quantization | Visual Intelligence (Springer) 2024 |
| An Empirical Study of Qwen3 Quantization | Visual Intelligence (Springer) 2026 |
| llama.cpp k-quants 设计（PR #1684）与 imatrix（PR #4773） | 工程实现依据 |

（仅预印本、未检索到正式发表，供参考不作依据：ZeroQuant-V2、LLM-QBench、Quantization and Machine Translation。）
