#!/usr/bin/env python3
"""AIY 27 PPT v4：编辑式高视觉冲击版（10 页）。

设计约束：
- 暖纸底 + 近黑 + 信号橙；不用圆角卡片堆叠，细线分栏，大数字做视觉锚点。
- 封面用 iPhone 18 Pro Max 真机截图（cover-phone.png），不是示意图。
- 全部文字/表格/线框为 PPTX 原生对象，WPS 可编辑；图表是真机/训练日志生成 PNG。
用法：.venv/bin/python docs/aiy27/figures/gen_pptx_v4.py
"""
import os
import struct

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "AIY27-PPT-v4.pptx")

# ---------- 色板 ----------
INK = RGBColor(0x11, 0x11, 0x12)
PAPER = RGBColor(0xF4, 0xF1, 0xE9)
BLUE_BG = RGBColor(0xE9, 0xF1, 0xFB)
PEACH_BG = RGBColor(0xFA, 0xE8, 0xDD)
GREEN_BG = RGBColor(0xE9, 0xF4, 0xEC)
WHITE_BG = RGBColor(0xFF, 0xFF, 0xFF)
OFFWHITE = RGBColor(0xF7, 0xF3, 0xEA)
MUTED = RGBColor(0x6B, 0x67, 0x5E)
LIGHT = RGBColor(0xA8, 0xA2, 0x95)
HAIR = RGBColor(0xD8, 0xD2, 0xC4)
ORANGE = RGBColor(0xFF, 0x4D, 0x00)
BLUE = RGBColor(0x1F, 0x5E, 0xFF)
GREEN = RGBColor(0x0E, 0x7A, 0x3D)
DARK = RGBColor(0x0B, 0x0B, 0x0C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "PingFang SC"
MONO = "Menlo"

SW, SH = Inches(13.333), Inches(7.5)
M = Inches(0.7)
W = SW - 2 * M


def png_size(path):
    with open(path, "rb") as f:
        d = f.read(26)
    w, h = struct.unpack(">II", d[16:24])
    return w, h


def set_font(run, size, bold=False, color=INK, name=FONT):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        e = rPr.find(qn(tag))
        if e is None:
            e = rPr.makeelement(qn(tag), {})
            rPr.append(e)
        e.set("typeface", name)


def text(slide, x, y, w, h, lines, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, space_after=0, line_spacing=1.0):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        p.line_spacing = line_spacing
        runs = para if isinstance(para, list) else [para]
        for run in runs:
            t, s, b, c = run[:4]
            name = run[4] if len(run) > 4 else FONT
            r = p.add_run()
            r.text = t
            set_font(r, s, b, c, name)
    return tb


def rect(slide, x, y, w, h, fill, line=None, line_w=0.75, radius=None):
    shape = MSO_SHAPE.ROUNDED_RECTANGLE if radius is not None else MSO_SHAPE.RECTANGLE
    shp = slide.shapes.add_shape(shape, x, y, w, h)
    if radius is not None:
        try:
            shp.adjustments[0] = radius
        except Exception:
            pass
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w)
    shp.shadow.inherit = False
    return shp


def bg(slide, color):
    rect(slide, 0, 0, SW, SH, color)


def rule(slide, x, y, w, h=Inches(0.008), color=HAIR):
    rect(slide, x, y, w, h, color)


def vrule(slide, x, y, h, w=Inches(0.008), color=HAIR):
    rect(slide, x, y, w, h, color)


def new_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def kicker(slide, label, dark=False):
    y = Inches(0.48)
    rect(slide, M, y + Inches(0.02), Inches(0.10), Inches(0.10), ORANGE)
    text(slide, M + Inches(0.18), y, Inches(8.0), Inches(0.18),
         [[(label, 8, True, ORANGE, MONO)]], space_after=0)


def pageno(slide, n, dark=False):
    color = LIGHT if dark else MUTED
    text(slide, SW - M - Inches(1.0), Inches(0.46), Inches(1.0), Inches(0.18),
         [[(f"{n:02d} / 10", 7.5, False, color, MONO)]],
         align=PP_ALIGN.RIGHT, space_after=0)


def source(slide, txt, dark=False):
    color = LIGHT if dark else MUTED
    text(slide, M, Inches(7.16), Inches(11.9), Inches(0.18),
         [[(txt, 6.8, False, color, MONO)]], space_after=0)


def headline(slide, lines, y=Inches(0.86), size=31, dark=False, width=None):
    color = OFFWHITE if dark else INK
    text(slide, M, y, width or Inches(11.5), Inches(1.1),
         [[(t, size, True, color)] for t in lines], space_after=0, line_spacing=1.04)


def subline(slide, txt, y=Inches(1.62), dark=False, size=9.8):
    color = LIGHT if dark else MUTED
    text(slide, M, y, Inches(11.8), Inches(0.30), [[(txt, size, False, color)]],
         space_after=0)


def conclusion(slide, txt, y=Inches(6.78), dark=False):
    color = ORANGE if dark else ORANGE
    rect(slide, M, y + Inches(0.02), Inches(0.10), Inches(0.10), ORANGE)
    text(slide, M + Inches(0.18), y, Inches(11.8), Inches(0.30),
         [[(txt, 12.0, True, color)]], space_after=0)


def stat(slide, x, y, w, value, label, note="", color=ORANGE, value_size=30,
         dark=False):
    label_c = OFFWHITE if dark else INK
    note_c = LIGHT if dark else MUTED
    text(slide, x, y, w, Inches(0.50), [[(value, value_size, True, color)]],
         space_after=0, line_spacing=1.0)
    text(slide, x, y + Inches(0.50), w, Inches(0.22),
         [[(label, 9.5, True, label_c)]], space_after=0)
    if note:
        text(slide, x, y + Inches(0.72), w, Inches(0.30),
             [[(note, 7.8, False, note_c)]], space_after=0)


