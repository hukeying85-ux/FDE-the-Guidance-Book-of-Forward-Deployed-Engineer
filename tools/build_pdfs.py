#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build two designed Chinese PDFs from this repository's Markdown sources.

Usage:
    FDE_ASSETS=/home/user/assets python3 tools/build_pdfs.py

Assets expected in FDE_ASSETS/fonts (static instances of Google Fonts):
    NotoSansSC-Regular.ttf, NotoSansSC-Bold.ttf,
    NotoSerifSC-Regular.ttf, NotoSerifSC-Bold.ttf, JetBrainsMono-Regular.ttf
Assets expected in FDE_ASSETS:
    cover_book.png, cover_synthesis.png
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import markdown
from bs4 import BeautifulSoup, NavigableString, Tag
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    HRFlowable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents
import reportlab.lib.textsplit as _textsplit
import reportlab.platypus.paragraph as _rlparagraph

# Chinese full-width punctuation that ReportLab's Japanese kinsoku set omits.
_EXTRA_NO_START = "：；，？！、。”’…·％‰"
_textsplit.ALL_CANNOT_START += _EXTRA_NO_START
_rlparagraph.ALL_CANNOT_START += _EXTRA_NO_START

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(os.environ.get("FDE_ASSETS", "/home/user/assets"))
FONTS = ASSETS / "fonts"
OUT_DIR = ROOT

# --------------------------------------------------------------------------
# Palette & geometry
# --------------------------------------------------------------------------
INK = colors.HexColor("#1D2B3A")
NAVY = colors.HexColor("#122B45")
TEAL = colors.HexColor("#2C6E6B")
GOLD = colors.HexColor("#C39A4A")
GOLD_DARK = colors.HexColor("#8A6520")
GOLD_PALE = colors.HexColor("#E4D2A6")
MUTED = colors.HexColor("#728092")
PAPER = colors.HexColor("#FCFBF7")
PAPER_TINT = colors.HexColor("#F4F1E8")
RULE = colors.HexColor("#DCD5C5")
WHITE = colors.white

PW, PH = 176 * mm, 250 * mm
LM = RM = 22 * mm
FW = PW - LM - RM
FRAME = Frame(LM, 20 * mm, FW, PH - 42 * mm, id="body",
              leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

DATE = "2026-11-02"

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
def register_fonts() -> None:
    files = {
        "Sans": "NotoSansSC-Regular.ttf",
        "SansBold": "NotoSansSC-Bold.ttf",
        "Serif": "NotoSerifSC-Regular.ttf",
        "SerifBold": "NotoSerifSC-Bold.ttf",
        "Mono": "JetBrainsMono-Regular.ttf",
    }
    for name, fn in files.items():
        path = FONTS / fn
        if not path.exists():
            raise SystemExit(f"Missing font: {path}\nRun tools/prepare_fonts.py first.")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="SansBold",
                                  italic="Sans", boldItalic="SansBold")
    pdfmetrics.registerFontFamily("Serif", normal="Serif", bold="SerifBold",
                                  italic="Serif", boldItalic="SerifBold")
    pdfmetrics.registerFontFamily("Mono", normal="Mono", bold="Mono",
                                  italic="Mono", boldItalic="Mono")


def S(name, **kw) -> ParagraphStyle:
    base = dict(fontName="Sans", fontSize=10.2, leading=18.2,
                textColor=INK, wordWrap="CJK", allowWidows=0, allowOrphans=0)
    base.update(kw)
    return ParagraphStyle(name, **base)


