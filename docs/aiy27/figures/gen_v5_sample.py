#!/usr/bin/env python3
"""AIY 27 PPT v5 样张：编辑式「证据照片 + 象牙白抽象面板」。
只生成 2 页（封面 + 拍照做题），方向确认后再批量。
用法：.venv/bin/python docs/aiy27/figures/gen_v5_sample.py
"""
import os

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "AIY27-PPT-v5-sample.pptx")
ASSETS = os.path.join(HERE, "v5-assets")

PAPER = RGBColor(0xF3, 0xF0, 0xE8)
INK = RGBColor(0x18, 0x17, 0x15)
MUTED = RGBColor(0x6E, 0x68, 0x5D)
HAIR = RGBColor(0xD8, 0xD1, 0xC3)
BLUE = RGBColor(0x4F, 0x72, 0x96)
BLUE_LT = RGBColor(0xA9, 0xBC, 0xCC)
TEAL = RGBColor(0x6E, 0x9C, 0x96)
GREEN = RGBColor(0x7F, 0xA0, 0x7A)
RUST = RGBColor(0xB5, 0x52, 0x39)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SERIF = "Georgia"
SONG = "PingFang SC"
SANS = "PingFang SC"
MONO = "Menlo"

SW, SH = Inches(13.333), Inches(7.5)
M = Inches(0.75)


def _set_font(run, size, bold=False, color=INK, name=SANS, italic=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    if italic:
        run.font.italic = True
    run.font.color.rgb = color
    run.font.name = name
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        e = rPr.find(qn(tag))
        if e is None:
            e = rPr.makeelement(qn(tag), {})
            rPr.append(e)
        e.set("typeface", name)


def txt(slide, x, y, w, h, paras, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
        line_spacing=1.0, space_after=0):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        p.line_spacing = line_spacing
        runs = para if isinstance(para, list) else [para]
        for run in runs:
            text, size, bold, color = run[:4]
            name = run[4] if len(run) > 4 else SANS
            italic = run[5] if len(run) > 5 else False
            r = p.add_run()
            r.text = text
            _set_font(r, size, bold, color, name, italic)
    return tb


def rect(slide, x, y, w, h, fill=None, line=None, line_w=0.75):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w)
    shp.shadow.inherit = False
    return shp


def line(slide, x1, y1, x2, y2, color=HAIR, width=0.75):
    from pptx.enum.shapes import MSO_CONNECTOR
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    c.line.color.rgb = color
    c.line.width = Pt(width)
    return c


def circle_outline(slide, x, y, d, color=BLUE_LT, width=0.8):
    shp = slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, d, d)
    shp.fill.background()
    shp.line.color.rgb = color
    shp.line.width = Pt(width)
    shp.shadow.inherit = False
    return shp


def slide_base(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, SW, SH, PAPER)
    return s


def kicker(s, label, page=None, total=10, x=M):
    rect(s, x, Inches(0.50), Inches(0.09), Inches(0.09), RUST)
    txt(s, x + Inches(0.17), Inches(0.47), Inches(8.0), Inches(0.20),
        [[(label, 7.5, True, RUST, MONO)]])
    if page:
        txt(s, SW - M - Inches(1.0), Inches(0.47), Inches(1.0), Inches(0.20),
            [[(f"{page:02d} / {total:02d}", 7.5, False, MUTED, MONO)]],
            align=PP_ALIGN.RIGHT)


def source(s, text):
    txt(s, M, Inches(7.14), Inches(11.8), Inches(0.20),
        [[(text, 6.8, False, MUTED, MONO)]])


def swatches(s, x, y):
    colors = [RGBColor(0x0A, 0x84, 0xFF), RGBColor(0x30, 0xD5, 0xC8),
              RGBColor(0x34, 0xC7, 0x59), RGBColor(0xC9, 0xD1, 0xDE)]
    for i, c in enumerate(colors):
        rect(s, x + Inches(0.18) * i, y, Inches(0.13), Inches(0.13), c)