def phone(slide, path, x, y, w, h):
    # 后置阴影 + 黑色机身 + 真机截图
    rect(slide, x + Inches(0.07), y + Inches(0.07), w, h,
         RGBColor(0xE2, 0xDC, 0xD0), radius=0.10)
    rect(slide, x, y, w, h, RGBColor(0xF3, 0xF0, 0xE9),
         line=RGBColor(0xC9, 0xC3, 0xB5), line_w=0.8, radius=0.10)
    margin = Inches(0.075)
    avail_w, avail_h = w - 2 * margin, h - 2 * margin
    iw, ih = png_size(path)
    scale = min(avail_w / iw, avail_h / ih)
    pw, ph = iw * scale, ih * scale
    px = x + margin + (avail_w - pw) / 2
    py = y + margin + (avail_h - ph) / 2
    slide.shapes.add_picture(path, px, py, width=pw, height=ph)


def fit_image(slide, path, x, y, w, h, align="center"):
    iw, ih = png_size(path)
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    px = x + (w - pw) / 2 if align == "center" else x
    py = y + (h - ph) / 2
    return slide.shapes.add_picture(path, px, py, width=pw, height=ph)


def fig(name):
    return os.path.join(HERE, name)


# ======================================================================
prs = Presentation()
prs.slide_width = SW
prs.slide_height = SH

# ---------------- S1 封面 ----------------
s = new_slide(prs)
bg(s, BLUE_BG)
rect(s, Inches(9.0), 0, Inches(4.333), SH, PEACH_BG)
kicker(s, "AIY 27 · 高中组 PRO · 题目一 AI×科学工程（自定方向）")
pageno(s, 1)

text(s, M, Inches(1.18), Inches(8.6), Inches(1.9), [
    [("口袋里的", 50, True, INK)],
    [("Agent", 50, True, BLUE), (" 实验室", 50, True, ORANGE)],
], space_after=0, line_spacing=1.0)

text(s, M, Inches(3.18), Inches(8.5), Inches(0.45),
     [[("面向消费级设备的本地 DIY 多 Agent 编排平台", 22, True, INK)]],
     space_after=0)
text(s, M, Inches(3.72), Inches(8.5), Inches(0.32),
     [[("数据不出域 · 美高课程特训 · 日历 / 提醒真实可用 · 一台手机跑起来", 11.5, False, MUTED)]],
     space_after=0)
text(s, M, Inches(4.38), Inches(8.2), Inches(0.34),
     [[("不是云端助手的缩小版，而是学生自己的本地 Agent 工作台。", 13, True, ORANGE)]],
     space_after=0)

metrics = [
    ("61.1", "tok/s", "稳定解码 · 18 Pro Max"),
    ("0", "上传", "推理全程本机"),
    ("13/13", "真机回归", "含时间解析自检"),
    ("10M", "tokens", "美高课程合成训练"),
]
mx, mw = M, Inches(1.95)
for i, (v, unit, label) in enumerate(metrics):
    text(s, mx, Inches(5.48), mw, Inches(0.40),
         [[(v, 25, True, INK), (f" {unit}", 8.5, True, ORANGE, MONO)]],
         space_after=0)
    text(s, mx, Inches(5.95), mw, Inches(0.22),
         [[(label, 7.8, False, MUTED)]], space_after=0)
    if i < 3:
        vrule(s, mx + mw - Inches(0.12), Inches(5.50), Inches(0.62), color=HAIR)
    mx += mw

text(s, M, Inches(6.52), Inches(8.3), Inches(0.22),
     [[("团队：＿＿＿＿＿＿＿＿　　演示人：＿＿＿＿＿＿＿＿　　GitHub：mobile-llm-engine",
        8.2, False, MUTED)]], space_after=0)
text(s, M, Inches(6.88), Inches(8.3), Inches(0.22),
     [[("模型口径：基于 Qwen3 继续训练 · 推理底座 llama.cpp（MIT）· 数字来自本机训练与真机日志",
        7.2, False, MUTED)]], space_after=0)

phone(s, fig("cover-phone.png"), Inches(9.35), Inches(0.25), Inches(3.62), Inches(7.80))


# ---------------- S2 问题与用户 ----------------
s = new_slide(prs)
bg(s, PAPER)
kicker(s, "01 / PROBLEM")
pageno(s, 2)
headline(s, ["数据一旦离开设备，", "控制权就没了。"], y=Inches(0.88), size=31, width=Inches(12.0))
subline(s, "国际学校 / 美高学生每天遇到的不是「AI 不好用」，而是「不敢用」和「没网用」。",
        y=Inches(2.18), size=10.2)

stat(s, M, Inches(2.62), Inches(5.8), "0", "断网时的云端可用性",
     "请求离开设备；断网即失效，数据已经出设备", ORANGE, 40)
stat(s, M, Inches(3.69), Inches(5.8), "3.29万", "2026 ZCode 事件被上传文件",
     "4.11 亿明文字符，项目连同修改历史打包上传", ORANGE, 34)
stat(s, M, Inches(4.76), Inches(5.8), "15/15", "改前日期题全错",
     "模型没有「今天」锚点，只能靠心算瞎猜", ORANGE, 36)

text(s, Inches(7.15), Inches(2.42), Inches(5.5), Inches(0.22),
     [[("2026 公开事故（节选）", 8, True, ORANGE, MONO)]], space_after=0)
items = [
    ("2026.04–06", "Claude Code 安全后门", "未经同意回传地域、身份标识等敏感数据", "求是网 / 工信部风险提示"),
    ("2026.09", "智谱 ZCode 传包风波", "整个项目连同修改历史打包加密上传云端", "36氪 / 掘金（企业函件称）"),
    ("2026.08", "PROMPTPEEK 攻击", "共享缓存侧信道可还原其他用户提问", "NDSS 2025 论文"),
    ("2026.08", "Reasoning Trace Theft", "三家 API 加密推理链缺陷，跨模型重放窃取思维链", "CSA 研究 / 绿盟分析"),
    ("2026 上半年", "法国医院病历事件", "医生用 Claude 3 写病历，8 个月 1247 份", "法媒隐私审计报告"),
]
yy = Inches(2.72)
for i, (yr, title, leak, src) in enumerate(items):
    if i:
        rule(s, Inches(7.15), yy - Inches(0.06), Inches(5.45), color=HAIR)
    text(s, Inches(7.15), yy, Inches(1.15), Inches(0.18),
         [[(yr, 7.2, True, ORANGE, MONO)]], space_after=0)
    text(s, Inches(8.35), yy - Inches(0.015), Inches(4.25), Inches(0.20),
         [[(title, 9.0, True, INK)]], space_after=0)
    text(s, Inches(8.35), yy + Inches(0.20), Inches(4.25), Inches(0.20),
         [[(leak, 7.6, False, MUTED)]], space_after=0)
    text(s, Inches(11.35), yy + Inches(0.38), Inches(1.25), Inches(0.16),
         [[(src, 5.6, False, MUTED)]], align=PP_ALIGN.RIGHT, space_after=0)
    yy += Inches(0.78)