ST = {
    "body": S("Body", firstLineIndent=20.4, alignment=TA_JUSTIFY, spaceAfter=5.2),
    "body_noindent": S("BodyNoIndent", alignment=TA_JUSTIFY, spaceAfter=5.2),
    "small": S("Small", fontSize=8.5, leading=13.5, textColor=MUTED),
    "small_center": S("SmallCenter", fontSize=8.5, leading=13.5,
                      textColor=MUTED, alignment=TA_CENTER),
    "h2": S("H2", fontName="SerifBold", fontSize=15.2, leading=23,
            textColor=NAVY, spaceBefore=11, spaceAfter=7, keepWithNext=1,
            firstLineIndent=0, alignment=TA_LEFT),
    "h3": S("H3", fontName="SansBold", fontSize=11.4, leading=18,
            textColor=TEAL, spaceBefore=9, spaceAfter=4, keepWithNext=1,
            firstLineIndent=0),
    "list": S("ListItem", fontSize=9.9, leading=16.8, leftIndent=17,
              firstLineIndent=-10, spaceAfter=3.2, alignment=TA_JUSTIFY),
    "quote": S("Quote", fontName="Serif", fontSize=10.0, leading=17.2,
               textColor=colors.HexColor("#3A4A5B"), alignment=TA_JUSTIFY),
    "quote_small": S("QuoteSmall", fontName="Serif", fontSize=9.6,
                     leading=16.2, textColor=colors.HexColor("#3A4A5B"),
                     alignment=TA_JUSTIFY),
    "chapter_num": S("ChapterNum", fontName="SerifBold", fontSize=52,
                     leading=56, textColor=GOLD_PALE, firstLineIndent=0),
    "chapter_title": S("ChapterTitle", fontName="SerifBold", fontSize=25,
                       leading=34, textColor=NAVY, firstLineIndent=0,
                       spaceBefore=2, spaceAfter=7, keepWithNext=1),
    "kicker": S("Kicker", fontSize=8.6, leading=13, textColor=GOLD_DARK,
                firstLineIndent=0, spaceAfter=4),
    "label": S("Label", fontName="SansBold", fontSize=9.2, leading=14,
               textColor=NAVY, firstLineIndent=0, spaceBefore=6, spaceAfter=4),
    "front_title": S("FrontTitle", fontName="SerifBold", fontSize=22,
                     leading=30, textColor=NAVY, firstLineIndent=0,
                     spaceAfter=12),
    "front_sub": S("FrontSub", fontName="Serif", fontSize=12, leading=20,
                   textColor=MUTED, firstLineIndent=0, spaceAfter=8),
    "half_title": S("HalfTitle", fontName="SerifBold", fontSize=26,
                    leading=38, textColor=NAVY, firstLineIndent=0,
                    alignment=TA_CENTER, spaceAfter=10),
    "half_eng": S("HalfEng", fontSize=9, leading=15, textColor=GOLD_DARK,
                  firstLineIndent=0, alignment=TA_CENTER, spaceAfter=6),
    "toc0": S("TOC0", fontName="SansBold", fontSize=10.3, leading=21,
              textColor=NAVY, firstLineIndent=0, spaceBefore=7,
              linkUnderline=0),
    "toc1": S("TOC1", fontSize=9, leading=15.5, textColor=INK,
              leftIndent=17, firstLineIndent=0, linkUnderline=0),
    "th": S("TableHead", fontName="SansBold", fontSize=8.3, leading=12.5,
            textColor=WHITE, firstLineIndent=0, alignment=TA_LEFT),
    "td": S("TableCell", fontSize=8.3, leading=12.6, textColor=INK,
            firstLineIndent=0, alignment=TA_LEFT),
    "code": S("Code", fontName="Mono", fontSize=8.2, leading=12.5,
              textColor=colors.HexColor("#8A4D2A"), firstLineIndent=0),
}


def esc(s: str) -> str:
    return xml_escape(s)


def esc_attr(s: str) -> str:
    return xml_escape(s, {'"': "&quot;", "'": "&apos;"})


def break_identifiers(text: str) -> str:
    """Give long ASCII identifiers (repo names, paths) sane break points."""
    def repl(m):
        token = m.group(0)
        if len(token) <= 24 or not re.search(r"[/_-]", token):
            return token
        parts = re.split(r"(?<=[/_-])", token)
        out, cur = "", ""
        for p in parts:
            if cur and len(cur) + len(p) > 22:
                out += cur + "<br/>"
                cur = p
            else:
                cur += p
        return out + cur
    return re.sub(r"[A-Za-z0-9][A-Za-z0-9/_\-.]*", repl, text)


def inline_html(node) -> str:
    """Convert a BeautifulSoup node into ReportLab's mini-HTML."""
    if isinstance(node, NavigableString):
        return break_identifiers(esc(re.sub(r"\s+", " ", str(node))))
    if not isinstance(node, Tag):
        return ""
    name = node.name.lower()
    inner = "".join(inline_html(c) for c in node.children)
    if name in ("strong", "b"):
        return f"<b>{inner}</b>"
    if name in ("em", "i"):
        return f"<i>{inner}</i>"
    if name == "code":
        return f'<font name="Mono" size="8.4" color="#8A4D2A">{inner}</font>'
    if name in ("a", "link"):
        href = node.get("href", "")
        if not href:
            return inner
        return (f'<link href="{esc_attr(href)}" color="#8A6520" '
                f'underline="0">{inner}</link>')
    if name == "br":
        return "<br/>"
    if name == "img":
        return ""
    return inner


