#!/usr/bin/env python3
"""AIY 27 PPT v6 素材：设备屏幕卡 + 三张数据图。

- 设备卡：真实跑分截图 + 深色窄边框 + 柔和投影（不是假手机，只是屏幕展示卡）。
- 图表：matplotlib / Helvetica Neue / 透明底，颜色与 v6 色板一致。
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "v6-assets")
os.makedirs(OUT, exist_ok=True)

NAVY = "#0B1B2B"
BLUE = "#1E6BFF"
MINT = "#2FBFB0"
RUST = "#B24A32"
GRAY = "#8A939E"
LINE = "#D9D2C5"
INK = "#0E1116"

plt.rcParams.update({
    "font.family": "Helvetica Neue",
    "font.size": 9,
    "axes.edgecolor": LINE,
    "axes.labelcolor": "#6E7680",
    "xtick.color": "#6E7680",
    "ytick.color": "#6E7680",
    "figure.dpi": 300,
    "savefig.dpi": 300,
})


def device_tile():
    src = Image.open(os.path.join(HERE, "v5-assets", "cover-device-v5b.png")).convert("RGB")
    W, H = 1480, 1720
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([40, 58, 1440, 1700], radius=100, fill=(0, 0, 0, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(34))
    canvas.alpha_composite(shadow)

    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle([40, 40, 1440, 1682], radius=96, fill=(10, 10, 12, 255))
    bd.rounded_rectangle([54, 54, 1426, 1668], radius=84, outline=(52, 52, 58, 255), width=2)
    canvas.alpha_composite(body)

    sw, sh = 1348, 1596
    screen = src.resize((sw, sh), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (sw, sh), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, sw, sh], radius=62, fill=255)
    screen.putalpha(mask)
    canvas.paste(screen, (66, 66), screen)
    canvas.save(os.path.join(OUT, "device-tile.png"))


def chart_training():
    rows = [
        ("SFT19", 45, NAVY),
        ("SFT25", 47, NAVY),
        ("SFT26", 47, GRAY),
        ("SFT27e", 58, BLUE),
    ]
    fig, ax = plt.subplots(figsize=(7.4, 3.3))
    ys = np.arange(len(rows))[::-1]
    for y, (name, score, color) in zip(ys, rows):
        ax.plot([0, score], [y, y], color=color, lw=3.2, alpha=0.9, solid_capstyle="round")
        ax.plot(score, y, "o", ms=10, color=color, zorder=3)
        ax.text(score + 1.4, y, str(score), va="center", ha="left",
                color=color, fontsize=12, fontweight="bold")
    ax.set_yticks(ys)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8.5, color=INK)
    ax.set_xlim(0, 69)
    ax.set_ylim(-0.6, 3.6)
    ax.set_xlabel("score / 69", fontsize=8)
    ax.axvline(47, color=GRAY, lw=1, ls=(0, (3, 4)), alpha=0.7)
    ax.text(47.8, 3.35, "training plateau 47", color=GRAY, fontsize=8, va="top")
    ax.grid(axis="x", color=LINE, lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0)
    fig.tight_layout(pad=0.3)
    fig.savefig(os.path.join(OUT, "chart-training.png"), transparent=True)
    plt.close(fig)


def chart_engine():
    models = [
        ("0.6B IQ4_XS", 1.109, 121.1, MINT),
        ("0.6B Q4_K_M", 1.144, 119.7, MINT),
        ("0.6B Q5_K_M", 1.187, 100.5, MINT),
        ("1.7B Q8_0", 2.683, 40.1, NAVY),
        ("1.7B Q5_K_M", 2.054, 56.5, NAVY),
        ("1.7B Q4_K_M", 1.903, 61.1, BLUE),
    ]
    fig, ax = plt.subplots(figsize=(6.6, 3.7))
    for name, mem, speed, color in models:
        size = 90 if name.startswith("1.7") else 70
        ax.scatter(mem, speed, s=size, color=color, alpha=0.9, edgecolor="white", linewidth=1.2, zorder=3)
        if name.startswith("0.6"):
            continue
        dx, dy = 0.04, 2.4
        if name == "1.7B Q4_K_M":
            dx, dy = 0.045, 3.2
        if name == "1.7B Q5_K_M":
            dx, dy = 0.045, -7.0
        if name == "1.7B Q8_0":
            dx, dy = 0.045, 2.4
        ax.text(mem + dx, speed + dy, name.replace("1.7B ", "1.7B\n"),
                fontsize=7.4, color=color, va="bottom")
    # 0.6B 三点集中，合并成一个注记，避免标签互相压
    ax.annotate("0.6B · 3 quants\n100–121 tok/s", xy=(1.15, 113.5), xytext=(1.34, 108),
                fontsize=7.6, color="#1E8E84", va="center",
                arrowprops=dict(arrowstyle="-", color="#1E8E84", lw=0.8, alpha=0.7))
    ax.axvline(2.048, color=GRAY, lw=1, ls=(0, (3, 4)), alpha=0.7)
    ax.set_xlim(0.95, 2.95)
    ax.set_ylim(15, 135)
    ax.set_xlabel("peak memory / GB", fontsize=8)
    ax.set_ylabel("stable decode / tok/s", fontsize=8)
    ax.grid(color=LINE, lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout(pad=0.3)
    fig.savefig(os.path.join(OUT, "chart-engine.png"), transparent=True)
    plt.close(fig)


def chart_dates():
    x = [0, 1, 2]
    y = [51.7, 93.3, 96.7]
    labels = ["SFT20b", "SFT20c", "SFT20d"]
    fig, ax = plt.subplots(figsize=(6.4, 3.1))
    ax.plot(x, y, color=NAVY, lw=2.4, zorder=2)
    for i, (xi, yi) in enumerate(zip(x, y)):
        color = BLUE if i == 2 else NAVY
        ax.scatter(xi, yi, s=110, color=color, edgecolor="white", linewidth=1.5, zorder=3)
        vy = yi + 3.2 if i > 0 else yi - 7.0
        ax.text(xi, vy, f"{yi:.1f}%", ha="center", color=color, fontsize=12, fontweight="bold")
        ly = yi - 8.0 if i > 0 else yi - 14.0
        ax.text(xi, ly, labels[i], ha="center", color=GRAY, fontsize=8)
    ax.set_ylim(35, 108)
    ax.set_xlim(-0.4, 2.4)
    ax.set_ylabel("date accuracy / %", fontsize=8)
    ax.grid(axis="y", color=LINE, lw=0.7, alpha=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xticks([])
    ax.tick_params(length=0)
    fig.tight_layout(pad=0.3)
    fig.savefig(os.path.join(OUT, "chart-dates.png"), transparent=True)
    plt.close(fig)


def dark_bg(w, h, seed=7, glow=(0.55, 0.44), glow_r=0.80, rings=None,
            ring_center=(0.53, 0.44), amp=0.20, vignette=0.50):
    """深海军蓝背景：斜向渐变 + 弥散蓝光 + 细同心环 + 稀疏点阵 + 微颗粒。"""
    W, H = w * 2, h * 2
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    x = xx / (W - 1); y = yy / (H - 1)
    t = np.clip(0.52 * x + 0.48 * y, 0, 1)[..., None]
    top = np.array([11.0, 28.0, 45.0])
    bot = np.array([5.0, 13.0, 23.0])
    img = top * (1 - t) + bot * t
    asp = H / W

    def glow_at(cx, cy, r, color, a):
        d = np.sqrt((x - cx) ** 2 + ((y - cy) * asp) ** 2) / r
        return (np.clip(1 - d, 0, 1) ** 1.6)[..., None] * np.array(color) * a

    img += glow_at(glow[0], glow[1], glow_r, (30, 90, 200), amp)
    img += glow_at(0.10, 0.92, 0.75, (20, 110, 100), amp * 0.22)
    vx = (x - 0.5) * 1.14; vy = (y - 0.5) * 1.02
    v = np.clip(1 - vignette * (vx * vx + vy * vy), 0.64, 1.0)[..., None]
    img *= v
    rng = np.random.default_rng(seed)
    img += rng.normal(0, 1.1, (H, W, 1))
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")

    if rings:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        cx, cy = ring_center[0] * W, ring_center[1] * H
        base = min(W, H)
        for r, a in rings:
            rr = r * base
            d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
                      outline=(130, 175, 225, a), width=2)
        im = Image.alpha_composite(im, ov)

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for py in range(28, H, 56):
        for px in range(28, W, 56):
            d.point((px, py), fill=(150, 190, 235, 8))
    im = Image.alpha_composite(im, ov)
    return im.convert("RGB").resize((w, h), Image.LANCZOS)


def dark_panels():
    specs = [
        ("bg-cover.jpg", 1197, 1500, dict(glow=(0.55, 0.42), glow_r=0.82,
         rings=[(0.33, 30), (0.47, 22), (0.61, 16)], ring_center=(0.53, 0.44))),
        ("bg-problem.jpg", 946, 1144, dict(seed=11, glow=(0.24, 0.18), glow_r=0.62,
         rings=[(0.44, 18), (0.64, 12)], ring_center=(0.94, 0.88))),
        ("bg-ceiling.jpg", 886, 744, dict(seed=17, glow=(0.84, 0.22), glow_r=0.70,
         rings=[(0.58, 16), (0.82, 11)], ring_center=(1.04, -0.04))),
        ("bg-math.jpg", 1137, 1500, dict(seed=23, glow=(0.82, 0.18), glow_r=0.78,
         rings=[(0.50, 14), (0.74, 10)], ring_center=(1.06, 1.02))),
        ("bg-closing.jpg", 1137, 1500, dict(seed=31, glow=(0.82, 0.76), glow_r=0.78,
         rings=[(0.44, 22), (0.64, 15)], ring_center=(0.90, 0.94))),
        ("bg-gates.jpg", 2667, 420, dict(seed=41, glow=(0.55, 0.55), glow_r=0.80,
         rings=[(0.52, 15), (0.86, 10)], ring_center=(0.55, 1.55))),
    ]
    for name, w, h, kw in specs:
        dark_bg(w, h, **kw).save(os.path.join(OUT, name), quality=94, subsampling=0)


def vscode_tile():
    """真实 VS Code 窗口截图：裁到标题栏 + 面包屑 + 代码，圆角与投影做成浮动卡。"""
    src = Image.open(os.path.join(OUT, "raw", "vscode-toolcall-raw.png")).convert("RGBA")
    crop = src.crop((0, 0, 2300, 850))
    w, h = crop.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=22, fill=255)
    crop.putalpha(mask)

    pad, blur = 24, 18
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2 + 10), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    sh.putalpha(mask.point(lambda v: int(v * 0.55)))
    shadow.paste(sh, (pad, pad + 10), sh)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(crop, (pad, pad))
    canvas.save(os.path.join(OUT, "vscode-toolcall.png"))


if __name__ == "__main__":
    device_tile()
    chart_training()
    chart_engine()
    chart_dates()
    dark_panels()
    vscode_tile()
    print("assets ->", OUT)
