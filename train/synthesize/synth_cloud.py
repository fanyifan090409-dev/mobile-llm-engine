#!/usr/bin/env python3
"""云端 teacher 合成适配器（Pro 机官方 CodeBuddy CLI）：复用 synthesize_academic.py 的
任务构建与标记块校验（含雅思亚洲考生低 AI 风格契约），把 chat() 换成 CLI 子进程调用。

产物与训练机 teacher 输出同契约（messages/category/form/hash，hash 算法一致），
合并时按 hash 去重。云端只做 gen 类（出题/雅思材料），solve 两轮调用留给训练机 teacher。

用法：python3 synth_cloud.py --target-samples 300 --outdir cloud_sft18
"""
import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import synthesize_academic as SA

CLI = os.path.expanduser("~/.codebuddy/bin/codebuddy")
TIMEOUT = 600


def chat_cloud(user_text):
    """官方 CLI 单次补全，返回文本；失败/空返回 ''。"""
    for attempt in range(3):
        try:
            r = subprocess.run([CLI, "-p", user_text], capture_output=True,
                               text=True, timeout=TIMEOUT)
            if r.returncode == 0 and r.stdout.strip():
                out = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", r.stdout.strip()).strip()
                return out
        except Exception:
            pass
        time.sleep(10)
    return ""


def clean_out(out, form):
    """部分模型在正文前加客套前缀，切到第一个标记块。"""
    markers = SA.GEN_MARKERS.get(form, [])
    if markers:
        first = min((out.find(m) for m in markers if m in out), default=-1)
        if first > 0:
            out = out[first:]
    return out.strip()


def run_task(rng):
    c = SA.pick_category(rng)
    spec = SA.build_spec(rng, c)
    if spec["kind"] == "solve":  # 云端只做 gen 类
        spec = SA.build_ap_problem_gen(rng, c)
    out = chat_cloud(spec["messages"][0]["content"])
    if not out:
        return [], 0
    out = clean_out(out, spec["form"])
    if not SA.validate_gen(spec["form"], out):
        return [], 0
    return [{"messages": spec["messages"] + [{"role": "assistant", "content": out}],
             "category": c, "form": spec["form"]}], len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-samples", type=int, default=300)
    ap.add_argument("--outdir", default="cloud_sft18")
    ap.add_argument("--seed", type=int, default=20261102)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    os.makedirs(args.outdir, exist_ok=True)
    files = {c: open(os.path.join(args.outdir, f"{c}.jsonl"), "a", encoding="utf-8")
             for c in SA.SHARE}
    seen = set()
    for c in SA.SHARE:
        p = os.path.join(args.outdir, f"{c}.jsonl")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    try:
                        seen.add(json.loads(line)["hash"])
                    except Exception:
                        pass
    n = 0
    started = time.time()
    last_log = started
    while n < args.target_samples:
        samples, _ = run_task(rng)
        for s in samples:
            h = hashlib.sha256(json.dumps(s["messages"], ensure_ascii=False,
                                          sort_keys=True).encode()).hexdigest()[:16]
            if h in seen:
                continue
            seen.add(h)
            s["hash"] = h
            files[s["category"]].write(json.dumps(s, ensure_ascii=False) + "\n")
            files[s["category"]].flush()
            n += 1
        if time.time() - last_log > 300:
            last_log = time.time()
            el = time.time() - started
            print(f"[{time.strftime('%H:%M:%S')}] 样本 {n}/{args.target_samples} | "
                  f"速率 {n / el * 60:.1f} 样本/分", flush=True)
    for f in files.values():
        f.close()
    print(f"完成：{n} 样本 → {args.outdir}/")


if __name__ == "__main__":
    main()