def plain(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


# --------------------------------------------------------------------------
# Flowables & document template
# --------------------------------------------------------------------------
class PageMarker(Flowable):
    """Zero-height marker: tells the canvas what chrome to draw on this page."""
    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.width = 0
        self.height = 0

    def wrap(self, *args):
        return (0, 0)

    def draw(self):
        pass


class BookDocTemplate(BaseDocTemplate):
    def __init__(self, filename, cfg, **kw):
        super().__init__(filename, pagesize=(PW, PH),
                         leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
                         title=cfg["meta_title"], author=cfg["meta_author"],
                         subject=cfg["meta_subject"], creator="Arena FDE PDF Kit",
                         keywords=cfg["meta_keywords"], **kw)
        self.cfg = cfg
        self._state = {"kind": "cover"}
        self._seq = 0
        self.addPageTemplates([PageTemplate(id="main", frames=[FRAME])])

    def beforeDocument(self):
        self._state = {"kind": "cover"}
        self._seq = 0

    def afterFlowable(self, flowable):
        if isinstance(flowable, PageMarker):
            self._state["kind"] = flowable.kind
            return
        heading = getattr(flowable, "_heading", None)
        if not heading:
            return
        toc_level, outline_level, text = heading
        key = f"sec-{self._seq:05d}"
        self._seq += 1
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(text, key, level=outline_level,
                                  closed=(outline_level > 0))
        if toc_level is not None:
            self.notify("TOCEntry", (toc_level, esc(text), self.page, key))

    def afterPage(self):
        draw_chrome(self.canv, self.page, self._state, self.cfg)


def draw_tracked(c, x, y, text, font, size, color, spacing):
    """Canvas has no public setCharSpace; use a text object."""
    t = c.beginText(x, y)
    t.setFont(font, size)
    t.setFillColor(color)
    t.setCharSpace(spacing)
    t.textOut(text)
    c.drawText(t)


def fade_band(c, y0, y1, max_alpha, steps=28, top=True):
    """Soft vertical darkening without a visible hard edge."""
    h = (y1 - y0) / steps
    c.setFillColor(colors.HexColor("#07121F"))
    for i in range(steps):
        frac = (i + 1) / steps if top else (steps - i) / steps
        c.setFillAlpha(max_alpha * frac)
        c.rect(0, y0 + i * h, PW, h + 0.3, fill=1, stroke=0)
    c.setFillAlpha(1)


def draw_cover(c, cfg):
    c.saveState()
    art = cfg["cover_art"]
    if art.exists():
        c.drawImage(ImageReader(str(art)), 0, 0, width=PW, height=PH)
    fade_band(c, PH * 0.42, PH, 0.34, top=True)
    fade_band(c, 0, 46 * mm, 0.42, top=False)

    # Top eyebrow
    draw_tracked(c, LM, PH - 30 * mm, cfg["eyebrow"],
                 "Sans", 8.2, GOLD_PALE, 1.6)

    # Gold hairline
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(LM, PH - 35 * mm, LM + 30 * mm, PH - 35 * mm)

    y = PH - 68 * mm
    for line, size, font, color, gap in cfg["cover_title_lines"]:
        c.setFont(font, size)
        c.setFillColor(color)
        c.drawString(LM, y, line)
        y -= gap * mm
    y -= 3 * mm
    c.setFont("Sans", 11.2)
    c.setFillColor(colors.HexColor("#E5E9EE"))
    c.drawString(LM, y, cfg["cover_sub"])
    y -= 8 * mm
    draw_tracked(c, LM, y, cfg["cover_eng"],
                 "Sans", 8.2, GOLD_PALE, 1.3)
    y -= 8 * mm
    c.setStrokeColor(colors.HexColor("#6E7B88"))
    c.setLineWidth(0.5)
    c.line(LM, y, PW - LM, y)

    # Bottom block
    c.setFont("Sans", 9.5)
    c.setFillColor(colors.HexColor("#DDE4EB"))
    c.drawString(LM, 30 * mm, cfg["cover_author"])
    c.drawString(LM, 24 * mm, cfg["cover_edition"])
    c.setFont("Sans", 7.8)
    c.setFillColor(colors.HexColor("#93A0AE"))
    c.drawString(LM, 17 * mm, cfg["cover_note"])
    c.drawRightString(PW - LM, 17 * mm, cfg["cover_footer"])
    c.restoreState()


def draw_chrome(c, page, state, cfg):
    c.saveState()
    if page == 1:
        draw_cover(c, cfg)
        c.restoreState()
        return
    kind = state.get("kind", "body")
    if kind == "chapter":
        c.setFillColor(GOLD)
        c.rect(0, 0, 2.4 * mm, PH, fill=1, stroke=0)
    if kind == "body":
        c.setStrokeColor(RULE)
        c.setLineWidth(0.45)
        c.line(LM, PH - 16.5 * mm, PW - RM, PH - 16.5 * mm)
        c.setFont("Sans", 7.6)
        c.setFillColor(MUTED)
        c.drawString(LM, PH - 13.6 * mm, cfg["header_left"])
        c.drawRightString(PW - RM, PH - 13.6 * mm, cfg["header_right"])
        c.setFillColor(GOLD)
        c.rect(LM - 3 * mm, PH - 16.8 * mm, 8 * mm, 0.7, fill=1, stroke=0)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.45)
    c.line(LM, 17 * mm, PW - RM, 17 * mm)
    c.setFont("Sans", 7.6)
    c.setFillColor(MUTED)
    c.drawString(LM, 12.2 * mm, cfg["footer_left"])
    c.setFillColor(GOLD_DARK)
    c.drawCentredString(PW / 2, 12.2 * mm, f"— {page} —")
    c.setFillColor(MUTED)
    c.drawRightString(PW - RM, 12.2 * mm, cfg["footer_right"])
    c.restoreState()


