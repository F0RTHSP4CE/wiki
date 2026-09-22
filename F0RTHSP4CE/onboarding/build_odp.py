#!/usr/bin/env python3
"""Build the editable F0RTHSP4CE onboarding ODP from its Markdown source."""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import math
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / "member-candidate-onboarding.md"
DEFAULT_OUTPUT = ROOT / "member-candidate-onboarding.odp"
DEFAULT_PDF_OUTPUT = ROOT / "member-candidate-onboarding.pdf"
REPO_ROOT = ROOT.parents[1]
ASSET_DIR = ROOT / "assets"
WORDMARK_PNG = ASSET_DIR / "f0-wordmark.png"
MARK_PNG = ASSET_DIR / "f0-mark.png"
UNBOUNDED_TTF = ASSET_DIR / "Unbounded-VariableFont_wght.ttf"

PAGE_W = 33.867
PAGE_H = 19.05
GREEN = "#00FF00"
RED = "#D90000"
YELLOW = "#FFFF00"
BLACK = "#000000"
WHITE = "#FFFFFF"

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "presentation": "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "dc": "http://purl.org/dc/elements/1.1/",
    "meta": "urn:oasis:names:tc:opendocument:xmlns:meta:1.0",
    "manifest": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def q(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


@dataclass
class Section:
    title: str
    lines: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Slide:
    layout: str
    title: str
    intro: str
    sections: list[Section]
    callout: str
    sources: list[tuple[str, str]]


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float
    style: str
    radius: float = 0.0


@dataclass
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    style: str = "line"


@dataclass
class Triangle:
    x: float
    y: float
    w: float
    h: float
    style: str = "green"
    direction: str = "right"


@dataclass
class TextBox:
    x: float
    y: float
    w: float
    h: float
    text: str
    style: str
    sources: list[tuple[str, str]] | None = None


@dataclass
class Image:
    x: float
    y: float
    w: float
    h: float
    path: str


@dataclass
class Scene:
    commands: list[Rect | Line | Triangle | TextBox | Image] = field(default_factory=list)

    def rect(self, x: float, y: float, w: float, h: float, style: str, radius: float = 0.0) -> None:
        self.commands.append(Rect(x, y, w, h, style, radius))

    def line(self, x1: float, y1: float, x2: float, y2: float, style: str = "line") -> None:
        self.commands.append(Line(x1, y1, x2, y2, style))

    def triangle(self, x: float, y: float, w: float, h: float,
                 style: str = "green", direction: str = "right") -> None:
        self.commands.append(Triangle(x, y, w, h, style, direction))

    def text(self, x: float, y: float, w: float, h: float, text: str, style: str,
             sources: list[tuple[str, str]] | None = None) -> None:
        self.commands.append(TextBox(x, y, w, h, text, style, sources))

    def image(self, x: float, y: float, w: float, h: float, path: str) -> None:
        self.commands.append(Image(x, y, w, h, path))


LAYOUTS = {"title", "list"}


def plain(text: str) -> str:
    text = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    return text.strip()


def parse_metadata(lines: list[str]) -> tuple[dict[str, str], list[str]]:
    if not lines or lines[0].strip() != "---":
        raise ValueError("Markdown must begin with metadata delimited by ---")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise ValueError("Unclosed metadata block") from exc
    metadata: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"Malformed metadata line: {line}")
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    return metadata, lines[end + 1:]


