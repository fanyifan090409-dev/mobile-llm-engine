#!/usr/bin/env python3
"""AIY PPT 重构版专用半页图（C1-C4）。

与原 F 系列的区别：不带图内大标题/结论条（页面统一提供），只保留坐标、数值和
最小图例，便于嵌进高密度页面。画布固定，禁止 tight bbox。
用法：.venv/bin/python docs/aiy27/figures/gen_deck_charts.py
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

HERE = os.path.dirname(os.path.abspath(__file__))

_FONT = None
for _p in ("/System/Library/Fonts/PingFang.ttc",
           "/System/Library/Fonts/Hiragino Sans GB.ttc",
           "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"):
    if os.path.exists(_p):
        try:
            fm.fontManager.addfont(_p)
            _FONT = fm.FontProperties(fname=_p).get_name()
            break
        except Exception:
            continue
if _FONT:
    plt.rcParams["font.sans-serif"] = [_FONT, "Helvetica Neue", "DejaVu Sans"]

BLUE = "#0A84FF"
GREEN = "#30D158"
ORANGE = "#FF9F0A"
RED = "#FF3B30"
DARK = "#1D1D1F"
MID = "#6E6E73"
LIGHT = "#AEAEB2"
GRID = "#E5E5EA"
BLUE_L = "#9CCBFF"
GRAY_L = "#C7C7CC"

plt.rcParams.update({
    "axes.edgecolor": GRID,
    "axes.linewidth": 0.8,
    "axes.labelcolor": MID,
    "xtick.color": MID,
    "ytick.color": MID,
    "font.size": 9.5,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
})


def save(fig, name):
    path = os.path.join(HERE, name)
    fig.savefig(path, dpi=200, facecolor="white")
    plt.close(fig)
    print("saved", path)


def strip(ax, keep_left=False):
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)


# ---------------- C1 工具调用 40 题
fig, ax = plt.subplots(figsize=(7.2, 3.6))
groups = ["0.6B 基线", "1.7B Q8_0", "1.7B Q5_K_M", "1.7B Q4_K_M"]
emit = [100, 97.5, 90, 97.5]
schema = [100, 95, 90, 95]
y = list(range(len(groups)))
h = 0.34
bars1 = ax.barh([i + h / 2 for i in y], emit, height=h, color=BLUE_L, label="发射率")
bars2 = ax.barh([i - h / 2 for i in y], schema, height=h, color=BLUE, label="schema 通过率")
for bars in (bars1, bars2):
    for b in bars:
        w = b.get_width()
        ax.text(w + 1.5, b.get_y() + b.get_height() / 2, f"{w:g}%",
                va="center", ha="left", fontsize=9, color=DARK)
ax.set_yticks(y, groups, fontsize=10)
ax.set_xlim(0, 112)
ax.set_xticks([0, 25, 50, 75, 100], ["0", "25%", "50%", "75%", "100%"])
strip(ax)
ax.legend(loc="lower right", frameon=False, ncol=2, fontsize=9,
          bbox_to_anchor=(1.0, 1.0))
fig.tight_layout(pad=0.4)
save(fig, "C1-工具调用.png")

# ---------------- C2 幻觉率（日期题）
fig, ax = plt.subplots(figsize=(5.6, 3.2))
cats = ["总体 (n=15)", "相对日期 (n=9)", "绝对日期 (n=6)"]
before = [0, 0, 0]
after = [60, 78, 33]
x = range(len(cats))
b1 = ax.bar([i - 0.18 for i in x], before, width=0.34, color=GRAY_L, label="无今天锚点")
b2 = ax.bar([i + 0.18 for i in x], after, width=0.34, color=BLUE, label="有今天锚点")
for bars, vals, suffix in ((b1, before, "%"), (b2, after, "%")):
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v}{suffix}",
                ha="center", va="bottom", fontsize=9.5, color=DARK,
                fontweight="bold" if v else "normal")
ax.set_xticks(list(x), cats, fontsize=9.5)
ax.set_ylim(0, 95)
ax.set_yticks([0, 25, 50, 75], ["0", "25%", "50%", "75%"])
strip(ax)
ax.grid(axis="x", visible=False)
ax.grid(axis="y", color=GRID, linewidth=0.7)
ax.legend(loc="upper right", frameon=False, fontsize=8.5)
fig.tight_layout(pad=0.4)
save(fig, "C2-幻觉率.png")

# ---------------- C3 真机跑分跨代对比
fig, ax = plt.subplots(figsize=(7.4, 3.9))
groups = ["1.7B Q4_K_M", "1.7B Q5_K_M", "1.7B Q8_0",
          "0.6B Q5_K_M", "0.6B Q4_K_M", "0.6B IQ4_XS"]
i17 = [38.5, 34.2, 27.3, 86.9, 89.0, 96.7]
i18 = [61.1, 56.5, 40.1, 100.5, 119.7, 121.1]
y = list(range(len(groups)))
h = 0.34
b17 = ax.barh([i + h / 2 for i in y], i17, height=h, color=GRAY_L, label="iPhone 17 Pro Max")
b18 = ax.barh([i - h / 2 for i in y], i18, height=h, color=BLUE, label="iPhone 18 Pro Max")
for bars in (b17, b18):
    for b in bars:
        w = b.get_width()
        ax.text(w + 1.5, b.get_y() + b.get_height() / 2, f"{w:.1f}",
                va="center", ha="left", fontsize=8.8, color=DARK)
ax.set_yticks(y, groups, fontsize=9.5)
ax.set_xlim(0, 145)
ax.set_xticks([0, 30, 60, 90, 120], ["0", "30", "60", "90", "120"])
ax.set_xlabel("稳定解码 tok/s（4 轮取后 3 轮均值，4K 上下文）", fontsize=9)
strip(ax)
ax.legend(loc="lower right", frameon=False, fontsize=8.8,
          bbox_to_anchor=(1.0, 1.0), ncol=2)
fig.tight_layout(pad=0.4)
save(fig, "C3-设备跑分.png")

# ---------------- C4 SFT17 训练曲线
data = json.load(open(os.path.join(HERE, "data", "sft17_training.json")))
train = data["train"]
evals = data["eval"]
fig, ax = plt.subplots(figsize=(5.2, 2.3))
ax.plot([p[0] for p in train], [p[1] for p in train],
        color=BLUE, linewidth=1.6, label="训练 loss")
ax.plot([p[0] for p in evals], [p[1] for p in evals],
        color=ORANGE, linewidth=1.8, marker="o", markersize=4, label="验证 loss")
ax.set_xlabel("训练步数（2 epochs · 2764 步）", fontsize=8.8)
ax.set_ylabel("loss", fontsize=8.8)
strip(ax)
ax.grid(axis="y", color=GRID, linewidth=0.7)
ax.legend(loc="upper right", frameon=False, fontsize=8.5)
fig.tight_layout(pad=0.35)
save(fig, "C4-训练曲线.png")