rect(s, M, Inches(6.02), Inches(0.10), Inches(0.68), ORANGE)
text(s, M + Inches(0.20), Inches(6.00), Inches(11.7), Inches(0.24),
     [[("目标用户：国际学校 / 美高在读学生 + 想学 AI 编排的初学者", 9.2, True, INK)]],
     space_after=0)
text(s, M + Inches(0.20), Inches(6.25), Inches(11.7), Inches(0.34),
     [[("我们要的不是更聪明的云端，而是能放在口袋里的控制权。", 13.5, True, ORANGE)]],
     space_after=0)
source(s, "来源：2026 年公开报道（求是网 / 工信部 NVDB、36氪 / 掘金、NDSS 2025、CSA / 绿盟、法媒审计）· 用户调研")

# ---------------- S3 机会 + 多 Agent 定位 ----------------
s = new_slide(prs)
bg(s, PAPER)
rect(s, 0, 0, Inches(6.0), SH, BLUE_BG)
kicker(s, "02 / OPPORTUNITY")
pageno(s, 3)
text(s, M, Inches(0.90), Inches(4.9), Inches(0.72),
     [[("云端 AI 的", 29, True, INK)]], space_after=0)
text(s, M, Inches(1.42), Inches(4.9), Inches(0.72),
     [[("两个硬伤", 29, True, INK)]], space_after=0)
text(s, M, Inches(2.28), Inches(5.0), Inches(0.52),
     [[("断网 = 不可用", 25, True, INK)]], space_after=0)
text(s, M, Inches(2.88), Inches(5.0), Inches(0.52),
     [[("数据 = 已出设备", 25, True, ORANGE)]], space_after=0)
text(s, M, Inches(3.80), Inches(4.9), Inches(0.22),
     [[("输入  →  上传  →  云端推理  →  返回", 8.5, False, MUTED, MONO)]], space_after=0)
text(s, M, Inches(4.12), Inches(4.9), Inches(0.22),
     [[("依赖网络、账号、额度与厂商策略；模型不是你的。", 8.0, False, MUTED)]], space_after=0)
text(s, M, Inches(4.55), Inches(4.9), Inches(0.52),
     [[("模型不是你的，", 13, True, INK)]], space_after=0)
text(s, M, Inches(4.88), Inches(4.9), Inches(0.52),
     [[("数据也不是你的。", 13, True, ORANGE)]], space_after=0)

text(s, Inches(6.55), Inches(0.48), Inches(5.9), Inches(0.22),
     [[("03 / LOCAL OPPORTUNITY", 8, True, ORANGE, MONO)]], space_after=0)
text(s, Inches(6.55), Inches(0.92), Inches(6.0), Inches(0.62),
     [[("本地 AI 的机会", 29, True, INK)]], space_after=0)
text(s, Inches(6.55), Inches(1.55), Inches(5.9), Inches(0.30),
     [[("同样一句话，不需要离开设备。", 10.0, False, MUTED)]], space_after=0)

steps = [
    ("01", "输入一句话", "同样的任务，不需要联网"),
    ("02", "本地 1.7B 推理", "权重在手机里，数据不出设备"),
    ("03", "结构化工具调用", "add_calendar_event + 参数"),
    ("04", "schema 校验", "格式不对直接拒绝，不执行"),
    ("05", "人确认 → 写入", "用户点「允许」才写进系统日历"),
]
yy = Inches(2.10)
for num, title, detail in steps:
    text(s, Inches(6.55), yy, Inches(0.40), Inches(0.22),
         [[(num, 10, True, ORANGE, MONO)]], space_after=0)
    text(s, Inches(7.05), yy - Inches(0.02), Inches(5.3), Inches(0.22),
         [[(title, 11.2, True, INK)]], space_after=0)
    text(s, Inches(7.05), yy + Inches(0.22), Inches(5.3), Inches(0.20),
         [[(detail, 7.8, False, MUTED)]], space_after=0)
    if num != "05":
        text(s, Inches(7.05), yy + Inches(0.42), Inches(5.3), Inches(0.18),
             [[("↓", 8, True, ORANGE, MONO)]], space_after=0)
    yy += Inches(0.64)

# 多 Agent 定位条
rect(s, M, Inches(5.55), Inches(11.93), Inches(1.18), PEACH_BG)
text(s, M + Inches(0.22), Inches(5.64), Inches(5.0), Inches(0.18),
     [[("NEXT / 本地 DIY 多 Agent 编排", 7.5, True, ORANGE, MONO)]], space_after=0)
text(s, M + Inches(0.22), Inches(5.84), Inches(6.1), Inches(0.30),
     [[("从「一个助手」到「一套 Agent 编排」", 16, True, INK)]], space_after=0)
agents = ["PLANNER", "CALENDAR", "REMINDER", "TUTOR", "VERIFIER"]
ax = Inches(7.55)
for a in agents:
    rect(s, ax, Inches(5.82), Inches(0.88), Inches(0.27), WHITE_BG,
         line=RGBColor(0xC9, 0xC3, 0xB5), line_w=0.5)
    text(s, ax, Inches(5.87), Inches(0.88), Inches(0.18),
         [[(a, 5.8, True, INK, MONO)]], align=PP_ALIGN.CENTER, space_after=0)
    ax += Inches(0.94)
text(s, M + Inches(0.22), Inches(6.30), Inches(11.4), Inches(0.22),
     [[("学生自己拆任务、配角色、看内存代价；当前单 Agent，多 Agent 编排为规划项。", 8.0, False, MUTED)]],
     space_after=0)