def split_slides(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = [[]]
    for line in lines:
        if line.strip() == "---":
            if any(item.strip() for item in blocks[-1]):
                blocks.append([])
            continue
        blocks[-1].append(line)
    return [block for block in blocks if any(item.strip() for item in block)]


def parse_slide(lines: list[str], index: int) -> Slide:
    layout = "cards"
    title = ""
    intro_lines: list[str] = []
    sections: list[Section] = []
    callouts: list[str] = []
    sources: list[tuple[str, str]] = []
    current: Section | None = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        match = re.fullmatch(r"<!--\s*layout:\s*([a-z-]+)\s*-->", line)
        if match:
            layout = match.group(1)
            continue
        if line.startswith("# "):
            title = plain(line[2:])
            continue
        if line.startswith("## "):
            current = Section(plain(line[3:]))
            sections.append(current)
            continue
        if line.startswith("> "):
            callouts.append(plain(line[2:]))
            continue
        if line.startswith("Sources:"):
            sources = re.findall(r"\[([^]]+)]\((https?://[^)]+)\)", line)
            continue
        kind = "bullet" if line.startswith("- ") else "paragraph"
        value = plain(line[2:] if kind == "bullet" else line)
        if current is None:
            intro_lines.append(value)
        else:
            current.lines.append((kind, value))

    if layout not in LAYOUTS:
        raise ValueError(f"Slide {index}: unsupported layout {layout!r}")
    if not title:
        raise ValueError(f"Slide {index}: missing # title")
    if intro_lines:
        raise ValueError(f"Slide {index}: subtitle/intro copy is not allowed in this deck")
    if callouts:
        raise ValueError(f"Slide {index}: bottom callouts are not allowed in this deck")
    if not sources:
        raise ValueError(f"Slide {index}: missing or malformed Sources line")
    return Slide(layout, title, " ".join(intro_lines), sections, " ".join(callouts), sources)


def git_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_deck(path: Path) -> tuple[dict[str, str], list[Slide]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    metadata, body = parse_metadata(lines)
    revision = git_revision()
    generated = dt.date.today().isoformat()
    substitutions = {"{git_revision}": revision, "{generated_date}": generated}
    slides: list[Slide] = []
    for index, block in enumerate(split_slides(body), start=1):
        expanded = []
        for line in block:
            for key, value in substitutions.items():
                line = line.replace(key, value)
            expanded.append(line)
        slides.append(parse_slide(expanded, index))
    if not slides:
        raise ValueError("The deck must contain at least one slide")
    metadata["source-revision"] = revision
    metadata["generated-date"] = generated
    return metadata, slides


def section_text(section: Section) -> str:
    parts = []
    for kind, value in section.lines:
        parts.append((">  " if kind == "bullet" else "") + value)
    return "\n".join(parts)


def base_scene(slide: Slide, number: int) -> Scene:
    scene = Scene()
    scene.rect(0, 0, PAGE_W, PAGE_H, "black")
    scene.rect(1.2, 0.62, 0.28, 0.28, "green")
    scene.text(1.75, 0.5, 20.0, 0.6, f"FØ / MEMBER ONBOARDING / {number:02d}", "kicker")
    scene.text(1.2, 1.3, 27.6, 1.55, slide.title, "title")
    scene.image(29.75, 0.48, 2.8, 1.35, "Pictures/f0_mark.png")
    scene.line(1.2, 3.18, 32.65, 3.18, "green_rule")
    scene.text(1.2, 17.94, 29.2, 0.48, "", "footer", slide.sources)
    scene.text(31.5, 17.9, 1.1, 0.5, f"{number:02d}", "page")
    return scene


def scene_for_slide(slide: Slide, number: int) -> Scene:
    if slide.layout == "title":
        if len(slide.sections) != 1:
            raise ValueError(f"Slide {number}: title layout needs one metadata section")
        scene = Scene()
        scene.rect(0, 0, PAGE_W, PAGE_H, "black")
        scene.image(1.2, 3.0, 31.0, 2.86, "Pictures/f0_wordmark.png")
        scene.line(1.2, 7.18, 32.2, 7.18, "green_rule")
        scene.text(1.2, 8.25, 30.6, 2.1, slide.title.upper(), "hero_title")
        scene.text(1.2, 11.35, 30.6, 2.5, section_text(slide.sections[0]), "hero_meta")
        scene.text(1.2, 17.94, 28.8, 0.48, "", "footer", slide.sources)
        scene.text(31.4, 17.9, 1.0, 0.5, f"{number:02d}", "page")
        return scene

    scene = base_scene(slide, number)
    y0 = 4.0
    content_bottom = 17.15

    if slide.layout == "flow":
        count = len(slide.sections)
        if count < 3 or count > 5:
            raise ValueError(f"Slide {number}: flow layout needs three to five sections")
        gap = 0.12
        h = (content_bottom - y0 - gap * (count - 1)) / count
        for idx, section in enumerate(slide.sections):
            y = y0 + idx * (h + gap)
            scene.rect(1.2, y + 0.2, 1.1, 1.1, "outline_green")
            scene.text(1.2, y + 0.28, 1.1, 0.75, f"{idx + 1:02d}", "step_number")
            scene.text(3.0, y + 0.14, 7.3, h - 0.25, section.title, "step_title")
            scene.text(10.5, y + 0.1, 21.7, h - 0.15, section_text(section), "step_body")

    elif slide.layout == "list":
        count = len(slide.sections)
        if count < 2 or count > 4:
            raise ValueError(f"Slide {number}: list layout needs two to four sections")
        gap = 0.3
        h = (content_bottom - y0 - gap * (count - 1)) / count
        for idx, section in enumerate(slide.sections):
            y = y0 + idx * (h + gap)
            scene.text(1.2, y + 0.1, 2.0, 0.9, f"{idx + 1:02d}", "list_number")
            section_title = section.title
            label_style = None
            shared_labels = None
            private_labels = None
            if section_title.startswith("{red} "):
                section_title = section_title.removeprefix("{red} ")
                label_style = ("red", "label_white")
            elif section_title.startswith("{green} "):
                section_title = section_title.removeprefix("{green} ")
                label_style = ("green", "label_black")
            elif section_title.startswith("{white} "):
                section_title = section_title.removeprefix("{white} ")
                label_style = ("white", "label_black")
            elif section_title.startswith("{shared} "):
                section_title = section_title.removeprefix("{shared} ")
                shared_labels = [part.strip() for part in section_title.split(" / ", 1)]
                if len(shared_labels) != 2:
                    raise ValueError(f"Slide {number}: shared item label needs two parts")
            elif section_title.startswith("{private} "):
                section_title = section_title.removeprefix("{private} ")
                private_labels = [part.strip() for part in section_title.split(" | ", 1)]
                if len(private_labels) != 2:
                    raise ValueError(f"Slide {number}: private item label needs two parts")
            stacked_labels = shared_labels or private_labels
            if stacked_labels:
                label_width = 29.0
                first_fill = "green" if shared_labels else "red"
                first_text = "label_black" if shared_labels else "label_white"
                second_fill = "white" if shared_labels else "yellow"
                scene.rect(3.65, y, label_width, 1.15, first_fill)
                scene.text(3.9, y + 0.03, label_width - 0.5, 1.05,
                           stacked_labels[0], first_text)
                scene.rect(3.65, y + 1.25, label_width, 1.15, second_fill)
                scene.text(3.9, y + 1.28, label_width - 0.5, 1.05,
                           stacked_labels[1], "label_black")
            elif label_style:
                # Use the complete content width. Font metrics differ slightly
                # between the PDF renderer and LibreOffice Impress, so a
                # character-count estimate can wrap long item labels.
                label_width = 29.0
                scene.rect(3.65, y, label_width, 1.5, label_style[0])
                scene.text(3.9, y + 0.08, label_width - 0.5, 1.35,
                           section_title, label_style[1])
            else:
                scene.text(3.8, y + 0.05, 28.0, 1.3, section_title, "list_title")
            body_y = y + 2.6 if stacked_labels else y + 1.55
            body_h = h - 2.8 if stacked_labels else h - 1.75
            scene.text(3.8, body_y, 28.0, body_h, section_text(section), "list_body")
            if idx < count - 1:
                scene.line(3.8, y + h, 32.65, y + h, "white_rule")

    elif slide.layout == "warning":
        if len(slide.sections) != 1:
            raise ValueError(f"Slide {number}: warning layout needs exactly one section")
        section = slide.sections[0]
        scene.text(1.2, y0 + 0.35, 25.4, content_bottom - y0 - 0.35,
                   section_text(section), "body")
        scene.triangle(28.2, 4.4, 3.8, 3.5, "outline_green", "up")
        scene.text(28.2, 5.3, 3.8, 1.3, "!", "warning_mark")
        if "emergency" in slide.title.lower():
            scene.text(28.2, 8.5, 3.8, 1.4, "112", "warning_number")

    elif slide.layout == "single":
        if len(slide.sections) != 1:
            raise ValueError(f"Slide {number}: single layout needs exactly one section")
        section = slide.sections[0]
        scene.text(1.2, y0 + 0.35, 31.0, content_bottom - y0 - 0.35,
                   section_text(section), "single_body")
    else:
        raise ValueError(f"Slide {number}: unhandled layout {slide.layout}")

    return scene


GRAPHIC_STYLES = {
    "black": {"fill": BLACK, "stroke": "none"},
    "green": {"fill": GREEN, "stroke": "none"},
    "red": {"fill": RED, "stroke": "none"},
    "yellow": {"fill": YELLOW, "stroke": "none"},
    "white": {"fill": WHITE, "stroke": "none"},
    "outline_green": {"fill": BLACK, "stroke": GREEN},
    "outline_white": {"fill": BLACK, "stroke": WHITE},
}

TEXT_STYLES = {
    "kicker": (11, GREEN, True, "left", "Liberation Sans"),
    "title": (36, WHITE, True, "left", "Unbounded"),
    "section": (28, GREEN, True, "left", "Unbounded"),
    "body": (26, WHITE, False, "left", "Liberation Sans"),
    "body_small": (25, WHITE, False, "left", "Liberation Sans"),
    "callout": (18, GREEN, True, "left", "Liberation Sans"),
    "footer": (8.5, WHITE, False, "left", "Liberation Sans"),
    "page": (10.5, GREEN, True, "right", "Unbounded"),
    "hero_title": (44, WHITE, True, "left", "Unbounded"),
    "hero_meta": (12, WHITE, False, "left", "Liberation Sans"),
    "hero_callout": (21, GREEN, True, "left", "Liberation Sans"),
    "hero_label": (21, WHITE, True, "left", "Unbounded"),
    "step_number": (17, GREEN, True, "center", "Unbounded"),
    "step_title": (23, GREEN, True, "left", "Unbounded"),
    "step_body": (23, WHITE, False, "left", "Liberation Sans"),
    "list_number": (21, GREEN, True, "left", "Unbounded"),
    "list_title": (27, GREEN, True, "left", "Unbounded"),
    "label_white": (23, WHITE, True, "left", "Unbounded"),
    "label_black": (23, BLACK, True, "left", "Unbounded"),
    "list_body": (25, WHITE, False, "left", "Liberation Sans"),
    "warning_mark": (36, WHITE, True, "center", "Unbounded"),
    "warning_number": (27, GREEN, True, "center", "Unbounded"),
    "single_body": (27, WHITE, False, "left", "Liberation Sans"),
}


def add_graphic_style(parent: ET.Element, name: str, fill: str, stroke: str) -> None:
    style = ET.SubElement(parent, q("style", "style"), {
        q("style", "name"): f"G_{name}", q("style", "family"): "graphic",
    })
    props = {
        q("draw", "fill"): "none" if fill == "none" else "solid",
        q("draw", "textarea-vertical-align"): "top",
        q("draw", "auto-grow-height"): "false", q("draw", "auto-grow-width"): "false",
        q("fo", "padding"): "0cm",
    }
    if fill != "none":
        props[q("draw", "fill-color")] = fill
    if stroke == "none":
        props[q("draw", "stroke")] = "none"
    else:
        props.update({q("draw", "stroke"): "solid", q("svg", "stroke-color"): stroke,
                      q("svg", "stroke-width"): "0.035cm"})
    ET.SubElement(style, q("style", "graphic-properties"), props)


def add_text_style(parent: ET.Element, name: str, size: float, color: str,
                   bold: bool, align: str, font: str) -> None:
    style = ET.SubElement(parent, q("style", "style"), {
        q("style", "name"): f"P_{name}", q("style", "family"): "paragraph",
    })
    ET.SubElement(style, q("style", "paragraph-properties"), {
        q("fo", "text-align"): align,
        q("fo", "margin-top"): "0cm", q("fo", "margin-bottom"): "0.13cm",
        q("fo", "line-height"): "115%",
    })
    ET.SubElement(style, q("style", "text-properties"), {
        q("style", "font-name"): font,
        q("fo", "font-family"): font,
        q("fo", "font-size"): f"{size}pt",
        q("fo", "font-weight"): "bold" if bold else "normal",
        q("fo", "color"): color,
        q("fo", "language"): "en", q("fo", "country"): "US",
    })


def add_font_face(parent: ET.Element, name: str, family: str,
                  embedded_path: str | None = None) -> None:
    face = ET.SubElement(parent, q("style", "font-face"), {
        q("style", "name"): name, q("svg", "font-family"): family,
        q("style", "font-family-generic"): "swiss", q("style", "font-pitch"): "variable",
    })
    if embedded_path:
        source = ET.SubElement(face, q("svg", "font-face-src"))
        uri = ET.SubElement(source, q("svg", "font-face-uri"), {
            q("xlink", "href"): embedded_path, q("xlink", "type"): "simple",
        })
        ET.SubElement(uri, q("svg", "font-face-format"), {q("svg", "string"): "truetype"})


def content_xml(scenes: list[Scene]) -> bytes:
    root = ET.Element(q("office", "document-content"), {q("office", "version"): "1.2"})
    fonts = ET.SubElement(root, q("office", "font-face-decls"))
    add_font_face(fonts, "Unbounded", "Unbounded", "Fonts/Unbounded.ttf")
    add_font_face(fonts, "Liberation Sans", "Liberation Sans")
    auto = ET.SubElement(root, q("office", "automatic-styles"))
    dp = ET.SubElement(auto, q("style", "style"), {
        q("style", "name"): "dp1", q("style", "family"): "drawing-page",
    })
    ET.SubElement(dp, q("style", "drawing-page-properties"), {
        q("presentation", "background-visible"): "true",
        q("presentation", "background-objects-visible"): "true",
        q("presentation", "display-footer"): "false",
        q("presentation", "display-page-number"): "false",
        q("presentation", "display-date-time"): "false",
    })
    for name, values in GRAPHIC_STYLES.items():
        add_graphic_style(auto, name, values["fill"], values["stroke"])
    add_graphic_style(auto, "text", "none", "none")
    add_graphic_style(auto, "image", "none", "none")
    for name, values in TEXT_STYLES.items():
        add_text_style(auto, name, *values)
    link_style = ET.SubElement(auto, q("style", "style"), {
        q("style", "name"): "T_link", q("style", "family"): "text",
    })
    ET.SubElement(link_style, q("style", "text-properties"), {
        q("fo", "color"): WHITE, q("style", "text-underline-style"): "none",
        q("style", "font-name"): "Liberation Sans", q("fo", "font-family"): "Liberation Sans",
    })

    for style_name, color, width in (
        ("green_rule", GREEN, "0.055cm"),
        ("white_rule", WHITE, "0.025cm"),
    ):
        line_style = ET.SubElement(auto, q("style", "style"), {
            q("style", "name"): f"G_{style_name}", q("style", "family"): "graphic",
        })
        ET.SubElement(line_style, q("style", "graphic-properties"), {
            q("draw", "stroke"): "solid", q("svg", "stroke-color"): color,
            q("svg", "stroke-width"): width, q("draw", "fill"): "none",
        })

    body = ET.SubElement(root, q("office", "body"))
    presentation = ET.SubElement(body, q("office", "presentation"))
    for index, scene in enumerate(scenes, start=1):
        page = ET.SubElement(presentation, q("draw", "page"), {
            q("draw", "name"): f"slide{index}", q("draw", "style-name"): "dp1",
            q("draw", "master-page-name"): "Default",
        })
        for command in scene.commands:
            if isinstance(command, Rect):
                ET.SubElement(page, q("draw", "rect"), {
                    q("draw", "style-name"): f"G_{command.style}",
                    q("svg", "x"): f"{command.x:.3f}cm", q("svg", "y"): f"{command.y:.3f}cm",
                    q("svg", "width"): f"{command.w:.3f}cm", q("svg", "height"): f"{command.h:.3f}cm",
                    q("draw", "corner-radius"): f"{command.radius:.3f}cm",
                })
            elif isinstance(command, Line):
                ET.SubElement(page, q("draw", "line"), {
                    q("draw", "style-name"): f"G_{command.style}",
                    q("svg", "x1"): f"{command.x1:.3f}cm", q("svg", "y1"): f"{command.y1:.3f}cm",
                    q("svg", "x2"): f"{command.x2:.3f}cm", q("svg", "y2"): f"{command.y2:.3f}cm",
                })
            elif isinstance(command, Triangle):
                points = {
                    "right": "0,0 1000,500 0,1000",
                    "down": "0,0 1000,0 500,1000",
                    "up": "500,0 1000,1000 0,1000",
                }[command.direction]
                ET.SubElement(page, q("draw", "polygon"), {
                    q("draw", "style-name"): f"G_{command.style}",
                    q("svg", "x"): f"{command.x:.3f}cm", q("svg", "y"): f"{command.y:.3f}cm",
                    q("svg", "width"): f"{command.w:.3f}cm", q("svg", "height"): f"{command.h:.3f}cm",
                    q("svg", "viewBox"): "0 0 1000 1000", q("draw", "points"): points,
                })
            elif isinstance(command, Image):
                frame = ET.SubElement(page, q("draw", "frame"), {
                    q("draw", "style-name"): "G_image", q("draw", "name"): f"Image {index}",
                    q("svg", "x"): f"{command.x:.3f}cm", q("svg", "y"): f"{command.y:.3f}cm",
                    q("svg", "width"): f"{command.w:.3f}cm", q("svg", "height"): f"{command.h:.3f}cm",
                })
                ET.SubElement(frame, q("draw", "image"), {
                    q("xlink", "href"): command.path, q("xlink", "type"): "simple",
                    q("xlink", "show"): "embed", q("xlink", "actuate"): "onLoad",
                })
            elif isinstance(command, TextBox):
                frame = ET.SubElement(page, q("draw", "frame"), {
                    q("draw", "style-name"): "G_text", q("draw", "name"): f"Text {index}",
                    q("svg", "x"): f"{command.x:.3f}cm", q("svg", "y"): f"{command.y:.3f}cm",
                    q("svg", "width"): f"{command.w:.3f}cm", q("svg", "height"): f"{command.h:.3f}cm",
                })
                box = ET.SubElement(frame, q("draw", "text-box"))
                if command.sources is not None:
                    paragraph = ET.SubElement(box, q("text", "p"), {
                        q("text", "style-name"): f"P_{command.style}",
                    })
                    paragraph.text = "Sources: "
                    for source_index, (label, href) in enumerate(command.sources):
                        if source_index:
                            separator = ET.SubElement(paragraph, q("text", "span"))
                            separator.text = "  ·  "
                        anchor = ET.SubElement(paragraph, q("text", "a"), {
                            q("xlink", "href"): href, q("xlink", "type"): "simple",
                            q("text", "style-name"): "T_link",
                        })
                        anchor.text = label
                else:
                    for line in command.text.split("\n") or [""]:
                        paragraph = ET.SubElement(box, q("text", "p"), {
                            q("text", "style-name"): f"P_{command.style}",
                        })
                        paragraph.text = line
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def styles_xml() -> bytes:
    root = ET.Element(q("office", "document-styles"), {q("office", "version"): "1.2"})
    fonts = ET.SubElement(root, q("office", "font-face-decls"))
    add_font_face(fonts, "Unbounded", "Unbounded", "Fonts/Unbounded.ttf")
    add_font_face(fonts, "Liberation Sans", "Liberation Sans")
    styles = ET.SubElement(root, q("office", "styles"))
    standard = ET.SubElement(styles, q("style", "default-style"), {q("style", "family"): "paragraph"})
    ET.SubElement(standard, q("style", "text-properties"), {
        q("style", "font-name"): "Liberation Sans", q("fo", "font-family"): "Liberation Sans",
        q("fo", "language"): "en", q("fo", "country"): "US",
    })
    auto = ET.SubElement(root, q("office", "automatic-styles"))
    page_layout = ET.SubElement(auto, q("style", "page-layout"), {q("style", "name"): "pm1"})
    ET.SubElement(page_layout, q("style", "page-layout-properties"), {
        q("fo", "page-width"): f"{PAGE_W}cm", q("fo", "page-height"): f"{PAGE_H}cm",
        q("style", "print-orientation"): "landscape", q("fo", "margin"): "0cm",
    })
    master = ET.SubElement(root, q("office", "master-styles"))
    ET.SubElement(master, q("style", "master-page"), {
        q("style", "name"): "Default", q("style", "page-layout-name"): "pm1",
    })
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def meta_xml(metadata: dict[str, str]) -> bytes:
    root = ET.Element(q("office", "document-meta"), {q("office", "version"): "1.2"})
    meta = ET.SubElement(root, q("office", "meta"))
    ET.SubElement(meta, q("dc", "title")).text = metadata.get("title", "F0RTHSP4CE onboarding")
    ET.SubElement(meta, q("dc", "subject")).text = metadata.get("subtitle", "")
    ET.SubElement(meta, q("dc", "creator")).text = "F0RTHSP4CE"
    ET.SubElement(meta, q("meta", "generator")).text = "F0RTHSP4CE build_odp.py"
    ET.SubElement(meta, q("dc", "date")).text = metadata["generated-date"]
    ET.SubElement(meta, q("meta", "user-defined"), {
        q("meta", "name"): "Source revision", q("meta", "value-type"): "string",
    }).text = metadata["source-revision"]
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def settings_xml() -> bytes:
    root = ET.Element(q("office", "document-settings"), {q("office", "version"): "1.2"})
    settings = ET.SubElement(root, q("office", "settings"))
    view = ET.SubElement(settings, q("config", "config-item-set"), {q("config", "name"): "ooo:view-settings"})
    ET.SubElement(view, q("config", "config-item"), {
        q("config", "name"): "VisibleAreaTop", q("config", "type"): "int",
    }).text = "0"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def manifest_xml() -> bytes:
    root = ET.Element(q("manifest", "manifest"), {q("manifest", "version"): "1.2"})
    entries = [
        ("/", "application/vnd.oasis.opendocument.presentation"),
        ("content.xml", "text/xml"), ("styles.xml", "text/xml"),
        ("meta.xml", "text/xml"), ("settings.xml", "text/xml"),
        ("Pictures/f0_wordmark.png", "image/png"),
        ("Pictures/f0_mark.png", "image/png"),
        ("Fonts/Unbounded.ttf", "application/x-font-ttf"),
        ("Thumbnails/thumbnail.png", "image/png"),
    ]
    for path, media_type in entries:
        ET.SubElement(root, q("manifest", "file-entry"), {
            q("manifest", "full-path"): path, q("manifest", "media-type"): media_type,
        })
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def zip_info(name: str, stored: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def build_odp(output: Path, metadata: dict[str, str], scenes: list[Scene]) -> None:
    for asset in (WORDMARK_PNG, MARK_PNG, UNBOUNDED_TTF):
        if not asset.exists():
            raise FileNotFoundError(f"Missing onboarding asset: {asset}")
    files = {
        "content.xml": content_xml(scenes), "styles.xml": styles_xml(),
        "meta.xml": meta_xml(metadata), "settings.xml": settings_xml(),
        "META-INF/manifest.xml": manifest_xml(),
        "Pictures/f0_wordmark.png": WORDMARK_PNG.read_bytes(),
        "Pictures/f0_mark.png": MARK_PNG.read_bytes(),
        "Fonts/Unbounded.ttf": UNBOUNDED_TTF.read_bytes(),
        "Thumbnails/thumbnail.png": MARK_PNG.read_bytes(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(zip_info("mimetype", stored=True),
                         b"application/vnd.oasis.opendocument.presentation")
        for name in sorted(files):
            archive.writestr(zip_info(name), files[name])


def validate_odp(path: Path, expected_slides: int) -> None:
    required = {
        "mimetype", "content.xml", "styles.xml", "meta.xml", "settings.xml",
        "META-INF/manifest.xml", "Pictures/f0_wordmark.png", "Pictures/f0_mark.png",
        "Fonts/Unbounded.ttf", "Thumbnails/thumbnail.png",
    }
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        missing = required.difference(names)
        if missing:
            raise ValueError(f"ODP is missing entries: {sorted(missing)}")
        if names[0] != "mimetype" or archive.getinfo("mimetype").compress_type != zipfile.ZIP_STORED:
            raise ValueError("mimetype must be the first, uncompressed ZIP entry")
        if archive.read("mimetype") != b"application/vnd.oasis.opendocument.presentation":
            raise ValueError("Incorrect ODP mimetype")
        xml_docs = {name: ET.fromstring(archive.read(name)) for name in required if name.endswith(".xml")}
        content = xml_docs["content.xml"]
        if content.attrib.get(q("office", "version")) != "1.2":
            raise ValueError("content.xml is not OpenDocument 1.2")
        pages = content.findall(f".//{q('draw', 'page')}")
        if len(pages) != expected_slides:
            raise ValueError(f"Expected {expected_slides} pages in ODP, found {len(pages)}")
        for page_index, page in enumerate(pages, start=1):
            page_links = [
                node.attrib[q("xlink", "href")]
                for node in page.findall(f".//*[@{q('xlink', 'href')}]")
                if node.attrib[q("xlink", "href")].startswith(("http://", "https://"))
            ]
            if not page_links:
                raise ValueError(f"Slide {page_index} has no clickable source link")
        hrefs = [node.attrib[q("xlink", "href")] for node in content.findall(f".//*[@{q('xlink', 'href')}]")]
        for href in hrefs:
            if href.startswith(("/", "file://")):
                raise ValueError(f"Local absolute path leaked into ODP: {href}")
            if not href.startswith(("http://", "https://")) and href not in names:
                raise ValueError(f"Broken internal media reference: {href}")
        links = [href for href in hrefs if href.startswith(("http://", "https://"))]
        if len(links) < expected_slides:
            raise ValueError("Each slide must contain at least one source link")
        manifest = xml_docs["META-INF/manifest.xml"]
        declared = {
            node.attrib[q("manifest", "full-path")]
            for node in manifest.findall(q("manifest", "file-entry"))
        }
        for name in names:
            if name not in {"mimetype", "META-INF/manifest.xml"} and name not in declared:
                raise ValueError(f"ZIP entry is missing from the manifest: {name}")


def register_app_font(path: Path) -> None:
    """Register a bundled font with Fontconfig for this process."""
    library = ctypes.CDLL("libfontconfig.so.1")
    library.FcConfigGetCurrent.restype = ctypes.c_void_p
    library.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    library.FcConfigAppFontAddFile.restype = ctypes.c_int
    library.FcConfigBuildFonts.argtypes = [ctypes.c_void_p]
    library.FcConfigBuildFonts.restype = ctypes.c_int
    config = library.FcConfigGetCurrent()
    if not config or not library.FcConfigAppFontAddFile(config, str(path).encode()):
        raise RuntimeError(f"Could not register font: {path}")
    library.FcConfigBuildFonts(config)


def rgb(hex_color: str) -> tuple[float, float, float]:
    value = hex_color.lstrip("#")
    return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))


def render_pdf(path: Path, scenes: list[Scene], metadata: dict[str, str]) -> None:
    """Render a vector PDF directly from the same scene graph as the ODP."""
    try:
        register_app_font(UNBOUNDED_TTF)
        import cairo
        import gi
        gi.require_version("Pango", "1.0")
        gi.require_version("PangoCairo", "1.0")
        from gi.repository import Pango, PangoCairo
    except (ImportError, OSError) as exc:
        raise RuntimeError("Direct PDF output requires Pycairo, PyGObject, Pango, and Fontconfig") from exc

    points_per_cm = 72 / 2.54
    width = PAGE_W * points_per_cm
    height = PAGE_H * points_per_cm
    path.parent.mkdir(parents=True, exist_ok=True)
    surface = cairo.PDFSurface(str(path), width, height)
    if hasattr(surface, "set_metadata"):
        surface.set_metadata(cairo.PDF_METADATA_TITLE, metadata.get("title", "FØ Member Onboarding"))
        surface.set_metadata(cairo.PDF_METADATA_AUTHOR, "FØRTHSP4CE")
        surface.set_metadata(cairo.PDF_METADATA_CREATE_DATE, metadata["generated-date"])

    image_cache: dict[str, object] = {}

    def layout_for(context, text: str, style_name: str, box_width: float):
        size, color, bold, align, family = TEXT_STYLES[style_name]
        layout = PangoCairo.create_layout(context)
        description = Pango.FontDescription()
        description.set_family(family)
        description.set_absolute_size(size * Pango.SCALE)
        description.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
        layout.set_font_description(description)
        layout.set_width(int(box_width * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_spacing(int(1.5 * Pango.SCALE))
        layout.set_alignment({
            "left": Pango.Alignment.LEFT,
            "center": Pango.Alignment.CENTER,
            "right": Pango.Alignment.RIGHT,
        }[align])
        layout.set_text(text, -1)
        context.set_source_rgb(*rgb(color))
        return layout

    def draw_sources(context, command: TextBox) -> None:
        x = command.x * points_per_cm
        y = command.y * points_per_cm
        max_width = command.w * points_per_cm
        cursor = x
        runs: list[tuple[str, str | None]] = [("Sources: ", None)]
        for index, (label, href) in enumerate(command.sources or []):
            if index:
                runs.append(("  ·  ", None))
            runs.append((label, href))
        for value, href in runs:
            layout = layout_for(context, value, command.style, max_width)
            run_width = layout.get_size()[0] / Pango.SCALE
            context.move_to(cursor, y)
            if href:
                context.tag_begin(cairo.TAG_LINK, f"uri='{href}'")
            PangoCairo.show_layout(context, layout)
            if href:
                context.tag_end(cairo.TAG_LINK)
            cursor += run_width

    for scene in scenes:
        context = cairo.Context(surface)
        for command in scene.commands:
            if isinstance(command, Rect):
                style = GRAPHIC_STYLES[command.style]
                x, y, w, h = (command.x * points_per_cm, command.y * points_per_cm,
                              command.w * points_per_cm, command.h * points_per_cm)
                context.rectangle(x, y, w, h)
                if style["fill"] != "none":
                    context.set_source_rgb(*rgb(style["fill"]))
                    context.fill_preserve()
                if style["stroke"] != "none":
                    context.set_source_rgb(*rgb(style["stroke"]))
                    context.set_line_width(1.25)
                    context.stroke()
                else:
                    context.new_path()
            elif isinstance(command, Line):
                context.move_to(command.x1 * points_per_cm, command.y1 * points_per_cm)
                context.line_to(command.x2 * points_per_cm, command.y2 * points_per_cm)
                context.set_source_rgb(*rgb(WHITE if command.style == "white_rule" else GREEN))
                context.set_line_width(0.8 if command.style == "white_rule" else 1.4)
                context.stroke()
            elif isinstance(command, Triangle):
                x, y, w, h = (command.x * points_per_cm, command.y * points_per_cm,
                              command.w * points_per_cm, command.h * points_per_cm)
                points = {
                    "right": ((x, y), (x + w, y + h / 2), (x, y + h)),
                    "down": ((x, y), (x + w, y), (x + w / 2, y + h)),
                    "up": ((x + w / 2, y), (x + w, y + h), (x, y + h)),
                }[command.direction]
                context.move_to(*points[0])
                for point in points[1:]:
                    context.line_to(*point)
                context.close_path()
                style = GRAPHIC_STYLES[command.style]
                if style["fill"] != "none":
                    context.set_source_rgb(*rgb(style["fill"]))
                    context.fill_preserve()
                if style["stroke"] != "none":
                    context.set_source_rgb(*rgb(style["stroke"]))
                    context.set_line_width(1.25)
                    context.stroke()
                else:
                    context.new_path()
            elif isinstance(command, Image):
                source_path = WORDMARK_PNG if command.path.endswith("f0_wordmark.png") else MARK_PNG
                if command.path not in image_cache:
                    image_cache[command.path] = cairo.ImageSurface.create_from_png(str(source_path))
                image = image_cache[command.path]
                x, y, w, h = (command.x * points_per_cm, command.y * points_per_cm,
                              command.w * points_per_cm, command.h * points_per_cm)
                scale = min(w / image.get_width(), h / image.get_height())
                context.save()
                context.translate(x + (w - image.get_width() * scale) / 2,
                                  y + (h - image.get_height() * scale) / 2)
                context.scale(scale, scale)
                context.set_source_surface(image, 0, 0)
                context.paint()
                context.restore()
            elif isinstance(command, TextBox):
                if command.sources is not None:
                    draw_sources(context, command)
                    continue
                x = command.x * points_per_cm
                y = command.y * points_per_cm
                layout = layout_for(context, command.text, command.style, command.w * points_per_cm)
                context.move_to(x, y)
                PangoCairo.show_layout(context, layout)
        context.show_page()
    surface.finish()


def validate_pdf(path: Path, expected_slides: int) -> None:
    if not path.exists() or path.stat().st_size < 10_000:
        raise ValueError("PDF output is missing or unexpectedly small")
    if path.read_bytes()[:5] != b"%PDF-":
        raise ValueError("PDF output has an invalid header")
    try:
        info = subprocess.check_output(["pdfinfo", str(path)], text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("pdfinfo is required for --check PDF validation") from exc
    match = re.search(r"^Pages:\s+(\d+)$", info, re.MULTILINE)
    if not match or int(match.group(1)) != expected_slides:
        raise ValueError(f"Expected {expected_slides} PDF pages")
    fonts = subprocess.check_output(["pdffonts", str(path)], text=True)
    # Cairo identifies the embedded variable Unbounded font as CairoFont in
    # the PDF font table. Liberation Sans keeps its PostScript name.
    if "CairoFont" not in fonts or "LiberationSans" not in fonts:
        raise ValueError("PDF does not contain embedded display and body fonts")
    link_info = subprocess.check_output(["pdfinfo", "-url", str(path)], text=True)
    linked_pages = {
        int(match.group(1))
        for match in re.finditer(r"^\s*(\d+)\s+Annotation\s+https?://", link_info, re.MULTILINE)
    }
    if linked_pages != set(range(1, expected_slides + 1)):
        raise ValueError("Every PDF page must contain clickable source links")


def wrap_for_preview(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines, current = [], words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def render_preview(path: Path, scenes: list[Scene]) -> None:
    try:
        from PIL import Image as PILImage, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required only for --preview") from exc

    scale = 24
    sw, sh = int(PAGE_W * scale), int(PAGE_H * scale)
    tiles: list[object] = []
    liberation_path = "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"
    liberation_bold_path = "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"
    fonts: dict[tuple[int, bool, str], object] = {}
    overflows: list[str] = []

    def get_font(points: float, bold: bool, family: str):
        key = (max(8, int(points * 0.82)), bold, family)
        if key not in fonts:
            path = (str(UNBOUNDED_TTF) if family == "Unbounded"
                    else liberation_bold_path if bold else liberation_path)
            fonts[key] = ImageFont.truetype(path, key[0])
        return fonts[key]

    for scene in scenes:
        image = PILImage.new("RGB", (sw, sh), BLACK)
        draw = ImageDraw.Draw(image)
        for command in scene.commands:
            if isinstance(command, Rect):
                style = GRAPHIC_STYLES[command.style]
                coords = tuple(int(v * scale) for v in (command.x, command.y, command.x + command.w, command.y + command.h))
                outline = None if style["stroke"] == "none" else style["stroke"]
                draw.rectangle(coords, fill=style["fill"], outline=outline,
                               width=max(1, int(0.035 * scale)))
            elif isinstance(command, Line):
                color = WHITE if command.style == "white_rule" else GREEN
                draw.line(tuple(int(v * scale) for v in (command.x1, command.y1, command.x2, command.y2)),
                          fill=color, width=max(1, int(0.05 * scale)))
            elif isinstance(command, Triangle):
                x, y, w, h = (int(command.x * scale), int(command.y * scale),
                              int(command.w * scale), int(command.h * scale))
                points = {
                    "right": [(x, y), (x + w, y + h // 2), (x, y + h)],
                    "down": [(x, y), (x + w, y), (x + w // 2, y + h)],
                    "up": [(x + w // 2, y), (x + w, y + h), (x, y + h)],
                }[command.direction]
                style = GRAPHIC_STYLES[command.style]
                fill = style["fill"]
                outline = None if style["stroke"] == "none" else style["stroke"]
                draw.polygon(points, fill=fill, outline=outline)
            elif isinstance(command, Image):
                source = WORDMARK_PNG if command.path.endswith("f0_wordmark.png") else MARK_PNG
                logo = PILImage.open(source).convert("RGBA")
                target = (max(1, int(command.w * scale)), max(1, int(command.h * scale)))
                logo.thumbnail(target)
                px = int((command.x + command.w / 2) * scale - logo.width / 2)
                py = int((command.y + command.h / 2) * scale - logo.height / 2)
                image.paste(logo, (px, py), logo)
            elif isinstance(command, TextBox):
                size, color, bold, align, family = TEXT_STYLES[command.style]
                font = get_font(size, bold, family)
                x, y, w = int(command.x * scale), int(command.y * scale), int(command.w * scale)
                text = command.text if command.sources is None else "Sources: " + " · ".join(label for label, _ in command.sources)
                cursor = y
                for raw_line in text.split("\n"):
                    for line in wrap_for_preview(draw, raw_line, font, w):
                        bbox = draw.textbbox((0, 0), line, font=font)
                        tx = x if align == "left" else x + w - (bbox[2] - bbox[0]) if align == "right" else x + (w - (bbox[2] - bbox[0])) // 2
                        draw.text((tx, cursor), line, font=font, fill=color)
                        cursor += int((bbox[3] - bbox[1] + 3) * 1.1)
                if cursor - y > int(command.h * scale) + 2:
                    overflows.append(f"slide {len(tiles) + 1}: {command.style} text exceeds its box")
        tiles.append(image.resize((480, 270)))

    if overflows:
        raise ValueError("Preview layout overflow: " + "; ".join(overflows))

    sheet = PILImage.new("RGB", (480 * 4, 270 * math.ceil(len(tiles) / 4)), "#202020")
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % 4) * 480, (index // 4) * 270))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pdf-output", type=Path, default=DEFAULT_PDF_OUTPUT)
    parser.add_argument("--no-pdf", action="store_true", help="skip the default vector PDF build")
    parser.add_argument("--preview", type=Path, help="write a PNG contact sheet")
    parser.add_argument("--check", action="store_true", help="validate generated ODP and PDF files")
    args = parser.parse_args(argv)

    try:
        metadata, slides = load_deck(args.source.resolve())
        scenes = [scene_for_slide(slide, index) for index, slide in enumerate(slides, start=1)]
        build_odp(args.output.resolve(), metadata, scenes)
        if not args.no_pdf:
            render_pdf(args.pdf_output.resolve(), scenes, metadata)
        if args.check:
            validate_odp(args.output.resolve(), len(slides))
            if not args.no_pdf:
                validate_pdf(args.pdf_output.resolve(), len(slides))
        if args.preview:
            render_preview(args.preview.resolve(), scenes)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    message = f"Built {args.output} ({len(slides)} slides, source {metadata['source-revision']})"
    if not args.no_pdf:
        message += f"; PDF {args.pdf_output}"
    if args.check:
        message += "; validation passed"
    if args.preview:
        message += f"; preview {args.preview}"
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
