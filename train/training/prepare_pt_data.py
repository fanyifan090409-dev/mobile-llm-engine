#!/usr/bin/env python3
"""续训语料预处理：原始文本 → tokenize + 打包 → uint32 二进制（多进程流式，内存恒定）。

打包策略：文档 token 流用 eos 分隔后切成 seq_len 窗口（跨文档续接，浪费 <1%）。

用法：
  python3 prepare_pt_data.py --tokenizer models/Qwen3-0.6B \
      --files "data/pt_raw/fineweb2_cmn/data/cmn_Hani/train/*.parquet" \
      --text-key text --max-tokens 1950000000 --out data/pt/fw2.bin --workers 24
  python3 prepare_pt_data.py --tokenizer models/Qwen3-0.6B \
      --files "data/pt_raw/belle/train_3.5M_CN.json" \
      --json-keys instruction,input,output --max-tokens 250000000 \
      --out data/pt/belle.bin --workers 24
"""
import argparse
import glob
import json
import os
import sys
from array import array
from multiprocessing import Pool

TOK = None


def _init(tokenizer_path):
    global TOK
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    from transformers import AutoTokenizer
    TOK = AutoTokenizer.from_pretrained(tokenizer_path)


def _iter_texts(fn, text_key, json_keys, rg, nsplit, wid):
    """按来源类型产出文本：parquet 走指定 row group，jsonl 按行号对 nsplit 取模分片。"""
    import pyarrow.parquet as pq
    if fn.endswith(".parquet"):
        pf = pq.ParquetFile(fn)
        for i in [rg] if rg >= 0 else range(pf.num_row_groups):
            col = pf.read_row_group(i, columns=[text_key]).column(text_key).to_pylist()
            for x in col:
                if isinstance(x, str) and len(x) >= 50:
                    yield x
    else:
        with open(fn, encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if nsplit > 1 and idx % nsplit != wid:
                    continue
                line = line.strip()
                if not line:
                    continue
                # BELLE 等为 JSON 数组格式（行尾逗号），rstrip 后兼容数组与 jsonl 两种
                line = line.rstrip(",")
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if isinstance(d, dict) and json_keys and all(k in d for k in json_keys):
                    parts = [str(d.get(k) or "").strip() for k in json_keys]
                    t = " ".join(p for p in parts if p)
                elif isinstance(d, dict) and "conversations" in d:
                    # BELLE 等对话格式：{conversations: [{from, value}, ...]}，拼接全部发言
                    t = " ".join(
                        str(c.get("value") or "").strip()
                        for c in d["conversations"]
                        if isinstance(c, dict) and c.get("value")
                    )
                else:
                    t = ""
                if len(t) >= 20:
                    yield t


def _process(args):
    fn, text_key, json_keys, seq_len, eos, rg, nsplit, wid, tmp = args
    carry = []
    written = 0
    with open(tmp, "wb") as f:
        batch = []
        for t in _iter_texts(fn, text_key, json_keys, rg, nsplit, wid):
            batch.append(t)
            if len(batch) >= 256:
                for ids in TOK(batch, add_special_tokens=False)["input_ids"]:
                    if not ids:
                        continue
                    carry.extend(ids)
                    carry.append(eos)
                    while len(carry) >= seq_len:
                        f.write(array("I", carry[:seq_len]).tobytes())
                        written += seq_len
                        del carry[:seq_len]
                batch = []
        if batch:
            for ids in TOK(batch, add_special_tokens=False)["input_ids"]:
                if not ids:
                    continue
                carry.extend(ids)
                carry.append(eos)
                while len(carry) >= seq_len:
                    f.write(array("I", carry[:seq_len]).tobytes())
                    written += seq_len
                    del carry[:seq_len]
    return written, tmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--files", required=True, help="glob 模式")
    ap.add_argument("--text-key", default=None, help="parquet 文本列名")
    ap.add_argument("--json-keys", default=None, help="jsonl 拼接字段，逗号分隔")
    ap.add_argument("--seq-len", type=int, default=4096)
    ap.add_argument("--max-tokens", type=int, default=None, help="token 预算，超出截断")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    files = sorted(glob.glob(args.files))
    if not files:
        sys.exit("没有匹配文件: " + args.files)
    json_keys = [k for k in (args.json_keys or "").split(",") if k]
    text_key = args.text_key or "text"

    from transformers import AutoTokenizer
    eos = AutoTokenizer.from_pretrained(args.tokenizer).eos_token_id

    import pyarrow.parquet as pq
    jobs = []
    for fn in files:
        if fn.endswith(".parquet"):
            for rg in range(pq.ParquetFile(fn).num_row_groups):
                jobs.append((fn, text_key, json_keys, args.seq_len, eos, rg, 1, 0, f"{args.out}.part{len(jobs)}"))
        else:
            nsplit = max(1, args.workers)
            for wid in range(nsplit):
                jobs.append((fn, text_key, json_keys, args.seq_len, eos, -1, nsplit, wid, f"{args.out}.part{len(jobs)}"))

    budget = args.max_tokens * 4 if args.max_tokens else None
    written = 0
    tmps = [j[-1] for j in jobs]
    with Pool(args.workers, initializer=_init, initargs=(args.tokenizer,)) as pool:
        for n, tmp in pool.imap_unordered(_process, jobs):
            with open(tmp, "rb") as ft:
                while True:
                    chunk = ft.read(1 << 26)
                    if not chunk:
                        break
                    if budget and written >= budget:
                        break
                    if budget:
                        chunk = chunk[:budget - written]
                    with open(args.out, "ab") as fout:
                        fout.write(chunk)
                    written += len(chunk)
            os.remove(tmp)
            print(f"merged {os.path.basename(tmp)} +{n} tokens, 累计 {written // 4 / 1e9:.2f}B", flush=True)
            if budget and written >= budget:
                pool.terminate()
                break
    for tmp in tmps:
        if os.path.exists(tmp):
            os.remove(tmp)

    final = (written // 4 // args.seq_len) * args.seq_len  # 对齐到整窗口
    os.truncate(args.out, final * 4)
    with open(args.out + ".meta.json", "w", encoding="utf-8") as f:
        json.dump({"tokens": final, "seq_len": args.seq_len, "eos": eos}, f, ensure_ascii=False)
    print(f"DONE {args.out}: {final / 1e9:.2f}B tokens ({final} 个)")


if __name__ == "__main__":
    main()
