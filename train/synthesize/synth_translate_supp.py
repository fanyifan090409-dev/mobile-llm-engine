#!/usr/bin/env python3
"""翻译类补充合成：teacher 批量生成中英互译例句，拆成独立样本追加进 data/sft/translate.jsonl。

背景：首轮 10M 合成里 translate 只有 3481 条（约 1.6% tokens，计划占比 25%）——翻译样本短
（约 30 tokens/条）+ 种子池小（48 句）导致大量去重跳过。本脚本改走「一次调用生成 5 组新例句、
每组双向拆 2 条样本」，绕过种子池瓶颈，teacher 自己造语料。

用法：
  python3 synth_translate_supp.py --target-samples 80000 --outdir data/sft
"""
import argparse
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from synthesize_sft import ENDPOINTS, chat, content_of

BATCH_PROMPT = (
    "请生成5组手机用户场景的中文句子及其地道英文翻译。场景尽量多样（日常对话、旅行购物、"
    "工作沟通、生活事务、点餐问路等），句子口语化自然，每句10到50字。每组两行，格式固定：\n"
    "中：<中文句子>\n英：<英文翻译>\n只输出这10行，不要编号、不要任何其他说明。"
)


def is_valid(zh, en):
    if not zh or not en or zh.strip() == en.strip():
        return False
    if not re.search(r"[\u4e00-\u9fff]", zh):  # 中文侧必须含汉字
        return False
    if re.search(r"[\u4e00-\u9fff]", en):      # 英文侧不能是中文
        return False
    if len(zh) > 60 or len(en) > 220:
        return False
    return True


def gen_batch(endpoint, model):
    """一次调用 → 最多 10 条样本（5 组 × 双向），返回 (样本列表, usage tokens)。"""
    resp = chat(endpoint, model, [{"role": "user", "content": BATCH_PROMPT}], max_tokens=1024)
    tks = resp.get("usage", {}).get("total_tokens", 0)
    out = content_of(resp)
    pairs, zh = [], None
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"^[\d\s\.、\-]*中(文)?[：:]\s*(.+)$", line)
        if m:
            zh = m.group(2).strip()
            # 容忍「中：你好 英：Hello」写在同一行的输出
            sp = re.split(r"英(文)?[：:]", zh, maxsplit=1)
            if len(sp) == 3:
                pairs.append((sp[0].strip(), sp[2].strip()))
                zh = None
            continue
        m = re.match(r"^[\d\s\.、\-]*英(文)?[：:]\s*(.+)$", line)
        if m and zh:
            en = m.group(2).strip()
            if is_valid(zh, en):
                pairs.append((zh, en))
            zh = None
    samples = []
    for zh, en in pairs:
        if not is_valid(zh, en):
            continue
        samples.append({"messages": [
            {"role": "user", "content": f"把这句话翻译成英文：{zh}"},
            {"role": "assistant", "content": en}]})
        samples.append({"messages": [
            {"role": "user", "content": f"把这句话翻译成中文：{en}"},
            {"role": "assistant", "content": zh}]})
    return samples, tks


def run_task(idx):
    endpoint, model = ENDPOINTS[idx % len(ENDPOINTS)]
    try:
        return gen_batch(endpoint, model)
    except Exception:
        return [], 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-samples", type=int, default=80000)
    ap.add_argument("--outdir", default="data/sft")
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    out_path = os.path.join(args.outdir, "translate.jsonl")

    seen = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["hash"])
                except Exception:
                    pass

    f_out = open(out_path, "a", encoding="utf-8")
    total_samples = total_tokens = est_tokens = dup_skip = 0
    started = time.time()
    last_log = -1

    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(run_task, i): i for i in range(16)}
        idx = 16
        while futs and total_samples < args.target_samples:
            for fut in as_completed(futs):
                futs.pop(fut)
                samples, tks = fut.result()
                total_tokens += tks
                for s in samples:
                    h = hashlib.sha256(json.dumps(s["messages"], ensure_ascii=False,
                                                   sort_keys=True).encode()).hexdigest()[:16]
                    if h in seen:
                        dup_skip += 1
                        continue
                    seen.add(h)
                    s["hash"] = h
                    s["category"] = "translate"
                    f_out.write(json.dumps(s, ensure_ascii=False) + "\n")
                    # 粗略估算数据集 tokens：中英混合约 1.6 字符/token
                    est_tokens += (len(s["messages"][0]["content"]) +
                                   len(s["messages"][1]["content"])) / 1.6
                    total_samples += 1
                if total_samples >= args.target_samples:
                    break
                futs[ex.submit(run_task, idx)] = idx
                idx += 1
                hundred = total_samples // 100
                if hundred != last_log:
                    last_log = hundred
                    el = max(time.time() - started, 1)
                    print(f"[{time.strftime('%H:%M:%S')}] 补充样本 {total_samples}/{args.target_samples} | "
                          f"usage {total_tokens/1e6:.2f}M | est数据 {est_tokens/1e6:.2f}M | "
                          f"速率 {total_tokens/el:.0f} tok/s | 去重跳过 {dup_skip}", flush=True)
        for f in futs:
            f.cancel()

    f_out.close()
    meta = {"supp_samples": total_samples, "usage_tokens": total_tokens,
            "est_dataset_tokens": round(est_tokens), "dup_skipped": dup_skip,
            "elapsed_s": round(time.time() - started)}
    with open(os.path.join(args.outdir, "meta_translate_supp.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
