#!/usr/bin/env python3
"""hf-mirror 免依赖下载器：纯 stdlib urllib，支持断点续传（不依赖 huggingface_hub）。

用法：
  dl_mirror.py model   Qwen/Qwen3-0.6B       <outdir> "<include glob>" "<exclude glob>"
  dl_mirror.py dataset HuggingFaceFW/fineweb-2 <outdir> "data/cmn_Hani/train/000_0000?.parquet" ""
"""
import fnmatch
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

MIRROR = "https://hf-mirror.com"


def api_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dl-mirror"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def fetch(url, dest, retries=6):
    tmp = dest + ".part"
    for i in range(retries):
        have = os.path.getsize(tmp) if os.path.exists(tmp) else 0
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "dl-mirror"})
            if have:
                req.add_header("Range", f"bytes={have}-")
            with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "ab") as f:
                if r.status == 200:
                    f.seek(0)
                    f.truncate()
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, dest)
            return dest
        except Exception as e:
            print(f"  retry {i + 1}: {e}", flush=True)
            time.sleep(5 * (i + 1))
    raise SystemExit(f"下载失败: {url}")


def main():
    kind, repo, outdir, include, exclude = sys.argv[1:6]
    api = f"{MIRROR}/api/{'models' if kind == 'model' else 'datasets'}/{repo}?blobs=true"
    d = api_json(api)
    inc = [p for p in include.split(",") if p] or None
    exc = [p for p in exclude.split(",") if p] or None
    files = []
    for s in d.get("siblings", []):
        name = s["rfilename"]
        if inc and not any(fnmatch.fnmatch(name, p) for p in inc):
            continue
        if exc and any(fnmatch.fnmatch(name, p) for p in exc):
            continue
        files.append((name, (s.get("lfs") or {}).get("size") or 0))
    print(f"files: {len(files)}", flush=True)

    def dl_one(item):
        name, expect = item
        dest = os.path.join(outdir, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return f"skip {name}"
        # 镜像约定：数据集文件在 /datasets/<repo>/resolve/...，模型在 /<repo>/resolve/...
        base = f"{MIRROR}/datasets/{repo}" if kind == "dataset" else f"{MIRROR}/{repo}"
        url = f"{base}/resolve/main/{urllib.parse.quote(name, safe='/')}"
        fetch(url, dest)
        size = os.path.getsize(dest)
        if expect and size != expect:
            return f"WARN {name} size {size} != expect {expect}"
        return f"ok {name} {size / 1e6:.1f}MB"

    with ThreadPoolExecutor(max_workers=6) as ex:
        for msg in ex.map(dl_one, files):
            print(msg, flush=True)
    print("ALL_DONE")


if __name__ == "__main__":
    main()