# --------------------------------------------------------------------------
# Markdown -> reportlab flowables
# --------------------------------------------------------------------------
def rule(width="26%", before=0, after=0, color=GOLD, thickness=1.0):
    h = HRFlowable(width=width, thickness=thickness, color=color,
                   spaceBefore=before, spaceAfter=after, hAlign="LEFT")
    h.keepWithNext = 1
    return h


def quote_box(text: str, small=False):
    st = ST["quote_small"] if small else ST["quote"]
    bar = Table([["", Paragraph(text, st)]],
                colWidths=[2.2 * mm, FW - 9 * mm])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), GOLD),
        ("BACKGROUND", (1, 0), (1, 0), PAPER_TINT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (1, 0), (1, 0), 7),
        ("RIGHTPADDING", (1, 0), (1, 0), 7),
        ("TOPPADDING", (1, 0), (1, 0), 7),
        ("BOTTOMPADDING", (1, 0), (1, 0), 7),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return bar


def data_table(rows, header=True):
    ncols = len(rows[0])
    texts = [[plain_cell(c) for c in row] for row in rows]
    widths = []
    for j in range(ncols):
        lens = [len(re.sub(r"\s", "", texts[i][j])) for i in range(len(texts))]
        m = max(lens) if lens else 1
        widths.append(max(6, min(m, 34)) ** 0.62)
    if ncols == 2 and max(len(texts[i][0]) for i in range(len(texts))) <= 14:
        col_w = [30 * mm, FW - 30 * mm]
    else:
        total = sum(widths)
        col_w = [max(13 * mm, FW * w / total) for w in widths]
        scale = FW / sum(col_w)
        col_w = [w * scale for w in col_w]

    data = []
    for i, row in enumerate(rows):
        style = ST["th"] if (header and i == 0) else ST["td"]
        data.append([Paragraph(inline_html(c) if isinstance(c, Tag) else esc(str(c)), style)
                     for c in row])
    t = Table(data, colWidths=col_w, repeatRows=1 if header else 0, hAlign="LEFT")
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, GOLD),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]
    for i in range(2, len(rows), 2):
        cmds.append(("BACKGROUND", (0, i), (-1, i), PAPER_TINT))
    if not header:
        cmds = [x for x in cmds if x[1] != (0, 0) or x[0] != "BACKGROUND"]
    t.setStyle(TableStyle(cmds))
    return t


def plain_cell(node):
    if isinstance(node, Tag):
        return node.get_text(" ", strip=True)
    return str(node)


def fact_table(pairs):
    rows = [["项目", "内容"]] + [[k, v] for k, v in pairs]
    return data_table(rows, header=True)


def section_list(items):
    if not items:
        return Spacer(1, 1)
    items = items[:10]
    cells = []
    for it in items:
        cells.append(Paragraph(f'<font color="#C39A4A">·</font>&nbsp;&nbsp;{esc(it)}',
                               ST["small"]))
    half = (len(cells) + 1) // 2
    left = cells[:half]
    right = cells[half:] + [Paragraph("", ST["small"])] * (half - len(cells[half:]))
    t = Table([[a, b] for a, b in zip(left, right)],
              colWidths=[(FW - 9 * mm) / 2, (FW - 9 * mm) / 2], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    return t


def render_nodes(nodes, story, indent_body=True):
    """Append flowables for a sequence of BeautifulSoup nodes."""
    for node in nodes:
        if isinstance(node, NavigableString):
            txt = str(node).strip()
            if txt:
                story.append(Paragraph(esc(txt), ST["body"]))
            continue
        if not isinstance(node, Tag):
            continue
        name = node.name.lower()
        if name == "h1":
            continue  # chapter openers are built separately
        elif name == "h2":
            story.append(rule(width="18%", before=8, after=4, thickness=0.9))
            p = Paragraph(inline_html(node), ST["h2"])
            p._heading = (1, 1, plain(node))
            story.append(p)
        elif name == "h3":
            p = Paragraph(inline_html(node), ST["h3"])
            lvl = 0 if node.get("data-front") else 2
            p._heading = (None, lvl, plain(node))
            story.append(p)
        elif name == "p":
            p = Paragraph(inline_html(node), ST["body"])
            story.append(p)
        elif name == "blockquote":
            paras = [inline_html(x) for x in node.find_all("p", recursive=False)]
            if not paras:
                paras = [inline_html(node)]
            story.append(Spacer(1, 3))
            story.append(quote_box("<br/><br/>".join(paras)))
            story.append(Spacer(1, 7))
        elif name == "ul":
            for li in node.find_all("li", recursive=False):
                p = Paragraph(inline_html(li), ST["list"], bulletText="•")
                p.bulletFontName = "Sans"
                p.bulletColor = GOLD
                p.bulletFontSize = 8.5
                story.append(p)
            story.append(Spacer(1, 5))
        elif name == "ol":
            for i, li in enumerate(node.find_all("li", recursive=False), 1):
                p = Paragraph(inline_html(li), ST["list"], bulletText=f"{i}.")
                p.bulletFontName = "SansBold"
                p.bulletColor = GOLD_DARK
                p.bulletFontSize = 8.5
                story.append(p)
            story.append(Spacer(1, 5))
        elif name == "table":
            rows = []
            trs = node.find_all("tr")
            for tr in trs:
                cells = tr.find_all(["th", "td"], recursive=False)
                if cells:
                    rows.append(cells)
            if rows:
                story.append(Spacer(1, 4))
                story.append(data_table(rows, header=True))
                story.append(Spacer(1, 7))
        elif name == "pre":
            code = node.get_text("\n", strip=True)
            code_html = "<br/>".join(esc(x) for x in code.split("\n"))
            box = Table([[Paragraph(code_html, ST["code"])]],
                        colWidths=[FW - 8 * mm], hAlign="LEFT")
            box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), PAPER_TINT),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(box)
            story.append(Spacer(1, 6))
        elif name == "hr":
            story.append(rule(width="100%", before=6, after=8,
                              color=RULE, thickness=0.5))
        else:
            # Unknown wrapper (div, etc.): render children
            render_nodes(list(node.children), story, indent_body)


