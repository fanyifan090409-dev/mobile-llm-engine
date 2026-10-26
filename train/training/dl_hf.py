#!/usr/bin/env python3
"""hf-mirror 下载器：snapshot_download 的薄封装（不依赖 huggingface-cli 入口脚本）。

用法：dl_hf.py <repo_id> <repo_type> <local_dir> <include逗号分隔或空> <exclude逗号分隔或空>
"""
import sys
from huggingface_hub import snapshot_download

repo, rtype, local_dir = sys.argv[1], sys.argv[2], sys.argv[3]
include = [p for p in sys.argv[4].split(",") if p] or None
exclude = [p for p in sys.argv[5].split(",") if p] or None
snapshot_download(
    repo_id=repo, repo_type=rtype, local_dir=local_dir,
    allow_patterns=include, ignore_patterns=exclude,
)
print("DL_DONE", repo)