conclusion(s, "AI 机会 = 1.3GB 权重装进手机后，本地实时推理第一次可用；下一步是把编排权交给用户。",
           y=Inches(6.93))
source(s, "来源：App Store 主流云端助手形态观察 · 本项目 iPhone 18 Pro Max 真机实测（2026-11-03）")

# ---------------- S4 解决方案 ----------------
s = new_slide(prs)
bg(s, PAPER)
kicker(s, "03 / SOLUTION")
pageno(s, 4)
headline(s, ["一句话，七步，", "日历里真的多了一条。"], y=Inches(0.84), size=30, width=Inches(11.8))
subline(s, "从断网到写入，全程发生在手机本地；每一步都可复核。", y=Inches(2.16), size=9.8)

rect(s, M, Inches(2.42), Inches(11.93), Inches(0.78), BLUE_BG)
text(s, M + Inches(0.22), Inches(2.51), Inches(1.4), Inches(0.18),
     [[("用户原话", 7.2, True, ORANGE, MONO)]], space_after=0)
text(s, M + Inches(0.22), Inches(2.70), Inches(11.3), Inches(0.40),
     [[("「家长会，明天下午三点，学校，约一小时」", 20, True, INK)]], space_after=0)

steps = [
    ("01", "飞行模式", "手机彻底断网"),
    ("02", "本地推理", "1.7B 模型在手机里"),
    ("03", "工具调用", "输出标准 tool_call JSON"),
    ("04", "schema 校验", "参数格式不对直接拒绝"),
    ("05", "系统确认", "用户点「允许」才执行"),
    ("06", "EventKit 写入", "日历里真的多一条"),
    ("07", "回读校验", "写不进去就如实报错"),
]
sx, sw = M, Inches(1.62)
for i, (num, title, detail) in enumerate(steps):
    if i:
        vrule(s, sx - Inches(0.10), Inches(3.58), Inches(0.40), color=HAIR)
    text(s, sx, Inches(3.55), sw, Inches(0.28),
         [[(num, 13, True, ORANGE, MONO)]], space_after=0)
    text(s, sx, Inches(3.87), sw, Inches(0.22),
         [[(title, 8.8, True, INK)]], space_after=0)
    text(s, sx, Inches(4.10), sw - Inches(0.05), Inches(0.34),
         [[(detail, 7.1, False, MUTED)]], space_after=0)
    sx += sw + Inches(0.08)
rule(s, M, Inches(4.48), Inches(11.93), color=HAIR)

features = [
    ("完全离线", "模型权重与推理都在手机，飞行模式可完整跑通。"),
    ("工具闭环", "不是聊天，是把事办成：日历 / 提醒真实写入系统。"),
    ("人确认", "写入前弹系统确认框，显示可读日期与过期警告。"),
    ("模型库 / 档位", "0.6B / 1.7B、4K–32K、四档速度，逐项标清代价。"),
]
fx, fw = M, Inches(2.85)
for i, (title, detail) in enumerate(features):
    text(s, fx, Inches(4.68), fw, Inches(0.24),
         [[(title, 11.5, True, INK)]], space_after=0)
    text(s, fx, Inches(4.96), fw - Inches(0.15), Inches(0.52),
         [[(detail, 7.6, False, MUTED)]], space_after=0, line_spacing=1.05)
    if i < 3:
        vrule(s, fx + fw - Inches(0.12), Inches(4.66), Inches(0.78), color=HAIR)
    fx += fw

rule(s, M, Inches(5.52), Inches(11.93), color=HAIR)
proof = [("13/13", "场景回归"), ("21.7s", "全套耗时"), ("1804 MB", "峰值内存"), ("42–79", "tok/s 场景解码")]
px = M
for i, (v, label) in enumerate(proof):
    text(s, px, Inches(5.66), Inches(2.75), Inches(0.32),
         [[(v, 18, True, ORANGE if i == 0 else INK)]], space_after=0)
    text(s, px, Inches(5.98), Inches(2.60), Inches(0.18),
         [[(label, 7.5, False, MUTED)]], space_after=0)
    if i < 3:
        vrule(s, px + Inches(2.82), Inches(5.66), Inches(0.42), color=HAIR)
    px += Inches(3.0)
conclusion(s, "断网也能把事办成——这是云端助手给不了的体验。", y=Inches(6.30))
text(s, M, Inches(6.62), Inches(11.8), Inches(0.22),
     [[("PIPL：用户数据不出设备，不收集、不存储对话内容。", 8.5, False, GREEN)]], space_after=0)
source(s, "来源：iOS 演示壳（EngineKit）真机流程 · 13/13 回归 · 2026-11-03")

# ---------------- S5 美高课程训练 ----------------
s = new_slide(prs)
bg(s, PAPER)
kicker(s, "04 / TRAINING")
pageno(s, 5)
headline(s, ["不追通用榜单，", "只在美高课程上用真题验收。"], y=Inches(0.84), size=29, width=Inches(11.8))
subline(s, "数据全部自建：真题转化 + 教师合成 + SymPy 符号验真；SFT19 训练中。", y=Inches(2.10), size=9.6)

stats = [
    ("21", "AP FRQ 真题", "80% 训练 / 20% holdout"),
    ("10M", "tokens 合成数据", "ap_calc 40% / precalc 20% / stats 15% / IELTS 25%"),
    ("110", "SymPy 抓出的违规", "300 条数值变式 0 错"),
    ("0/108", "AP Calc BC 基线", "改前真题得分"),
]
sx, sw = M, Inches(2.9)
for i, (v, label, note) in enumerate(stats):
    text(s, sx, Inches(2.42), sw, Inches(0.42),
         [[(v, 27, True, ORANGE)]], space_after=0)
    text(s, sx, Inches(2.88), sw, Inches(0.20),
         [[(label, 8.8, True, INK)]], space_after=0)
    text(s, sx, Inches(3.08), sw - Inches(0.12), Inches(0.34),
         [[(note, 6.9, False, MUTED)]], space_after=0)
    if i < 3:
        vrule(s, sx + sw - Inches(0.10), Inches(2.42), Inches(0.78), color=HAIR)
    sx += sw