def split_chapters(md_text):
    html_text = markdown.markdown(md_text, extensions=["tables", "sane_lists"])
    soup = BeautifulSoup(html_text, "html.parser")
    chapters, cur = [], None
    for node in soup.children:
        if isinstance(node, NavigableString) and not str(node).strip():
            continue
        if isinstance(node, Tag) and node.name == "h1":
            cur = {"title": plain(node), "nodes": []}
            chapters.append(cur)
        elif cur is not None:
            cur["nodes"].append(node)
    return chapters


def chapter_epigraph(nodes):
    def first_sentence(txt):
        m = re.search(r"^(.{10,118}?[。！？])", txt)
        if m:
            return m.group(1)
        return txt[:100] + ("…" if len(txt) > 100 else "")
    for n in nodes:
        if isinstance(n, Tag) and n.name == "blockquote":
            return first_sentence(plain(n))
    for n in nodes:
        if isinstance(n, Tag) and n.name == "p":
            txt = plain(n)
            if len(txt) > 12:
                return first_sentence(txt)
    return "把复杂的事情讲到现场去。"


def chapter_sections(nodes):
    return [plain(n) for n in nodes
            if isinstance(n, Tag) and n.name == "h2"]


def add_chapter(story, idx, ch, cfg):
    story.extend([PageBreak(), PageMarker("chapter"), Spacer(1, 13 * mm)])
    story.append(Paragraph(f"{idx:02d}", ST["chapter_num"]))
    p = Paragraph(inline_html(BeautifulSoup(
        markdown.markdown("# " + ch["title"]), "html.parser").find("h1")),
        ST["chapter_title"])
    p._heading = (0, 0, ch["title"])
    story.append(p)
    story.append(Paragraph(cfg["chapter_kicker"].format(n=idx), ST["kicker"]))
    story.append(rule(width="34%", before=1, after=9, thickness=1.3))
    ep = chapter_epigraph(ch["nodes"])
    if not ep.startswith(("「", "『", "“", '"')):
        ep = "「" + ep + "」"
    story.append(quote_box(ep, small=True))
    story.append(Spacer(1, 9 * mm))
    story.append(Paragraph("本章要点", ST["label"]))
    story.append(section_list(chapter_sections(ch["nodes"])))
    story.extend([PageBreak(), PageMarker("body")])
    render_nodes(ch["nodes"], story)


def toc_flowable():
    toc = TableOfContents(dotsMinLevel=0)
    toc.levelStyles = [ST["toc0"], ST["toc1"]]
    toc.tableStyle = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ])
    return toc


def front_matter(cfg, chapters):
    s = [PageMarker("cover"), Spacer(1, 1), PageBreak()]

    # Half title
    s += [PageMarker("front"), Spacer(1, 42 * mm)]
    s.append(Paragraph(cfg["half_title"], ST["half_title"]))
    s.append(Paragraph(cfg["half_eng"], ST["half_eng"]))
    s.append(rule(width="20%", before=6, after=12, thickness=1.0))
    for line in cfg["half_lines"]:
        s.append(Paragraph(line, ST["small_center"]))
    s.append(Spacer(1, 16 * mm))
    s.append(fact_table(cfg["facts"]))
    s.append(PageBreak())

    # About / project introduction
    s.append(PageMarker("front"))
    s.append(Paragraph(cfg["about_title"], ST["front_title"]))
    for para in cfg["about_paras"]:
        s.append(Paragraph(para, ST["body"]))
    if cfg.get("about_extra_nodes"):
        render_nodes(cfg["about_extra_nodes"], s)
    s.append(PageBreak())

    # Table of contents
    s.append(PageMarker("front"))
    s.append(Paragraph("目录", ST["front_title"]))
    s.append(Paragraph(cfg["toc_note"], ST["small"]))
    s.append(Spacer(1, 7 * mm))
    s.append(toc_flowable())
    s.append(Spacer(1, 9 * mm))
    s.append(Paragraph(cfg["map_title"], ST["label"]))
    s.append(data_table(cfg["map_rows"], header=True))
    s.append(Spacer(1, 4 * mm))
    s.append(Paragraph(cfg["map_note"], ST["small"]))
    return s


