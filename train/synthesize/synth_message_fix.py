#!/usr/bin/env python3
"""消息类修正合成：teacher 在合成期 system 提示下直接输出单条消息草稿，追加进 data/sft/message.jsonl。

背景：首轮 5,088 条 message 样本中 30%（1,542 条）是「给你几个选项」式回答，与「帮我写一条
XX 消息」的意图不符，会让模型学会输出多选项模板。本脚本强制单条草稿，只收合格样本。
原有坏样本不动，训练拼装时按同样规则过滤。

用法：
  python3 synth_message_fix.py --target-samples 9000 --outdir data/sft
"""
import argparse
import hashlib
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from synthesize_sft import ENDPOINTS, chat, content_of, MSG_SCENARIOS, TONES

# 合成期专用 system 提示：只约束生成格式，不写入数据集
SYNTH_SYS_MSG = (
    "你是手机助手。用户要求写一条消息时，直接输出这条消息的完整正文，"
    "不要给多个选项、不要加解释、不要用 markdown 标题或加粗，只输出消息本身。"
)
BAD_PATTERNS = ["选项", "以下几种", "供你选择", "###", "**", "1.", "2.", "3."]


def is_valid(content):
    if not content or len(content) < 8 or len(content) > 300:
        return False
    if content.startswith("这里"):
        return False
    if any(p in content for p in BAD_PATTERNS):
        return False
    return True


def build_user(rng):
    mtype, context = rng.choice(MSG_SCENARIOS)
    tone = rng.choice(TONES)
    return f"帮我写一条{mtype}消息：{context}。语气{tone}。"


def run_task(idx, rng):
    endpoint, model = ENDPOINTS[idx % len(ENDPOINTS)]
    user = build_user(rng)
    try:
        resp = chat(endpoint, model, [
            {"role": "system", "content": SYNTH_SYS_MSG},
            {"role": "user", "content": user},
        ], max_tokens=512)
        tks = resp.get("usage", {}).get("total_tokens", 0)
        out = content_of(resp)
        if not is_valid(out):
            return [], tks
        return [{"messages": [{"role": "user", "content": user},
                              {"role": "assistant", "content": out}]}], tks
    except Exception:
        return [], 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-samples", type=int, default=9000)
    ap.add_argument("--outdir", default="data/sft")
    ap.add_argument("--seed", type=int, default=20261024)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    out_path = os.path.join(args.outdir, "message.jsonl")

    seen = set()
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line)["hash"])
                except Exception:
                    pass

    rng = random.Random(args.seed)
    f_out = open(out_path, "a", encoding="utf-8")
    total_samples = total_tokens = est_tokens = drop_bad = 0
    started = time.time()
    last_log = -1

    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = {ex.submit(run_task, i, rng): i for i in range(16)}
        idx = 16
        while futs and total_samples < args.target_samples:
            for fut in as_completed(futs):
                futs.pop(fut)
                samples, tks = fut.result()
                total_tokens += tks
                if not samples:
                    drop_bad += 1
                for s in samples:
                    h = hashlib.sha256(json.dumps(s["messages"], ensure_ascii=False,
                                                   sort_keys=True).encode()).hexdigest()[:16]
                    if h in seen:
                        drop_bad += 1
                        continue
                    seen.add(h)
                    s["hash"] = h
                    s["category"] = "message"
                    f_out.write(json.dumps(s, ensure_ascii=False) + "\n")
                    est_tokens += (len(s["messages"][0]["content"]) +
                                   len(s["messages"][1]["content"])) / 1.6
                    total_samples += 1
                if total_samples >= args.target_samples:
                    break
                futs[ex.submit(run_task, idx, rng)] = idx
                idx += 1
                hundred = total_samples // 100
                if hundred != last_log:
                    last_log = hundred
                    el = max(time.time() - started, 1)
                    print(f"[{time.strftime('%H:%M:%S')}] 修正样本 {total_samples}/{args.target_samples} | "
                          f"usage {total_tokens/1e6:.2f}M | est数据 {est_tokens/1e6:.2f}M | "
                          f"速率 {total_tokens/el:.0f} tok/s | 丢弃 {drop_bad}", flush=True)
        for f in futs:
            f.cancel()

    f_out.close()
    meta = {"msg_samples": total_samples, "usage_tokens": total_tokens,
            "est_dataset_tokens": round(est_tokens), "dropped": drop_bad,
            "elapsed_s": round(time.time() - started)}
    with open(os.path.join(args.outdir, "meta_message_fix.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