pipeline = [
    ("01", "真题转化", "21 道 AP FRQ，逐题切题确认，80/20 划分"),
    ("02", "教师合成", "云端教师大模型 + 配比拼装，10M tokens"),
    ("03", "符号验真", "SymPy 对拍首轮抓 110 条违规，变式 0 错"),
    ("04", "SFT 训练", "1.7B 双卡 · WSD 学习率调度 · LR 消融完成"),
    ("05", "真题验收", "AP Calc BC holdout ≥85% 才进发布链"),
]
px, pw = M, Inches(2.30)
for i, (num, title, detail) in enumerate(pipeline):
    if i:
        vrule(s, px - Inches(0.09), Inches(3.66), Inches(0.72), color=HAIR)
    text(s, px, Inches(3.60), pw, Inches(0.22),
         [[(num, 9, True, LIGHT, MONO)]], space_after=0)
    text(s, px, Inches(3.82), pw, Inches(0.22),
         [[(title, 10.2, True, INK)]], space_after=0)
    text(s, px, Inches(4.05), pw - Inches(0.10), Inches(0.34),
         [[(detail, 7.0, False, MUTED)]], space_after=0)
    if num == "04":
        rect(s, px, Inches(4.35), Inches(1.15), Inches(0.21), PEACH_BG)
        text(s, px, Inches(4.38), Inches(1.15), Inches(0.16),
             [[("LR 消融完成", 6.2, True, ORANGE, MONO)]],
             align=PP_ALIGN.CENTER, space_after=0)
    px += pw + Inches(0.09)
rule(s, M, Inches(4.62), Inches(11.93), color=HAIR)

text(s, M, Inches(4.78), Inches(5.9), Inches(0.18),
     [[("已上线 / SFT17", 7.5, True, GREEN, MONO)]], space_after=0)
text(s, M, Inches(5.00), Inches(5.9), Inches(0.30),
     [[("2764 步 · eval 0.535", 15, True, INK)]], space_after=0)
text(s, M, Inches(5.34), Inches(5.9), Inches(0.22),
     [[("工具调用 90–97.5% · 真机峰值 1.9GB · 日期题 9/15", 8.3, False, MUTED)]],
     space_after=0)
rule(s, M, Inches(5.62), Inches(5.9), color=HAIR)
text(s, M, Inches(5.74), Inches(5.9), Inches(0.18),
     [[("在训 / SFT19 美高课程", 7.5, True, ORANGE, MONO)]], space_after=0)
text(s, M, Inches(5.96), Inches(5.9), Inches(0.22),
     [[("10M tokens 已合成 · AP Calc BC 0/108 基线 · 3 epochs 训练中", 8.3, True, INK)]],
     space_after=0)
text(s, M, Inches(6.20), Inches(5.9), Inches(0.22),
     [[("训练完成前不提前宣称提升。", 8.0, True, ORANGE)]], space_after=0)

fit_image(s, fig("V3-LR消融.png"), Inches(6.8), Inches(4.66), Inches(5.9), Inches(1.76))
text(s, Inches(6.80), Inches(6.46), Inches(5.9), Inches(0.18),
     [[("LR 消融：constant 收在 3.12；WSD 1000 步收在 3.07（单次消融，不宣称显著）",
        6.8, False, MUTED)]], space_after=0)
conclusion(s, "训练完成前不宣称提升；验收以 AP Calc BC 真题正确率为门禁。", y=Inches(6.90))
source(s, "来源：SFT17 评测报告 · SFT19 / LR 消融训练日志（2026-11-04 01:48）· AP Calc BC 私有真题基线")

# ---------------- S6 引擎与真机跑分 ----------------
s = new_slide(prs)
bg(s, PAPER)
kicker(s, "05 / ENGINE")
pageno(s, 6)
headline(s, ["同一套代码，", "0.6B / 1.7B 都装进 iPhone。"], y=Inches(0.84), size=29, width=Inches(11.8))
subline(s, "EngineKit 全 Swift 封装 llama.cpp；模型、上下文、速度档都可换，代价写在界面上。",
        y=Inches(2.10), size=9.6)

text(s, M, Inches(2.42), Inches(4.2), Inches(0.90),
     [[("61.1", 72, True, ORANGE)]], space_after=0, line_spacing=0.9)
text(s, M + Inches(2.55), Inches(2.63), Inches(1.7), Inches(0.30),
     [[("tok/s", 17, True, ORANGE)]], space_after=0)
text(s, M, Inches(3.56), Inches(4.3), Inches(0.22),
     [[("稳定解码 · 1.7B Q4_K_M · 18 Pro Max", 9, True, INK)]], space_after=0)
rule(s, M, Inches(3.48), Inches(4.1), color=HAIR)
text(s, M, Inches(3.98), Inches(4.2), Inches(0.45),
     [[("1.90", 32, True, INK), (" GB", 11, True, MUTED)]], space_after=0)
text(s, M, Inches(4.44), Inches(4.2), Inches(0.22),
     [[("峰值内存（4K 上下文）", 8.0, False, MUTED)]], space_after=0)
text(s, M, Inches(4.82), Inches(4.25), Inches(0.22),
     [[("4K / 8K / 16K / 32K", 9.0, True, INK, MONO)]], space_after=0)
text(s, M, Inches(5.06), Inches(4.25), Inches(0.34),
     [[("KV 约 0.44 / 0.88 / 1.75 / 3.5 GB；8GB 机型建议 ≤8K。", 7.6, False, MUTED)]],
     space_after=0)