def end_matter(cfg):
    s = [PageBreak(), PageMarker("front"), Spacer(1, 10 * mm)]
    s.append(Paragraph(cfg["end_title"], ST["front_title"]))
    s.append(rule(width="24%", before=0, after=10, thickness=1.0))
    for para in cfg["end_paras"]:
        s.append(Paragraph(para, ST["body"]))
    s.append(Spacer(1, 10 * mm))
    s.append(quote_box(cfg["end_quote"]))
    s.append(Spacer(1, 12 * mm))
    s.append(Paragraph(cfg["end_colophon"], ST["small"]))
    return s


def build_pdf(cfg, chapter_sources, out_path):
    register_fonts()
    chapters = []
    for title, text in chapter_sources:
        for ch in split_chapters(text):
            chapters.append(ch)
    print(f"[{out_path.name}] chapters={len(chapters)}", flush=True)

    story = front_matter(cfg, chapters)
    for i, ch in enumerate(chapters, 1):
        add_chapter(story, i, ch, cfg)
    story += end_matter(cfg)

    doc = BookDocTemplate(str(out_path), cfg)
    passes = doc.multiBuild(story, maxPasses=6)
    print(f"[{out_path.name}] pages={doc.page} passes={passes} "
          f"size={out_path.stat().st_size / 1024:.0f} KB", flush=True)
    return out_path


# --------------------------------------------------------------------------
# Configurations
# --------------------------------------------------------------------------
def readme_sections():
    md = (ROOT / "README.md").read_text(encoding="utf-8")
    html_text = markdown.markdown(md, extensions=["tables", "sane_lists"])
    soup = BeautifulSoup(html_text, "html.parser")
    wanted = {"关于本书", "为什么免费公开", "关于作者", "版权声明"}
    nodes, keep = [], False
    for n in soup.children:
        if isinstance(n, Tag) and n.name == "h2":
            keep = plain(n) in wanted
            if keep:
                n.name = "h3"
                n["data-front"] = "1"
                nodes.append(n)
            continue
        if keep and isinstance(n, Tag):
            nodes.append(n)
    return nodes


def book_chapters():
    files = sorted(ROOT.glob("[0-1][0-9]-*.md"))
    return [(f.stem, f.read_text(encoding="utf-8")) for f in files]