def cover(prs):
    s = slide_base(prs)
    # 左：真机截图，直接贴边，不加手机壳/阴影
    photo_w = Inches(4.6)
    s.shapes.add_picture(os.path.join(ASSETS, "cover-device-v5.png"),
                         0, 0, width=photo_w, height=SH)
    txt(s, Inches(0.22), Inches(7.16), Inches(4.1), Inches(0.16),
        [[("REAL DEVICE / iPhone 18 Pro Max", 6.2, False, MUTED, MONO)]])

    # 右：编辑面板
    x = Inches(5.15)
    kicker(s, "AIY 27 / FIELD REPORT", 1, x=x)
    # 抽象记忆：跑分圆环 + 四轮刻度 + 三条模型色带（右移，避开标题）
    circle_outline(s, Inches(10.55), Inches(0.55), Inches(2.35), BLUE_LT, 0.9)
    for i in range(4):
        color = BLUE if i < 3 else HAIR
        rect(s, Inches(10.95) + Inches(0.20) * i, Inches(1.82), Inches(0.045),
             Inches(0.26), color)
    for i, (w, c) in enumerate([(1.75, BLUE), (1.45, TEAL), (1.10, GREEN)]):
        rect(s, Inches(11.05), Inches(2.28) + Inches(0.15) * i, Inches(w),
             Inches(0.05), c)

    txt(s, x, Inches(1.18), Inches(5.1), Inches(1.7),
        [[("POCKET", 34, False, INK, SERIF)],
         [("INTELLIGENCE", 34, False, INK, SERIF)]], line_spacing=1.0)
    txt(s, x, Inches(2.62), Inches(5.2), Inches(0.55),
        [[("口袋里的 Agent 实验室", 23, True, INK, SONG)]])
    txt(s, x, Inches(3.14), Inches(5.2), Inches(0.30),
        [[("A local-first agent lab on a phone", 12.5, False, MUTED, SERIF, True)]])
    txt(s, x, Inches(3.62), Inches(5.4), Inches(0.60),
        [[("数据不出设备 · 美高课程特训\n日历 / 提醒真可用 · 一台 iPhone 跑起来", 9.8, False, MUTED, SANS)]],
        line_spacing=1.45)
    txt(s, x, Inches(4.48), Inches(5.4), Inches(0.30),
        [[("不是云端助手的缩小版，\n而是学生自己的本地 Agent 工作台。", 10.5, True, RUST, SANS)]],
        line_spacing=1.45)

    # 三项硬指标
    stats = [("61.1", "tok/s", "18 Pro Max · 1.7B Q4_K_M"),
             ("0", "上传", "推理全程本机"),
             ("16/16", "真机自检", "13 场景 + 3 语音")]
    for i, (value, unit, note) in enumerate(stats):
        sx = x + Inches(1.78) * i
        txt(s, sx, Inches(5.42), Inches(1.7), Inches(0.46),
            [[(value, 22, False, INK, SERIF), (" " + unit, 7.5, False, RUST, MONO)]])
        txt(s, sx, Inches(5.90), Inches(1.7), Inches(0.20),
            [[(note, 7.0, False, MUTED, SANS)]])

    line(s, x, Inches(6.40), SW - M, Inches(6.40), HAIR, 0.6)
    txt(s, x, Inches(6.58), Inches(7.0), Inches(0.22),
        [[("团队：____________    演示人：____________    GitHub：mobile-llm-engine",
           8.2, False, MUTED, MONO)]])
    txt(s, x, Inches(7.14), Inches(7.3), Inches(0.20),
        [[("模型口径：基于 Qwen3 继续训练 · 推理底座 llama.cpp（MIT）· 数字来自本机训练与真机日志",
           6.8, False, MUTED, MONO)]])
    swatches(s, Inches(11.75), Inches(6.62))