# 真机六档表
tx, ty = Inches(5.25), Inches(2.42)
widths = [Inches(2.10), Inches(1.25), Inches(1.55), Inches(1.55)]
rows = [
    ("档位", "17 PM", "18 PM", "峰值(18)"),
    ("1.7B Q4_K_M", "38.5", "61.1", "1903 MB"),
    ("1.7B Q5_K_M", "34.2", "56.5", "2054 MB"),
    ("1.7B Q8_0", "27.3", "40.1", "2683 MB"),
    ("0.6B Q5_K_M", "86.9", "100.5", "1187 MB"),
    ("0.6B Q4_K_M", "89.0", "119.7", "1144 MB"),
    ("0.6B IQ4_XS", "96.7", "121.1", "1109 MB"),
]
for ri, row in enumerate(rows):
    yy = ty + Inches(0.33) + ri * Inches(0.40)
    if ri == 0:
        text(s, tx, ty, Inches(6.45), Inches(0.20),
             [[(row[0], 7.2, True, MUTED, MONO), ("    17 / 18 PM：稳定解码 tok/s · 峰值 MB", 6.2, False, LIGHT, MONO)]],
             space_after=0)
        rule(s, tx, ty + Inches(0.25), Inches(6.45), color=INK)
        continue
    if ri > 1:
        rule(s, tx, yy - Inches(0.06), Inches(6.45), color=HAIR)
    text(s, tx, yy, widths[0], Inches(0.24), [[(row[0], 9.2, True, INK)]], space_after=0)
    text(s, tx + widths[0], yy, widths[1], Inches(0.24),
         [[(row[1], 10, False, MUTED, MONO)]], align=PP_ALIGN.RIGHT, space_after=0)
    text(s, tx + widths[0] + widths[1], yy, widths[2], Inches(0.24),
         [[(row[2], 16, True, ORANGE, MONO)]], align=PP_ALIGN.RIGHT, space_after=0)
    text(s, tx + widths[0] + widths[1] + widths[2], yy + Inches(0.03), widths[3], Inches(0.20),
         [[(row[3], 6.6, False, MUTED, MONO)]], align=PP_ALIGN.RIGHT, space_after=0)

# 多 Agent 容量规划
rect(s, M, Inches(5.35), Inches(11.93), Inches(1.28), GREEN_BG)
text(s, M + Inches(0.22), Inches(5.43), Inches(6.0), Inches(0.18),
     [[("MULTI-AGENT CAPACITY / 规划，待实测", 7.2, True, ORANGE, MONO)]], space_after=0)
text(s, M + Inches(0.22), Inches(5.64), Inches(3.4), Inches(0.22),
     [[("8GB 机型", 8.5, True, INK)]], space_after=0)
text(s, M + Inches(0.22), Inches(5.86), Inches(3.5), Inches(0.44),
     [[("2–3 个 0.6B Agent 同时在线；再开就进入内存警戒。", 7.4, False, MUTED)]],
     space_after=0)
text(s, M + Inches(3.95), Inches(5.64), Inches(3.5), Inches(0.22),
     [[("12GB 机型", 8.5, True, INK)]], space_after=0)
text(s, M + Inches(3.95), Inches(5.86), Inches(3.5), Inches(0.44),
     [[("2 个 1.7B + 1 个 0.6B；组合跑分记录峰值与被终止次数。", 7.4, False, MUTED)]],
     space_after=0)
text(s, M + Inches(7.75), Inches(5.64), Inches(3.9), Inches(0.22),
     [[("OOM 门禁", 8.5, True, ORANGE)]], space_after=0)
text(s, M + Inches(7.75), Inches(5.86), Inches(3.9), Inches(0.44),
     [[("每次组合跑分都测「最多几个不 OOM」，超预算自动降档，不靠拍脑袋。", 7.4, False, MUTED)]],
     space_after=0)
conclusion(s, "18 Pro Max 上 1.7B 稳定 61.1 tok/s；同一套代码向下兼容 0.6B、向上预留多 Agent 预算。",
           y=Inches(6.86))
source(s, "口径：4 轮取后 3 轮均值 · 4K · 均衡档 · 峰值内存单轮最高；17 PM 为同协议对比。")

# ---------------- S7 测试①工具调用 ----------------
s = new_slide(prs)
bg(s, PAPER)
kicker(s, "06 / TEST 01")
pageno(s, 7)
headline(s, ["40 道工具题，", "30/30 训练分布全过。"], y=Inches(0.84), size=29, width=Inches(11.8))
subline(s, "命题书要求「用测试证明有没有用」——每次工具调用都落成 case 文件。", y=Inches(2.10), size=9.6)

fit_image(s, fig("V1-工具调用.png"), M, Inches(2.38), Inches(7.05), Inches(3.18))

rx = Inches(8.15)
text(s, rx, Inches(2.32), Inches(4.4), Inches(0.55),
     [[("100%", 40, True, ORANGE)]], space_after=0)
text(s, rx, Inches(2.90), Inches(4.4), Inches(0.22),
     [[("训练分布 30/30 全过", 9.2, True, INK)]], space_after=0)
rule(s, rx, Inches(3.22), Inches(4.1), color=HAIR)
text(s, rx, Inches(3.38), Inches(4.4), Inches(0.42),
     [[("90–97.5%", 24, True, INK)]], space_after=0)
text(s, rx, Inches(3.84), Inches(4.4), Inches(0.22),
     [[("schema 通过率（三档量化）", 9.0, True, INK)]], space_after=0)
rule(s, rx, Inches(4.14), Inches(4.1), color=HAIR)
text(s, rx, Inches(4.30), Inches(4.4), Inches(0.55),
     [[("13/13", 40, True, BLUE)]], space_after=0)
text(s, rx, Inches(4.88), Inches(4.4), Inches(0.22),
     [[("真机回归（含 1 条时间自检）", 9.0, True, INK)]], space_after=0)

rect(s, M, Inches(5.65), Inches(11.93), Inches(0.62), RGBColor(0xFA, 0xE2, 0xD6))
text(s, M + Inches(0.20), Inches(5.73), Inches(11.5), Inches(0.46),
     [[("10 道泛化题失分，逐条定位：相对日期没把握 / 把确认话当主路径。SFT19 已注入「今天」锚点修复。",
        8.3, True, INK)]], space_after=0)
text(s, M, Inches(6.36), Inches(11.8), Inches(0.22),
     [[("真机回归 13/13 · 21.7 秒 · 解码 42–79 tok/s · 峰值 1804 MB", 10.5, True, INK, MONO)]],
     space_after=0)