def book_cfg():
    return {
        "meta_title": "前线部署工程师 · 精排版 v1.0.24",
        "meta_author": "范冰（XDash）",
        "meta_subject": "人工智能时代的客户价值交付秘籍",
        "meta_keywords": "FDE, Forward Deployed Engineer, 前线部署工程师, Palantir, 企业 AI",
        "cover_art": ASSETS / "cover_book.png",
        "eyebrow": "OPEN SOURCE EDITION  /  免费公开全文",
        "cover_title_lines": [
            ("前线部署工程师", 34, "SerifBold", WHITE, 15),
            ("客户价值交付秘籍", 20, "Serif", colors.HexColor("#E8DFC9"), 12),
        ],
        "cover_sub": "人工智能时代的客户价值交付秘籍",
        "cover_eng": "FORWARD DEPLOYED ENGINEER  ·  THE FIELD GUIDE",
        "cover_author": "范冰 著 · fde4.ai",
        "cover_edition": "2026 年 11 月 · 精排版 v1.0.24",
        "cover_note": "正文取自本仓库 13 个 Markdown 章节，仅重制版式，未改动内容",
        "cover_footer": "FIELD NOTES / 001",
        "header_left": "前线部署工程师",
        "header_right": "FDE · 客户价值交付",
        "footer_left": "fde4.ai",
        "footer_right": "精排版 v1.0.24",
        "chapter_kicker": "CHAPTER {n:02d}  /  FIELD NOTES",
        "half_title": "前线部署工程师",
        "half_eng": "FORWARD DEPLOYED ENGINEER",
        "half_lines": [
            "范冰 著", "人工智能时代的客户价值交付秘籍", "——",
            "免费公开全文 · 官网 fde4.ai", "精排版基于开源版 v1.0.24",
        ],
        "facts": [
            ["书名", "前线部署工程师：人工智能时代的客户价值交付秘籍"],
            ["作者", "范冰（XDash），《增长黑客》作者"],
            ["版本", "v1.0.24 · 2026 年 8 月原著，2026 年 11 月重排"],
            ["结构", "自序 + 8 章 + 后记 + 附录 A/B/C，共 13 个章节"],
            ["内容规模", "约 30 万字符，165 个可查案例，附录 C 逐条标注出处"],
            ["官网", "fde4.ai"],
            ["版权", "作者所有；免费阅读与非商业性分享，商业用途须书面许可"],
        ],
        "about_title": "关于这次精排版",
        "about_paras": [
            "这一版把仓库里的 Markdown 原稿重新排成一本可翻阅、可检索、可打印的书：重新设计封面与扉页，为每章加了独立的章节页与本章要点，正文采用思源宋体、思源黑体混排，加入带页码与点线的目录、PDF 书签、页眉页脚与引用框。<b>正文内容与原著完全一致，没有增删或改写。</b>",
            "排版上的主要变化包括：一是把 13 个章节拆成 13 个章节页，章号与本章小节一览放在正文之前；二是正文采用首行缩进、两端对齐与中文断行，长段落更耐读；三是所有二级标题进入可点击目录，PDF 阅读器的书签面板可直接跳转；四是表格、引文、清单分别采用不同的视觉层级；五是页眉标出书名，页脚给出页码与官网。",
            "本书的全部文字著作权归作者范冰所有。本精排版沿用原仓库的版权声明：供读者免费阅读与非商业性分享，转载请注明出处与作者；任何商业用途须事先获得作者书面许可。若发现错漏，欢迎在原仓库以 Issue 指正。",
        ],
        "about_extra_nodes": readme_sections(),
        "toc_note": "目录含章与节两级；页码由排版引擎自动生成，点击条目可跳转。",
        "map_title": "阅读地图 · 一次交付的完整旅程",
        "map_rows": [
            ["段落", "对应章节", "要回答的问题"],
            ["起点", "自序 / 第 1 章", "FDE 从哪里来，为什么是现在"],
            ["找对问题", "第 2 章", "什么值得做，如何避开概念验证坟墓"],
            ["进入客户", "第 3 章", "选谁、怎么赢、怎么过采购与安全审查"],
            ["跑起来", "第 4 章", "上线之后如何被真正使用"],
            ["留住与做大", "第 5、6 章", "续约、扩容、按结果收费"],
            ["可复制", "第 7 章", "现场经验如何回流产品"],
            ["回到现场", "第 8 章", "五个完整案例复盘"],
            ["边界与工具", "后记 / 附录 A–C", "伦理、指标、人物与出处"],
        ],
        "map_note": "全书按一次真实交付的时间线展开；附录 C 给出所有数据与案例的出处，可随时回查。",
        "end_title": "版权与出版说明",
        "end_paras": [
            "《前线部署工程师：人工智能时代的客户价值交付秘籍》著作权归作者范冰所有。本仓库内容由作者本人授权公开，供读者免费阅读与非商业性分享；转载请务必注明出处与作者。任何商业用途（包括但不限于出版、培训、付费内容改编）须事先获得作者书面许可。",
            "本 PDF 由仓库中的 Markdown 章节自动排版生成，使用 Google Fonts 的 Noto Serif SC、Noto Sans SC 与 JetBrains Mono（SIL Open Font License），封面图为生成式抽象插画。生成脚本位于 tools/build_pdfs.py，字体与封面素材不纳入仓库。",
            "书中数据与案例的出处见附录 C；引用任何数字前，建议回到原始来源核对其口径与时间。官网 fde4.ai 与仓库会持续更新，章节 Markdown 为最新文本基准。",
        ],
        "end_quote": "「复杂的事情，没法隔着屏幕解决，总得有人到场。」",
        "end_colophon": f"精排版生成于 {DATE} · 排版：Arena FDE PDF Kit · 版本 v1.0.24",
    }


