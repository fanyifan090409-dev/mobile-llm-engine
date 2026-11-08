#!/usr/bin/env python3
"""AIY PPT v4 图表：编辑式留白、透明底、信号橙 + 墨黑。"""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

HERE = os.path.dirname(os.path.abspath(__file__))
_FONT = None
for _p in ("/System/Library/Fonts/PingFang.ttc",
           "/System/Library/Fonts/Hiragino Sans GB.ttc"):
    if os.path.exists(_p):
        try:
            fm.fontManager.addfont(_p)
            _FONT = fm.FontProperties(fname=_p).get_name()
            break
        except Exception:
            pass
if _FONT:
    plt.rcParams["font.sans-serif"] = [_FONT, "Helvetica Neue", "DejaVu Sans"]

INK = "#111112"
MUTED = "#6B675E"
HAIR = "#D8D2C4"
ORANGE = "#FF4D00"
BLUE = "#1F5EFF"
GRAY = "#C9C3B5"
PAPER = "#F4F1E9"

plt.rcParams.update({
    "axes.edgecolor": HAIR, "axes.linewidth": 0.8,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "font.size": 9.5, "figure.facecolor": "none", "axes.facecolor": "none",
    "savefig.facecolor": "none",
})

def save(fig, name):
    path = os.path.join(HERE, name)
    fig.savefig(path, dpi=220, transparent=True)
    plt.close(fig)
    print("saved", path)

def strip(ax):
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)

# C1 工具调用
fig, ax = plt.subplots(figsize=(7.0, 3.45))
groups = ["1.7B Q4_K_M", "1.7B Q5_K_M", "1.7B Q8_0", "0.6B 基线"]
emit = [97.5, 90, 97.5, 100]
schema = [95, 90, 95, 100]
y = list(range(len(groups)))
h = 0.32
b1 = ax.barh([i + h/2 for i in y], emit, height=h, color=GRAY, label="发射率")
b2 = ax.barh([i - h/2 for i in y], schema, height=h, color=ORANGE, label="schema 通过率")
for bars in (b1, b2):
    for b in bars:
        w = b.get_width()
        ax.text(w + 1.3, b.get_y() + b.get_height()/2, f"{w:g}%",
                va="center", ha="left", fontsize=9.5, color=INK, fontweight="bold")
ax.set_yticks(y, groups, fontsize=10, color=INK)
ax.set_xlim(0, 112)
ax.set_xticks([0, 25, 50, 75, 100], ["0", "25", "50", "75", "100%"])
strip(ax)
ax.grid(axis="x", color=HAIR, linewidth=0.7)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.13), frameon=False,
          ncol=2, fontsize=9)
fig.tight_layout(pad=0.3)
save(fig, "V1-工具调用.png")

# C2 幻觉/瞎编
fig, ax = plt.subplots(figsize=(5.4, 3.0))
cats = ["总体 15 题", "相对日期 9 题", "绝对日期 6 题"]
before = [0, 0, 0]
after = [60, 78, 33]
x = range(len(cats))
b1 = ax.bar([i - 0.17 for i in x], before, width=0.32, color=GRAY, label="改前")
b2 = ax.bar([i + 0.17 for i in x], after, width=0.32, color=ORANGE, label="改后")
for bars, vals in ((b1, before), (b2, after)):
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v + 2, f"{v}%",
                ha="center", va="bottom", fontsize=10,
                color=INK, fontweight="bold")
ax.set_xticks(list(x), cats, fontsize=9.5, color=INK)
ax.set_ylim(0, 95)
ax.set_yticks([0, 25, 50, 75], ["0", "25", "50", "75%"])
strip(ax)
ax.grid(axis="y", color=HAIR, linewidth=0.7)
ax.legend(loc="upper right", frameon=False, fontsize=8.5)
fig.tight_layout(pad=0.3)
save(fig, "V2-瞎编率.png")

# C5 LR 消融
d = json.load(open(os.path.join(HERE, "data", "lr_ablation.json")))
fig, ax = plt.subplots(figsize=(7.2, 2.15))
cx = [p[0] for p in d["constant"]]; cy = [p[1] for p in d["constant"]]
wx = [p[0] for p in d["wsd"]]; wy = [p[1] for p in d["wsd"]]
wsd_done = d.get("wsd_steps", wx[-1]) >= 1000
if not wsd_done:
    ax.axvspan(0, wx[-1], color=ORANGE, alpha=0.07, linewidth=0)
ax.plot(cx, cy, color=BLUE, linewidth=1.9, label="constant 1000 步")
ax.plot(wx, wy, color=ORANGE, linewidth=2.2,
        label="WSD 1000 步" if wsd_done else "WSD（进行中）")
ax.scatter([wx[-1]], [wy[-1]], color=ORANGE, s=26, zorder=5)
if wsd_done:
    ax.text(650, 2.98, f"WSD 收在 {wy[-1]:.2f}", fontsize=8.5,
            color=ORANGE, fontweight="bold")
else:
    ax.text(wx[-1] + 18, wy[-1] + 0.10, f"WSD {wx[-1]}/1000", fontsize=9,
            color=ORANGE, fontweight="bold")
ax.text(760, cy[-1] + 0.10, f"constant 收在 {cy[-1]:.2f}", fontsize=8.5, color=BLUE)
ax.set_xlim(0, 1000)
ax.set_ylim(2.9, 4.95)
ax.set_xticks([0, 250, 500, 750, 1000], ["0", "250", "500", "750", "1000"])
ax.set_xlabel("训练步数", fontsize=8.5)
ax.set_ylabel("loss", fontsize=8.5)
strip(ax)
ax.grid(axis="y", color=HAIR, linewidth=0.7)
ax.legend(loc="upper right", frameon=False, fontsize=8.2)
fig.tight_layout(pad=0.3)
save(fig, "V3-LR消融.png")