text(s, M, Inches(6.58), Inches(11.8), Inches(0.18),
     [[("解码为场景瞬时值，不是稳定跑分；稳定值见第 6 页。", 6.8, False, MUTED)]], space_after=0)
conclusion(s, "不是「感觉能用」，是逐题可复核。", y=Inches(6.90))
source(s, "来源：SFT17 评测报告 · 演示壳 Harness 13/13（2026-11-03）")

# ---------------- S8 测试②瞎编 ----------------
s = new_slide(prs)
bg(s, PEACH_BG)
kicker(s, "07 / TEST 02")
pageno(s, 8)
text(s, M, Inches(0.86), Inches(11.8), Inches(0.62),
     [[("它还会不会瞎编？", 42, True, INK)]], space_after=0)
text(s, M, Inches(1.72), Inches(11.4), Inches(0.26),
     [[("问 15 道日期题：改前全错，改后 9 道答对。", 10.5, False, MUTED)]], space_after=0)

text(s, M, Inches(2.15), Inches(5.6), Inches(1.35),
     [[("9/15", 100, True, ORANGE)]], space_after=0, line_spacing=0.85)
text(s, M, Inches(3.72), Inches(5.4), Inches(0.24),
     [[("日期题答对（改前 0/15）", 9.8, True, INK)]], space_after=0)
text(s, M, Inches(4.02), Inches(5.4), Inches(0.24),
     [[("还有 6 道会错，产品必须让人确认。", 9.0, True, ORANGE)]], space_after=0)

rect(s, Inches(6.60), Inches(1.86), Inches(6.02), Inches(3.35), WHITE_BG, line=HAIR, line_w=0.6)
fit_image(s, fig("V2-瞎编率.png"), Inches(6.78), Inches(1.98), Inches(5.66), Inches(3.05))
text(s, Inches(6.60), Inches(5.24), Inches(6.0), Inches(0.18),
     [[("日期题逐题对拍（n=15）", 6.8, False, MUTED, MONO)]], space_after=0)

stats = [
    ("−78%", "瞎编次数（相对日期）"),
    ("14→0", "生成问题（复读/截断/空答）"),
    ("12.29→5.42", "目标领域 PPL，越低越顺"),
]
sx = M
for i, (v, label) in enumerate(stats):
    color = ORANGE if i == 0 else INK
    text(s, sx, Inches(5.62), Inches(3.5), Inches(0.42),
         [[(v, 25, True, color)]], space_after=0)
    text(s, sx, Inches(6.04), Inches(3.4), Inches(0.22),
         [[(label, 7.8, False, MUTED)]], space_after=0)
    if i < 2:
        vrule(s, sx + Inches(3.65), Inches(5.62), Inches(0.55), color=HAIR)
    sx += Inches(3.85)
text(s, M, Inches(6.48), Inches(11.8), Inches(0.28),
     [[("训练把它从「全瞎编」拉到「六成能答对」，但没有归零——所以产品必须有确认和兜底。",
        11.5, True, ORANGE)]], space_after=0)
source(s, "来源：SFT17 评测报告 §四/§五 · 日期映射 15 题 · 同 Q8_0 档、同 256 max-tokens 对拍")

# ---------------- S9 风险与人的角色 ----------------
s = new_slide(prs)
bg(s, PAPER)
kicker(s, "08 / RISK & HUMAN")
pageno(s, 9)
headline(s, ["AI 判断错了，", "产品怎么办？"], y=Inches(0.84), size=29, width=Inches(11.8))
subline(s, "命题书完成重点：怎样提醒使用者、由谁确认和处理。", y=Inches(2.10), size=9.6)

cols = [M, Inches(4.05), Inches(10.05)]
text(s, cols[0], Inches(2.44), Inches(3.2), Inches(0.20),
     [[("风险", 7.5, True, ORANGE, MONO)]], space_after=0)
text(s, cols[1], Inches(2.44), Inches(5.8), Inches(0.20),
     [[("产品怎么提醒", 7.5, True, ORANGE, MONO)]], space_after=0)
text(s, cols[2], Inches(2.44), Inches(3.0), Inches(0.20),
     [[("谁确认 / 处理", 7.5, True, ORANGE, MONO)]], space_after=0)
rule(s, M, Inches(2.68), Inches(11.93), color=INK)

risks = [
    ("日期 / 事实幻觉", "占位符被 schema 拦截；结果卡标注「不确定」，不执行写入。", "使用者本人"),
    ("时间 / 地点写错", "系统确认框显示可读日期与过期警告；确认后才写入。", "使用者本人"),
    ("模型编造工具", "白名单拒绝，返回失败原因并记日志；用户可见失败。", "使用者本人"),
    ("模型答不上来", "明确说「不知道」，不硬编；结果卡保留原始输出。", "使用者本人"),
    ("导入未知 GGUF", "导入前免责：App 仅提供本地推理环境，不分发模型；需确认许可。", "使用者本人"),
]
yy = Inches(2.84)
for i, (risk, how, who) in enumerate(risks):
    if i:
        rule(s, M, yy - Inches(0.08), Inches(11.93), color=HAIR)
    text(s, cols[0], yy, Inches(3.2), Inches(0.44),
         [[(risk, 9.5, True, INK)]], space_after=0)
    text(s, cols[1], yy, Inches(5.8), Inches(0.44),
         [[(how, 8.2, False, MUTED)]], space_after=0)
    text(s, cols[2], yy, Inches(2.6), Inches(0.44),
         [[(who, 8.2, True, INK)]], space_after=0)
    yy += Inches(0.52)

rect(s, M, Inches(5.55), Inches(11.93), Inches(1.18), PEACH_BG)
text(s, M + Inches(0.22), Inches(5.65), Inches(11.4), Inches(0.30),
     [[("红线：AI 只提供建议与结构化结果，最终决定权永远在人。", 18, True, INK)]],
     space_after=0)
text(s, M + Inches(0.22), Inches(6.08), Inches(11.4), Inches(0.34),
     [[("App Store 合规：不下载可执行代码 · 模型仅本地推理 · 权限最小化 · 隐私政策 · 无账号与统计 SDK",
        7.8, False, MUTED)]], space_after=0)