def report_cfg():
    return {
        "meta_title": "FDE 开源全景 · 综合研读报告",
        "meta_author": "Arena FDE PDF Kit（综合整理）",
        "meta_subject": "11 个高星 FDE 仓库 × 一本书的交叉研读",
        "meta_keywords": "FDE, Forward Deployed Engineer, 开源生态, 研读报告, 评测, 交付",
        "cover_art": ASSETS / "cover_synthesis.png",
        "eyebrow": "OPEN-SOURCE LANDSCAPE REVIEW  /  2026",
        "cover_title_lines": [
            ("FDE 开源全景", 34, "SerifBold", WHITE, 15),
            ("综合研读报告", 20, "Serif", colors.HexColor("#DCEDEA"), 12),
        ],
        "cover_sub": "11 个高星仓库 × 一本书 · 交叉对齐的知识地图",
        "cover_eng": "FORWARD DEPLOYED ENGINEER  ·  FIELD GUIDE TO THE ECOSYSTEM",
        "cover_author": "基于本仓库 + 11 个 GitHub 开源项目综合整理",
        "cover_edition": "2026 年 11 月 2 日 · 第 1 版",
        "cover_note": "star 数与许可为 2026-11-02 GitHub API 快照，正文为原创综合叙述",
        "cover_footer": "RESEARCH / 001",
        "header_left": "FDE 开源全景",
        "header_right": "综合研读报告 · 2026-11",
        "footer_left": "github.com/xdash",
        "footer_right": "第 1 版",
        "chapter_kicker": "PART {n:02d}  /  SYNTHESIS",
        "half_title": "FDE 开源全景",
        "half_eng": "A SYNTHESIS OF THE FDE OPEN-SOURCE ECOSYSTEM",
        "half_lines": [
            "11 个高星仓库 × 一本书", "——",
            "定义 · 能力 · 流程 · 工程 · 商业 · 组织",
            "交叉对齐，整理成一套可执行的知识地图",
        ],
        "facts": [
            ["报告名称", "FDE 开源全景：11 个高星仓库 × 一本书的综合研读报告"],
            ["基线著作", "本书《前线部署工程师》v1.0.24（5,399 stars）"],
            ["对照样本", "11 个 FDE 专门仓库，star 31–1,484，浅克隆离线研读"],
            ["快照日期", "2026-11-02（UTC），GitHub REST API"],
            ["内容结构", "13 个部分 + 附录：定义、能力、流程、工程、中国语境、工具、路径、分歧、速览、许可"],
            ["使用方法", "可免费阅读与非商业分享；二次分发前请逐项核对各原仓库许可"],
            ["来源文件", "research/FDE-开源生态综合研读.md、research/repo_metadata.json"],
        ],
        "about_title": "关于这份报告",
        "about_paras": [
            "本报告回答一个很具体的问题：<b>当 FDE 的开源资料已经多到读不过来时，它们合起来到底在说什么？</b> 我们以本书的交付全生命周期为叙事基线，把 11 个高星仓库按定义、能力、流程、工程、商业与组织六个维度拆开、去重、重新对齐，写成一份可以直接按顺序执行的综合研读。",
            "选样以 GitHub Search API 的 star 降序为起点，人工剔除只是顺带提到 FDE 的通用 AI 仓库，再对保留的 11 个仓库做浅克隆，离线研读 README、章节目录、技能清单、许可文件与关键实现。所有 star、语言与许可字段取自 2026-11-02 的 API 快照，保存在 research/repo_metadata.json。",
            "<b>本报告不是原文汇编。</b> 除少量短句引用外，表格、对照与叙述均为重新组织后的综合整理；未声明许可的仓库只做结构级引用。所有结论都标注了来源仓库全名，便于回溯核对。",
        ],
        "about_extra_nodes": [],
        "toc_note": "目录含部分与小节两级；点击条目可跳转。第 12 章为 12 份仓库速览卡。",
        "map_title": "按问题查读",
        "map_rows": [
            ["若你想……", "直接读"],
            ["判断 FDE 是什么、值不值得做", "第 4、5、11 章"],
            ["按项目推进一次真实交付", "第 6、7 章 + 附录检查清单"],
            ["给团队排学习顺序", "第 10、12 章"],
            ["核对样本、数字与许可", "第 2、13 章"],
            ["找工具、技能包与工程底座", "第 9 章"],
        ],
        "map_note": "全部 star 数与许可字段为 2026-11-02 快照，回查文件位于 research/repo_metadata.json。",
        "end_title": "来源、致谢与使用说明",
        "end_paras": [
            "感谢 11 个仓库的作者与维护者把 FDE 的方法、路线、清单、Notebook 与技能包公开出来；也感谢本书作者范冰把 165 个案例与出处整理成可核查的中文基线。没有这些开源工作，就不会有这份交叉研读。",
            "本报告可免费阅读与非商业分享；引用请注明「FDE 开源全景综合研读报告（2026-11-02）」及对应仓库全名。若用于商业培训、出版或咨询，请分别回查并取得各原仓库权利人的许可，尤其是采用自定义非商业许可、CC BY-SA 4.0 或未声明许可的仓库。",
            "star 数、工具版本、薪酬区间与合规要求都会变化；本报告把它们当作某一时点的快照，不作为选型或投资的依据。发现错漏，欢迎在本仓库以 Issue 指正。",
        ],
        "end_quote": "「模型已经不稀缺，能把模型放进客户真实业务、并用数字证明价值的人，才稀缺。」",
        "end_colophon": f"综合整理于 {DATE} · 排版：Arena FDE PDF Kit · 第 1 版",
    }


def main():
    register_fonts()
    out1 = build_pdf(book_cfg(), book_chapters(),
                     OUT_DIR / "前线部署工程师（FDE）精排版-v1.0.24.pdf")
    report_md = (ROOT / "research" / "FDE-开源生态综合研读.md").read_text(encoding="utf-8")
    chapters = [(f"报告 {i:02d}", t) for i, t in enumerate(re.split(r"(?=^# )", report_md, flags=re.M)) if t.strip()]
    out2 = build_pdf(report_cfg(), chapters,
                     OUT_DIR / "FDE-开源全景综合研读报告-2026-11.pdf")
    print("DONE:", out1.name, "|", out2.name)


if __name__ == "__main__":
    main()
