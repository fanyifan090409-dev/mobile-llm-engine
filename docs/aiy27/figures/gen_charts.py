#!/usr/bin/env python3
"""AIY PPT 数据图生成 v2（F1-F5）：科研级双面板构图 + 真实逐题数据。

v2 修正：
- 画布固定 1600×900（savefig 不用 tight bbox——各图比例不一导致 PPT 错位的根因）
- F2 横向条形（v1 数据坐标画错：类别在 y、值在 x 的横条被画成了纵条）
- 每图双面板 + (a)(b) 标签 + 逐题矩阵（40 题真实状态，来自 nightly 评测产物）
- F1 加收敛放大 inset；F4 改坡度图（对数轴）；F5 加验收线
用法：.venv/bin/python docs/aiy27/figures/gen_charts.py
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatch
from matplotlib.path import Path
from matplotlib.patheffects import withStroke

HERE = os.path.dirname(os.path.abspath(__file__))
plt.style.use(os.path.join(HERE, "style.mplstyle"))

import matplotlib.font_manager as fm
_FONT_NAME = None
for _p in ("/System/Library/Fonts/PingFang.ttc",
           "/System/Library/Fonts/Hiragino Sans GB.ttc",
           "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"):
    if os.path.exists(_p):
        try:
            fm.fontManager.addfont(_p)
            _FONT_NAME = fm.FontProperties(fname=_p).get_name()
            break
        except Exception:
            continue
if _FONT_NAME:
    plt.rcParams["font.sans-serif"] = [_FONT_NAME, "Helvetica Neue", "DejaVu Sans"]

BLUE = "#0A84FF"
GREEN = "#30D158"
ORANGE = "#FF9F0A"
RED = "#FF3B30"
DARK = "#1D1D1F"
MID = "#6E6E73"
LIGHT = "#AEAEB2"
HAIR = "#D9D9DE"
GRID = "#E5E5EA"

W, H = 8.0, 4.5          # 1600×900 @200dpi（固定画布，禁止 tight bbox）
DPI = 200


def new_fig():
    fig = plt.figure(figsize=(W, H), dpi=DPI)
    fig.subplots_adjust(left=0.08, right=0.975, top=0.84, bottom=0.24)
    return fig


def panel_label(ax, text):
    ax.text(-0.14, 1.08, text, transform=ax.transAxes, fontsize=13.5,
            fontweight="bold", color=DARK, va="top")


def title(fig, text, sub=None):
    fig.text(0.08, 0.935, text, fontsize=15, fontweight="bold", color=DARK)
    if sub:
        fig.text(0.08, 0.895, sub, fontsize=10.5, color=MID)


def footer(fig, conclusion, source):
    fig.text(0.08, 0.105, conclusion, fontsize=10.5, fontweight="semibold", color=DARK)
    fig.text(0.08, 0.055, source, fontsize=8.5, color=LIGHT)
    fig.add_artist(plt.Line2D([0.08, 0.975], [0.145, 0.145], transform=fig.transFigure,
                              color=HAIR, lw=0.8))


def rounded_bar_v(ax, x, h, w=0.34, color=BLUE, bottom=0):
    """纵向圆角顶条（x=类别位置，h=数值）。"""
    r = min(w / 2, h)
    top = bottom + h
    k = 0.552 * r
    verts = [(x - w / 2, bottom), (x - w / 2, top - r),
             (x - w / 2, top - r + k), (x - w / 2 + r - k, top), (x - w / 2 + r, top),
             (x + w / 2 - r, top),
             (x + w / 2 - r + k, top), (x + w / 2, top - r + k), (x + w / 2, top - r),
             (x + w / 2, bottom)]
    codes = [Path.MOVETO, Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.LINETO]
    ax.add_patch(mpatch.PathPatch(Path(verts, codes), facecolor=color, edgecolor="none"))


def rounded_bar_h(ax, y, w_val, h=0.30, color=BLUE, left=0):
    """横向圆角右端条（y=类别位置，w_val=数值沿 x 轴）。"""
    r = min(h / 2, w_val)
    x0, x1 = left, left + w_val
    y0, y1 = y - h / 2, y + h / 2
    k = 0.552 * r
    verts = [(x0, y0), (x0, y1),
             (x1 - r, y1),
             (x1 - r + k, y1), (x1, y1 - k), (x1, y1 - r),
             (x1, y0 + r),
             (x1, y0 + k), (x1 - k, y0), (x1 - r, y0),
             (x0, y0)]
    codes = [Path.MOVETO, Path.LINETO, Path.LINETO,
             Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO,
             Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO]
    ax.add_patch(mpatch.PathPatch(Path(verts, codes), facecolor=color, edgecolor="none"))


def value_label(ax, x, y, text, size=10, color=DARK, dy=0.02, dx=0):
    ax.text(x + dx, y + dy, text, ha="center", va="bottom", fontsize=size,
            fontweight="bold", color=color,
            path_effects=[withStroke(linewidth=3, foreground="white")])


def cleanup(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(HAIR)
    ax.spines["bottom"].set_color(HAIR)


def save(fig, name):
    fig.savefig(os.path.join(HERE, name), facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- F1 训练曲线

def f1_training():
    data = json.load(open(os.path.join(HERE, "data", "sft17_training.json")))
    train, evals = data["train"], data["eval"]
    xs = [p[0] for p in train]
    ys = [p[1] for p in train]
    fig = new_fig()
    fig.subplots_adjust(left=0.09, right=0.975, top=0.84, bottom=0.24)
    title(fig, "训练曲线 · 1.7B SFT17",
          "基于 Qwen3-1.7B 继续训练 · 2764 步 · 2 epochs · 2026-11-01 · 双卡 5090")
    ax = fig.add_axes([0.09, 0.28, 0.885, 0.55])
    panel_label(ax, "(a) 全程")
    ax.plot(xs, ys, color=BLUE, lw=1.5, solid_capstyle="round", zorder=3)
    ax.scatter([p[0] for p in evals], [p[1] for p in evals], s=30, color=GREEN, zorder=4)
    ax.plot([p[0] for p in evals], [p[1] for p in evals], color=GREEN, lw=0.9, ls="--", alpha=0.7, zorder=2)
    ax.annotate("loss 2.53", xy=(10, 2.532), xytext=(140, 2.35), fontsize=9.5, color=MID,
                arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.8))
    ax.annotate("train 0.48", xy=(2764, 0.482), xytext=(2260, 1.30), fontsize=9.5, color=BLUE,
                fontweight="bold", arrowprops=dict(arrowstyle="-", color=BLUE, lw=0.8, alpha=0.6))
    ax.annotate("eval 0.535", xy=(2764, 0.535), xytext=(2230, 0.78), fontsize=9.5, color=GREEN,
                fontweight="bold", arrowprops=dict(arrowstyle="-", color=GREEN, lw=0.8, alpha=0.6))
    ax.set_xlabel("训练步数", fontsize=10)
    ax.set_ylabel("loss", fontsize=10)
    ax.set_ylim(0.3, 2.75)
    ax.set_xlim(-80, 2900)
    cleanup(ax)
    # (b) 收敛放大
    ax2 = fig.add_axes([0.575, 0.34, 0.335, 0.32])
    ax2.set_facecolor("#FBFBFD")
    panel_label(ax2, "(b) 尾段放大")
    mask = [i for i, s in enumerate(xs) if s >= 2000]
    ax2.plot([xs[i] for i in mask], [ys[i] for i in mask], color=BLUE, lw=1.5, zorder=3)
    ax2.scatter([p[0] for p in evals if p[0] >= 2000], [p[1] for p in evals if p[0] >= 2000],
                s=26, color=GREEN, zorder=4)
    ax2.set_ylim(0.40, 0.62)
    ax2.set_xlim(1980, 2800)
    ax2.tick_params(labelsize=8)
    ax2.grid(color=GRID, lw=0.6, alpha=1)
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    ax2.spines["left"].set_color(HAIR)
    ax2.spines["bottom"].set_color(HAIR)
    footer(fig, "结论：训练损失 2.53 → 0.48（尾段稳定在 0.5 以下），验证损失收敛到 0.535——工具调用能力来自这 2764 步监督微调。",
           "数据来源：训练机 checkpoint-2764 trainer_state.json（282 条日志） · SFT17 评测报告 2026-11-02")
    save(fig, "F1-训练曲线.png")


# ---------------------------------------------------------------- F2 工具调用

def f2_toolcall():
    raw = json.load(open(os.path.join(HERE, "data", "toolcall_40.json")))
    tiers = ["sft17-Q8_0", "sft17-Q5_K_M", "sft17-Q4_K_M"]
    names = ["0.6B 基线\n（SFT3B）", "1.7B Q8_0", "1.7B Q5_K_M", "1.7B Q4_K_M"]
    emit = [100, 97.5, 90, 97.5]
    schema = [100, 95, 90, 95]
    fig = new_fig()
    title(fig, "工具调用评测 · 40 题（30 训练分布 + 10 泛化）",
          "日历事件添加 add_calendar_event · temperature 0.7 · demo-cli 实测 · 发射率与 schema 通过率分列")
    # (a) 横向条形
    ax = fig.add_axes([0.08, 0.28, 0.44, 0.53])
    panel_label(ax, "(a) 汇总")
    rows = list(range(4))[::-1]
    for i in rows:
        rounded_bar_h(ax, i - 0.19, emit[i], h=0.26, color=BLUE)
        rounded_bar_h(ax, i + 0.19, schema[i], h=0.26, color=GREEN)
        ax.text(emit[i] + 1.8, i - 0.19, f"{emit[i]:g}%", fontsize=9.5, fontweight="bold",
                color=BLUE, va="center", path_effects=[withStroke(linewidth=3, foreground="white")])
        ax.text(schema[i] + 1.8, i + 0.19, f"{schema[i]:g}%", fontsize=9.5, fontweight="bold",
                color=GREEN, va="center", path_effects=[withStroke(linewidth=3, foreground="white")])
    ax.set_yticks(list(rows), names)
    ax.set_ylim(-0.72, 3.4)
    ax.set_xlim(0, 112)
    ax.set_xticks([0, 25, 50, 75, 100], ["0", "25%", "50%", "75%", "100%"])
    ax.grid(axis="y", visible=False)
    ax.tick_params(labelsize=9)
    cleanup(ax)
    ax.plot([], [], color=BLUE, lw=5, solid_capstyle="round", label="发射率")
    ax.plot([], [], color=GREEN, lw=5, solid_capstyle="round", label="schema 通过率")
    ax.legend(loc="lower right", fontsize=8.5, bbox_to_anchor=(1.0, 0.02))
    # (b) 40 题 × 3 档矩阵
    ax2 = fig.add_axes([0.585, 0.28, 0.39, 0.53])
    panel_label(ax2, "(b) 逐题矩阵（40×3）")
    colors = {"executed": GREEN, "failed": GREEN, "rejected": RED, "no_emit": "#E0E0E5"}
    for ti, t in enumerate(tiers):
        rows = [r for r in raw[t]["rows"] if r["q"] != "summary"]
        # 行序按分组显式排布：训练分布 30 题在上（y=39..10），泛化 10 题在下（y=9..0）
        train = sorted([r for r in rows if r["group"] == "train"], key=lambda r: r["q"])
        gen = sorted([r for r in rows if r["group"] == "gen"], key=lambda r: r["q"])
        for i, r in enumerate(train):
            status = r["status"]
            c = colors.get(status, RED)
            ax2.scatter(ti, 39 - i, s=30, color=c, edgecolors=c if status != "no_emit" else LIGHT,
                        linewidths=1.2, zorder=3, alpha=1.0 if status != "no_emit" else 0.55)
        for i, r in enumerate(gen):
            status = r["status"]
            c = colors.get(status, RED)
            ax2.scatter(ti, 9 - i, s=30, color=c, edgecolors=c if status != "no_emit" else LIGHT,
                        linewidths=1.2, zorder=3, alpha=1.0 if status != "no_emit" else 0.55)
    ax2.axhspan(-0.5, 29.5, color="#F5F9FF", zorder=0)
    ax2.axhspan(29.5, 39.5, color="#FFF8F0", zorder=0)
    ax2.axhline(29.5, color=HAIR, lw=1, zorder=1)
    ax2.set_xlim(-0.5, 2.5)
    ax2.set_ylim(-0.5, 39.5)
    ax2.set_xticks(range(3), ["Q8_0", "Q5_K_M", "Q4_K_M"])
    ax2.set_yticks([0, 10, 20, 39], ["1", "10", "20", "40"])
    ax2.tick_params(labelsize=9)
    ax2.text(0.0, 33.6, "训练分布题 30 道（三档全过）", fontsize=9, color="#4A6FA5", fontweight="semibold")
    ax2.text(0.0, 3.4, "泛化题 10 道（失败集中在此）", fontsize=9, color="#B0702E", fontweight="semibold")
    ax2.grid(False)
    for s in ("top", "right", "left", "bottom"):
        ax2.spines[s].set_color(HAIR)
    ax2.scatter([], [], s=30, color=GREEN, label="通过（schema 校验）")
    ax2.scatter([], [], s=30, color=RED, label="拒绝（占位符/话术替代）")
    ax2.legend(loc="lower left", fontsize=8.5, bbox_to_anchor=(-0.02, -0.19), ncol=2)
    footer(fig, "结论：三档 schema 通过率 90-95%，30 道训练分布题 100% 通过；全部失败集中在泛化题——工具调用结构是稳定学会的。",
           "数据来源：SFT17 评测报告 §三 · 逐题状态 train/nightly/work/toolcall/sft17-*/case 产物（2026-11-01 实测）")
    save(fig, "F2-工具调用40题.png")


# ---------------------------------------------------------------- F3 幻觉率

def f3_hallucination():
    groups = ["总体\n(n=15)", "相对日期\n(n=9)", "绝对日期\n(n=6)"]
    before = [0, 0, 0]
    after = [60.0, 77.8, 33.3]
    fig = new_fig()
    title(fig, "幻觉率评测 · 日期映射 15 题",
          "「今天几号 / 明天星期几」类问题 · 评测口径：输出日期与基准日推算一致")
    ax = fig.add_axes([0.08, 0.28, 0.44, 0.53])
    panel_label(ax, "(a) 锚点前后正确率")
    x = range(len(groups))
    bw = 0.30
    for i in x:
        rounded_bar_v(ax, i - bw / 2 - 0.02, before[i], w=bw, color=LIGHT)
        rounded_bar_v(ax, i + bw / 2 + 0.02, after[i], w=bw, color=BLUE)
        value_label(ax, i - bw / 2 - 0.02, before[i], "0%", size=9.5, color=MID, dy=0.04)
        value_label(ax, i + bw / 2 + 0.02, after[i], f"{after[i]:.0f}%", size=9.5, color=BLUE, dy=0.04)
    ax.set_xticks(list(x), groups)
    ax.set_ylim(0, 96)
    ax.set_yticks([0, 25, 50, 75], ["0", "25%", "50%", "75%"])
    ax.tick_params(labelsize=9)
    ax.grid(axis="x", visible=False)
    cleanup(ax)
    ax.plot([], [], color=LIGHT, lw=5, solid_capstyle="round", label="无锚点（0/15）")
    ax.plot([], [], color=BLUE, lw=5, solid_capstyle="round", label="注入「今天」锚点（9/15）")
    ax.legend(loc="upper left", fontsize=8.5, bbox_to_anchor=(0.0, -0.02))
    # (b) 失败模式
    ax2 = fig.add_axes([0.585, 0.28, 0.39, 0.53])
    panel_label(ax2, "(b) 锚点后 6 题失败模式")
    ax2.axis("off")
    items = [
        ("① 相对日期映射不稳", "「大后天 / 明晚」这类短语偶发算错"),
        ("② 绝对日期丢失", "「12月20日」偶发输出成当天日期"),
        ("③ 补零不一致", "个位数日期缺前导 0（11-1 vs 11-01）"),
        ("④ 采样随机性", "temperature 0.7 下同题复跑结果不同"),
        ("⑤ 训练期无锚点", "SFT17 合成数据没教「明天=今天+1」——根因"),
    ]
    y = 0.88
    for t, d in items:
        ax2.text(0.02, y, t, fontsize=10.5, fontweight="semibold", color=DARK)
        ax2.text(0.02, y - 0.075, d, fontsize=9, color=MID)
        y -= 0.175
    ax2.text(0.02, y + 0.02, "对策：SFT19 合成全量带锚点 + 推理侧注入今天日期，验证集复测。",
             fontsize=9.5, fontweight="bold", color=GREEN)
    footer(fig, "结论：一句「今天是 2026 年 11 月 3 日（周三）」让正确率 0 → 60%——模型不是不会算日期，是缺少参照系；剩余失败已逐条定位。",
           "数据来源：SFT17 评测报告 §四（锚点版 2026-11-02 复测） · scripts/eval_hallucination.sh 口径")
    save(fig, "F3-幻觉率.png")


# ---------------------------------------------------------------- F4 原版对拍

def f4_compare():
    fig = new_fig()
    title(fig, "原版对拍 · 官方 Qwen3-1.7B vs 我们的 SFT17（同 Q8_0 档）",
          "同量化档、同 256 max-tokens 口径 · demo-cli 实测")
    # (a) PPL 坡度图（对数轴）
    ax = fig.add_axes([0.08, 0.28, 0.44, 0.53])
    panel_label(ax, "(a) 困惑度（越低越好）")
    pairs = [("目标域", 12.29, 5.42), ("通用域", 38.40, 17.58)]
    for name, o, m in pairs:
        ax.plot([0, 1], [o, m], lw=2.2, solid_capstyle="round", color=BLUE if name == "目标域" else GREEN, zorder=3)
        ax.scatter([0, 1], [o, m], s=44, color=BLUE if name == "目标域" else GREEN, zorder=4)
        ax.text(-0.06, o, f"{o:.2f}", fontsize=9.5, fontweight="bold", color=MID, va="center", ha="right")
        ax.text(1.06, m, f"{m:.2f}", fontsize=9.5, fontweight="bold", color=DARK, va="center", ha="left")
    ax.annotate("目标域 2.3×", xy=(0.5, 8.9), xytext=(0.62, 13), fontsize=9.5, color=BLUE, fontweight="semibold",
                arrowprops=dict(arrowstyle="-", color=BLUE, lw=0.8, alpha=0.6))
    ax.annotate("通用域 2.2×", xy=(0.5, 28), xytext=(0.62, 32), fontsize=9.5, color=GREEN, fontweight="semibold",
                arrowprops=dict(arrowstyle="-", color=GREEN, lw=0.8, alpha=0.6))
    ax.set_yscale("log")
    ax.set_xticks([0, 1], ["官方 Qwen3-1.7B", "我们的 SFT17"])
    ax.set_ylim(4, 52)
    ax.tick_params(labelsize=9.5)
    ax.grid(axis="x", visible=False)
    cleanup(ax)
    ax.plot([], [], color=BLUE, lw=2.2, label="目标域（工具/中文任务）")
    ax.plot([], [], color=GREEN, lw=2.2, label="通用域")
    ax.legend(loc="upper right", fontsize=8.5, bbox_to_anchor=(1.0, -0.02))
    # (b) 生成问题题数
    ax2 = fig.add_axes([0.585, 0.28, 0.39, 0.53])
    panel_label(ax2, "(b) 生成质量 · 15 题复读/截断/空答")
    rounded_bar_v(ax2, -0.20, 14, w=0.34, color=LIGHT)
    rounded_bar_v(ax2, 0.20, 0.01, w=0.34, color=GREEN)
    value_label(ax2, -0.20, 14, "14 题", size=10, color=MID, dy=0.4)
    value_label(ax2, 0.20, 0.01, "0 题", size=10, color=GREEN, dy=0.4)
    ax2.set_xticks([-0.2, 0.2], ["官方", "SFT17"])
    ax2.set_ylim(0, 17)
    ax2.tick_params(labelsize=9.5)
    ax2.grid(axis="x", visible=False)
    cleanup(ax2)
    ax2.text(0.02, 0.86, "官方默认开 thinking：256 预算被思考块吃满，", transform=ax2.transAxes,
             fontsize=9, color=MID)
    ax2.text(0.02, 0.80, "14/15 题答不完；SFT17 无 thinking 输出，干净收尾。", transform=ax2.transAxes,
             fontsize=9, color=MID)
    footer(fig, "结论：目标域困惑度 12.29 → 5.42（2.3 倍），生成问题 14 题 → 0 题——中文工具场景的能力是训练出来的，且生成干净不拖尾。",
           "数据来源：SFT17 评测报告 §五（demo-cli 实测，同 Q8_0 档、同 256 max-tokens 口径）")
    save(fig, "F4-原版对拍.png")


# ---------------------------------------------------------------- F5 跑分矩阵

def f5_bench():
    tiers = ["powerSaver", "balanced", "performance", "turbo"]
    air = [72.9, 72.4, 68.7, 76.3]
    pro = [91.7, 92.5, 93.4, 93.5]
    fig = new_fig()
    title(fig, "推理速度矩阵 · 官方 Qwen3-1.7B Q4_K_M",
          "解码 tok/s · context 4096 · max-tokens 200 · temperature 0.7（产品默认口径）· bench-mac.sh 四档矩阵")
    ax = fig.add_axes([0.08, 0.28, 0.44, 0.53])
    panel_label(ax, "(a) 双 Mac 四档")
    x = range(len(tiers))
    bw = 0.30
    for i in x:
        rounded_bar_v(ax, i - bw / 2 - 0.02, air[i], w=bw, color=BLUE)
        rounded_bar_v(ax, i + bw / 2 + 0.02, pro[i], w=bw, color=GREEN)
        value_label(ax, i - bw / 2 - 0.02, air[i], f"{air[i]:.1f}", size=9, color=BLUE, dy=1.4)
        value_label(ax, i + bw / 2 + 0.02, pro[i], f"{pro[i]:.1f}", size=9, color=GREEN, dy=1.4)
    ax.axhline(15, color=RED, lw=1.2, ls="--", zorder=2)
    ax.text(3.55, 15, " 验收线 15 tok/s", fontsize=9, color=RED, va="center")
    ax.set_xticks(list(x), tiers)
    ax.set_ylim(0, 112)
    ax.set_ylabel("tok/s", fontsize=10)
    ax.tick_params(labelsize=9.5)
    ax.grid(axis="x", visible=False)
    cleanup(ax)
    ax.plot([], [], color=BLUE, lw=5, solid_capstyle="round", label="M5 Air")
    ax.plot([], [], color=GREEN, lw=5, solid_capstyle="round", label="M5 Pro")
    ax.legend(loc="upper right", fontsize=8.5, bbox_to_anchor=(1.0, -0.02))
    # (b) 口径与真机状态
    ax2 = fig.add_axes([0.585, 0.28, 0.39, 0.53])
    panel_label(ax2, "(b) 口径与真机计划")
    ax2.axis("off")
    lines = [
        ("验收口径", "M5 Air balanced ≥ 15 tok/s（实测 72.4，为线 4.8 倍）", DARK),
        ("机型", "Mac M5 Air / M5 Pro（16GB）· 同文件 md5 校验", DARK),
        ("模型", "官方 Qwen3-1.7B Q4_K_M（钉版 llama-quantize 自转）", DARK),
        ("真机矩阵", "iPhone 16 / 17 / 18 Pro 三代芯片实测进行中", ORANGE),
        ("目标", "验证 8GB 内存机型装得下 + 各档速度曲线", ORANGE),
    ]
    y = 0.90
    for t, d, c in lines:
        ax2.text(0.02, y, t, fontsize=10.5, fontweight="bold", color=c)
        ax2.text(0.02, y - 0.065, d, fontsize=9, color=MID)
        y -= 0.168
    footer(fig, "结论：双 Mac 全档 ≥68 tok/s（balanced 72.4 / 92.5），远超 15 tok/s 验收线——1.7B 在笔记本上快过人阅读速度；真机矩阵是 Pro 组「不同设备」证据的最后一环。",
           "数据来源：docs/评测/M1.5-双Mac基准表.md（2026-10-26 实测） · 真机矩阵 #31 进行中")
    save(fig, "F5-跑分矩阵.png")


# ---------------------------------------------------------------- 双图合成（S6/S7 用）

def compose_slides():
    """把两张 1600×900 图合成一张 3200×900（中间留白缝）。
    用途：PPT 页内只放一张合成图——WPS/Keynote 对多图布局的渲染差异直接归零。"""
    import matplotlib.image as mpimg
    pairs = [
        ("F1-训练曲线.png", "F2-工具调用40题.png", "S6-评测①-训练与工具.png"),
        ("F3-幻觉率.png", "F4-原版对拍.png", "S7-评测②-幻觉与对拍.png"),
    ]
    for a, b, out in pairs:
        im1 = mpimg.imread(os.path.join(HERE, a))
        im2 = mpimg.imread(os.path.join(HERE, b))
        fig = plt.figure(figsize=(16, 4.5), dpi=200)
        ax1 = fig.add_axes([0.0, 0.0, 0.49, 1.0])
        ax1.imshow(im1)
        ax1.axis("off")
        ax2 = fig.add_axes([0.51, 0.0, 0.49, 1.0])
        ax2.imshow(im2)
        ax2.axis("off")
        fig.savefig(os.path.join(HERE, out), facecolor="white")
        plt.close(fig)


if __name__ == "__main__":
    f1_training()
    f2_toolcall()
    f3_hallucination()
    f4_compare()
    f5_bench()
    compose_slides()
    print("F1-F5 v2 + S6/S7 合成图 done ->", HERE)
