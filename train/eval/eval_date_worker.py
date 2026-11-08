#!/usr/bin/env python3
"""SFT20b 日期补训评测：60 题 held-out，判 start/end/remind 精确匹配。

用法：python3 eval_date_worker.py --model <gguf> --port 8124 --outdir <dir>
"""
import argparse
import json
import os
import re
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_FILE = os.path.join(ROOT, "train/eval/date_worker_eval.json")
TC_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
REL_RE = re.compile(r"明天|后天|今天|今晚|下周|本周|这周|周[一二三四五六日天]|月底|月初|当日|当天")


def chat(port, system, user, max_tokens=256):
    body = json.dumps({
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0, "max_tokens": max_tokens, "stream": False,
    }).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())["choices"][0]["message"].get("content") or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=8124)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--eval-file", default=EVAL_FILE)
    args = ap.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    cases = json.load(open(args.eval_file, encoding="utf-8"))
    emit = json_ok = schema = time_ok = title_ok = rel_leak = 0
    by_cat = {}
    lines = []
    for i, c in enumerate(cases, 1):
        system, user = c["messages"][0]["content"], c["messages"][1]["content"]
        expect = json.loads(TC_RE.search(c["expect"]).group(1))["arguments"]
        t0 = time.time()
        try:
            text = chat(args.port, system, user)
        except Exception as e:
            text = f"__ERROR__ {type(e).__name__}: {e}"
        calls = TC_RE.findall(text)
        got = None
        ok_json = ok_schema = False
        if calls:
            emit += 1
            try:
                obj = json.loads(calls[0])
                ok_json = True
                if isinstance(obj.get("name"), str) and isinstance(obj.get("arguments"), dict):
                    ok_schema = True
                    got = obj["arguments"]
            except Exception:
                pass
        json_ok += ok_json
        schema += ok_schema

        ok_time = ok_title = False
        leak = False
        if got:
            if "start_time" in expect:
                ok_time = (got.get("start_time") == expect["start_time"]
                           and got.get("end_time") == expect["end_time"])
                ok_title = got.get("title") == expect.get("title")
            else:
                ok_time = got.get("remind_time") == expect["remind_time"]
                ok_title = got.get("content") == expect.get("content")
            for k in ("start_time", "end_time", "remind_time"):
                if REL_RE.search(str(got.get(k, ""))):
                    leak = True
        time_ok += ok_time
        title_ok += ok_title
        rel_leak += leak

        cat = c["cat"]
        s = by_cat.setdefault(cat, {"n": 0, "time": 0})
        s["n"] += 1
        s["time"] += ok_time

        lines.append(f"[{i:02d}] {cat} emit={bool(calls)} json={ok_json} schema={ok_schema} "
                     f"time={ok_time} title={ok_title} {time.time()-t0:.1f}s")
        lines.append("  user: " + user)
        lines.append("  out : " + text.replace("\n", " | ")[:600])
        lines.append("  want: " + json.dumps(expect, ensure_ascii=False)[:300])
        with open(os.path.join(args.outdir, f"case_{i:02d}.txt"), "w", encoding="utf-8") as f:
            f.write(f"user: {user}\n\nout:\n{text}\n\nexpect: {json.dumps(expect, ensure_ascii=False)}\n")

    n = len(cases)
    summary = [
        f"model: {os.path.basename(args.model)}",
        f"total: {n}",
        f"emit: {emit}  emit_rate: {emit/n:.3f}",
        f"json_ok: {json_ok}  json_rate: {json_ok/n:.3f}",
        f"schema: {schema}  schema_rate: {schema/n:.3f}",
        f"time_exact: {time_ok}  time_rate: {time_ok/n:.3f}",
        f"title_ok: {title_ok}  title_rate: {title_ok/n:.3f}",
        f"relative_date_leaks: {rel_leak}",
    ]
    for cat, s in by_cat.items():
        summary.append(f"  {cat}: {s['time']}/{s['n']}")
    with open(os.path.join(args.outdir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n")
    with open(os.path.join(args.outdir, "detail.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
