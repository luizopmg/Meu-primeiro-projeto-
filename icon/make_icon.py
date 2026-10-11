"""Gera o ícone da Aranha Digital a partir de uma única definição de formas.

Saídas:
  app/src/main/res/drawable/ic_launcher_background.xml  (vetor: fundo com teia)
  app/src/main/res/drawable/ic_launcher_foreground.xml  (vetor: a aranha)
  icon/icon.svg                                         (mesmo desenho, para gerar os PNGs)
Grade de 108 x 108 (padrão do ícone adaptativo; área sempre visível = círculo de 66 no centro).
"""
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQUA, BODY, BODY_EDGE, HEAD, PINK = "#20F1DF", "#0DE2D5", "#E5FFFE", "#05121B", "#FF4ABA"
BG, WEB = "#0A1020", "#1C3150"
C = 54.0


def circle(cx, cy, r):
    return f"M{cx - r:.2f},{cy:.2f} a{r:.2f},{r:.2f} 0 1,0 {2 * r:.2f},0 a{r:.2f},{r:.2f} 0 1,0 {-2 * r:.2f},0 Z"


def ellipse(cx, cy, rx, ry):
    return f"M{cx - rx:.2f},{cy:.2f} a{rx:.2f},{ry:.2f} 0 1,0 {2 * rx:.2f},0 a{rx:.2f},{ry:.2f} 0 1,0 {-2 * rx:.2f},0 Z"


# ---- fundo: teia (8 raios + anéis octogonais)
web = []
for i in range(8):
    a = math.pi / 8 + i * math.pi / 4
    web.append(f"M{C:.2f},{C:.2f} L{C + math.cos(a) * 80:.2f},{C + math.sin(a) * 80:.2f}")
for r in (12, 21, 31, 42, 54):
    pts = [(C + math.cos(math.pi / 8 + i * math.pi / 4) * r, C + math.sin(math.pi / 8 + i * math.pi / 4) * r) for i in range(8)]
    web.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z")
BACKGROUND = [
    {"d": "M0,0 H108 V108 H0 Z", "fill": BG},
    {"d": " ".join(web), "stroke": WEB, "sw": 1.1},
]

# ---- frente: fio + aranha
LEFT_LEGS = ["M51,48 L42,38 L37,27", "M50,51 L39,46 L30,43", "M50,55 L39,58 L30,63", "M51,58 L43,67 L39,78"]


def mirror(d):
    out = []
    for tok in d.split():
        cmd, xy = tok[0], tok[1:]
        x, y = xy.split(",")
        out.append(f"{cmd}{108 - float(x):g},{y}")
    return " ".join(out)


legs = " ".join(LEFT_LEGS + [mirror(d) for d in LEFT_LEGS])
FOREGROUND = [
    {"d": "M54,10 L54,40", "stroke": AQUA, "sw": 1.3, "alpha": 0.7},
    {"d": legs, "stroke": AQUA, "sw": 3.2},
    {"d": ellipse(54, 61, 9, 11), "fill": BODY, "stroke": BODY_EDGE, "sw": 1.5},
    {"d": circle(54, 45, 6), "fill": HEAD, "stroke": AQUA, "sw": 2},
    {"d": circle(51.6, 44, 1.6) + " " + circle(56.4, 44, 1.6), "fill": PINK},
]


def vector_xml(shapes):
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<vector xmlns:android="http://schemas.android.com/apk/res/android"',
           '    android:width="108dp" android:height="108dp"',
           '    android:viewportWidth="108" android:viewportHeight="108">']
    for s in shapes:
        attrs = [f'android:pathData="{s["d"]}"']
        if "fill" in s:
            attrs.append(f'android:fillColor="{s["fill"]}"')
        if "stroke" in s:
            attrs += [f'android:strokeColor="{s["stroke"]}"', f'android:strokeWidth="{s["sw"]}"',
                      'android:strokeLineCap="round"', 'android:strokeLineJoin="round"']
        if "alpha" in s:
            attrs.append(f'android:strokeAlpha="{s["alpha"]}"')
        out.append("    <path " + "\n          ".join(attrs) + " />")
    out.append("</vector>\n")
    return "\n".join(out)


def svg_paths(shapes):
    parts = []
    for s in shapes:
        a = [f'd="{s["d"]}"', f'fill="{s.get("fill", "none")}"']
        if "stroke" in s:
            a += [f'stroke="{s["stroke"]}"', f'stroke-width="{s["sw"]}"', 'stroke-linecap="round"', 'stroke-linejoin="round"']
        if "alpha" in s:
            a.append(f'stroke-opacity="{s["alpha"]}"')
        parts.append("<path " + " ".join(a) + "/>")
    return "\n".join(parts)


res = os.path.join(ROOT, "app/src/main/res/drawable")
os.makedirs(res, exist_ok=True)
open(os.path.join(res, "ic_launcher_background.xml"), "w").write(vector_xml(BACKGROUND))
open(os.path.join(res, "ic_launcher_foreground.xml"), "w").write(vector_xml(FOREGROUND))
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108" width="108" height="108">\n'
       f'{svg_paths(BACKGROUND)}\n{svg_paths(FOREGROUND)}\n</svg>\n')
open(os.path.join(ROOT, "icon/icon.svg"), "w").write(svg)
print("ícone gerado")