text(s, M + Inches(0.22), Inches(6.30), Inches(11.4), Inches(0.18),
     [[("权限只在工具执行时申请；拒绝授权则功能降级，不影响本地对话。", 7.2, False, MUTED)]],
     space_after=0)
text(s, M, Inches(6.86), Inches(11.9), Inches(0.22),
     [[("当前限制（诚实披露）：1.7B 复杂推理有限 · 工具只有日历/提醒 · Android 未覆盖 · 美高课程训练中 · 日期仍有 6/15 错",
        6.8, False, MUTED)]], space_after=0)
source(s, "来源：ToolKit 白名单 / schema 实现 · 13 条回归用例 · 日期评测 15 题（SFT17 报告）· App Store Review Guidelines 2.5.2 / 5.1.1")

# ---------------- S10 团队 / AI 工具 / 路线 ----------------
s = new_slide(prs)
bg(s, PAPER)
kicker(s, "09 / TEAM & NEXT")
pageno(s, 10)
headline(s, ["一个人 + 一套 AI 工具链，", "把全栈跑通。"], y=Inches(0.84), size=29, width=Inches(11.8))
subline(s, "命题书硬性覆盖项 + 接下来的路线；训练队列与发布门禁都写进仓库。", y=Inches(2.10), size=9.6)

text(s, M, Inches(2.42), Inches(7.1), Inches(0.20),
     [[("团队分工（按实际填写）", 7.5, True, ORANGE, MONO)]], space_after=0)
team = [
    "引擎运行时（EngineKit）：＿＿＿＿＿＿＿＿＿＿",
    "模型训练与数据合成：＿＿＿＿＿＿＿＿＿＿",
    "iOS App 与演示：＿＿＿＿＿＿＿＿＿＿",
    "评测与回归：＿＿＿＿＿＿＿＿＿＿",
    "产品与测试：＿＿＿＿＿＿＿＿＿＿",
]
yy = Inches(2.66)
for line in team:
    text(s, M, yy, Inches(7.1), Inches(0.20), [[(line, 8.6, False, INK)]], space_after=0)
    yy += Inches(0.26)

text(s, M, Inches(4.10), Inches(7.1), Inches(0.20),
     [[("AI 工具使用说明", 7.5, True, ORANGE, MONO)]], space_after=0)
ai_lines = [
    "训练数据：云端教师大模型合成 + SymPy 后验 + 锚点/格式质检",
    "真题转化：官方 CodeBuddy CLI（云端大模型）逐题切题与评分标准转写",
    "开发辅助：编码/文档 AI 协作；对话与提示词可导出复查",
]
yy = Inches(4.33)
for line in ai_lines:
    text(s, M, yy, Inches(7.1), Inches(0.20), [[(line, 8.0, False, MUTED)]], space_after=0)
    yy += Inches(0.24)

text(s, M, Inches(5.15), Inches(7.1), Inches(0.20),
     [[("第三方资源", 7.5, True, ORANGE, MONO)]], space_after=0)
third = [
    "llama.cpp（MIT）· Qwen3 开源模型（Apache 2.0）",
    "iOS EventKit / SwiftUI 系统框架 · 公开中文语料",
]
yy = Inches(5.38)
for line in third:
    text(s, M, yy, Inches(7.1), Inches(0.20), [[(line, 8.0, False, MUTED)]], space_after=0)
    yy += Inches(0.24)
text(s, M, Inches(5.95), Inches(7.1), Inches(0.22),
     [[("模型口径：基于 Qwen3 继续训练，不自称自研；提交物 = 10 页 PPT + ≤8 分钟真机 Demo。",
        7.6, True, INK)]], space_after=0)

# 路线
rx = Inches(8.05)
text(s, rx, Inches(2.42), Inches(4.5), Inches(0.20),
     [[("路线（已实现 / 进行中 / 规划）", 7.5, True, ORANGE, MONO)]], space_after=0)
roadmap = [
    ("01", "SFT19 美高课程训练", "训练中；AP Calc BC 0/108 基线，3 epochs"),
    ("02", "量化 + 真题验收", "holdout ≥85% 才进发布链"),
    ("03", "TestFlight 分发", "模型库/导入/关于与隐私已具备"),
    ("04", "本地 DIY 多 Agent 编排", "规划中；Planner + Worker + Verifier，内存预算 + OOM 门禁"),
    ("05", "Android 端", "规划中，端侧多平台"),
]
yy = Inches(2.70)
for i, (num, title, detail) in enumerate(roadmap):
    if i:
        rule(s, rx, yy - Inches(0.07), Inches(4.55), color=HAIR)
    if num == "04":
        rect(s, rx - Inches(0.14), yy - Inches(0.02), Inches(0.06), Inches(0.52), ORANGE)
    text(s, rx, yy, Inches(0.45), Inches(0.22),
         [[(num, 9.5, True, ORANGE if num == "04" else LIGHT, MONO)]], space_after=0)
    text(s, rx + Inches(0.48), yy - Inches(0.02), Inches(4.1), Inches(0.22),
         [[(title, 9.2, True, INK)]], space_after=0)
    text(s, rx + Inches(0.48), yy + Inches(0.20), Inches(4.05), Inches(0.30),
         [[(detail, 7.0, False, MUTED)]], space_after=0)
    yy += Inches(0.66)

rect(s, M, Inches(6.22), Inches(11.93), Inches(0.66), BLUE_BG)
text(s, M + Inches(0.22), Inches(6.30), Inches(11.4), Inches(0.20),
     [[("GitHub：github.com/fanyifan090409-dev/mobile-llm-engine · 13 条回归 / 双机跑分 / 训练日志随仓库提供",
        7.2, False, MUTED, MONO)]], space_after=0)
text(s, M + Inches(0.22), Inches(6.53), Inches(11.4), Inches(0.24),
     [[("把 AI 从云端搬进口袋，把编排权交给学生。", 12.5, True, ORANGE)]], space_after=0)
source(s, "来源：项目仓库 · 训练/评测日志 · 第三方许可证（MIT / Apache 2.0）")

prs.save(OUT)
print("saved", OUT, "slides", len(prs.slides))