def math_page(prs):
    s = slide_base(prs)
    kicker(s, "06 / FIELD NOTE — MATH MODE", 6)
    txt(s, M, Inches(0.80), Inches(6.2), Inches(1.1),
        [[("PHOTO IN,", 24, False, INK, SERIF)],
         [("PROOF OUT", 24, False, INK, SERIF)]], line_spacing=1.0)
    txt(s, M, Inches(1.66), Inches(6.3), Inches(0.60),
        [[("拍照做题：公式识别 → 本地 CAS → 可复核答案。", 17, True, INK, SONG)]])
    txt(s, M, Inches(2.14), Inches(6.2), Inches(0.30),
        [[("Texo 20M 公式识别 + math.js，在手机上完成「看图 → 题意 → 计算」。", 9.2, False, MUTED, SANS)]])

    txt(s, M, Inches(2.66), Inches(3.0), Inches(0.18),
        [[("INPUT / 相册照片（示例）", 6.8, True, RUST, MONO)]])
    s.shapes.add_picture(os.path.join(ASSETS, "formula-input-v5.png"),
                         M + Inches(0.30), Inches(2.92), width=Inches(4.05))

    txt(s, M, Inches(4.52), Inches(3.0), Inches(0.18),
        [[("OCR / LaTeX", 6.8, True, RUST, MONO)]])
    txt(s, M, Inches(4.74), Inches(6.0), Inches(0.24),
        [[("\\lim_{x\\rarr0}\\frac{\\sin x}{x}", 10.5, False, INK, MONO)]])

    txt(s, M, Inches(5.12), Inches(6.0), Inches(0.26),
        [[("题意：", 8.5, False, MUTED, SANS),
          ("求 ((sin(x))/(x)) 在 x→0 时的极限。", 11, True, INK, SANS)]])
    txt(s, M, Inches(5.58), Inches(1.2), Inches(0.70),
        [[("1", 40, False, RUST, SERIF)]])
    txt(s, M + Inches(0.62), Inches(5.86), Inches(3.4), Inches(0.20),
        [[("math.js · 本机计算", 7.5, False, MUTED, MONO)]])
    txt(s, M, Inches(6.58), Inches(6.2), Inches(0.30),
        [[("数学段单独切 SFT27e；助理段仍用领队 + 工人。", 8.5, False, MUTED, SANS)]])

    # 右：抽象标记来自公式本身（分数线 / 根号式折线 / 极限逼近）
    rx = Inches(7.65)
    line(s, rx, Inches(1.12), rx + Inches(2.9), Inches(1.12), INK, 1.0)
    line(s, rx, Inches(1.32), rx + Inches(2.9), Inches(1.32), INK, 0.6)
    line(s, rx, Inches(1.74), rx + Inches(0.10), Inches(1.74), TEAL, 1.0)
    line(s, rx + Inches(0.10), Inches(1.74), rx + Inches(0.42), Inches(1.42), TEAL, 1.0)
    line(s, rx + Inches(0.42), Inches(1.42), rx + Inches(0.90), Inches(1.42), TEAL, 1.0)
    for i, c in enumerate([BLUE, BLUE, RUST, BLUE, BLUE]):
        rect(s, rx + Inches(2.25) + Inches(0.16) * i, Inches(1.52), Inches(0.045),
             Inches(0.30), c)

    stats = [("58/69", "数学端到端", "84.1% · SFT27e v5"),
             ("69/69", "工具发射", "schema 全通过"),
             ("186ms", "真机识别（热）", "18 Pro Max"),
             ("18/18", "Mac 对拍", "与 Python 逐字一致")]
    for i, (value, label, note) in enumerate(stats):
        col, row = i % 2, i // 2
        sx = rx + Inches(2.25) * col
        sy = Inches(2.58) + Inches(1.02) * row
        txt(s, sx, sy, Inches(2.1), Inches(0.46),
            [[(value, 23, False, INK, SERIF)]])
        txt(s, sx, sy + Inches(0.46), Inches(2.1), Inches(0.20),
            [[(label, 8.5, True, INK, SANS)]])
        txt(s, sx, sy + Inches(0.66), Inches(2.1), Inches(0.20),
            [[(note, 7.2, False, MUTED, SANS)]])

    line(s, rx, Inches(5.02), SW - M, Inches(5.02), HAIR, 0.6)
    txt(s, rx, Inches(5.18), Inches(4.9), Inches(0.60),
        [[("一张照片，三个本机步骤：\n识别公式 → 转成题意 → 调用 CAS。", 10, False, MUTED, SANS)]],
        line_spacing=1.45)
    txt(s, rx, Inches(6.05), Inches(4.9), Inches(0.30),
        [[("没有网络请求，也没有把题目发给云端。", 10.5, True, RUST, SANS)]])
    source(s, "来源：Texo 18 图对拍（2026-11-09）· SFT27e 69 题端到端评测 · iPhone 18 Pro Max 真机自检")


def main():
    prs = Presentation()
    prs.slide_width = SW
    prs.slide_height = SH
    cover(prs)
    math_page(prs)
    prs.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
