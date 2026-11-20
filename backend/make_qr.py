# -*- coding: utf-8 -*-
"""生成展品二维码 PNG 与可打印标签页 labels.html
用法： python make_qr.py <基础URL，如 http://81.70.40.146> [输出目录，默认 ../qr]
"""
import json
import sys
from pathlib import Path

import qrcode

BASE_DIR = Path(__file__).parent
SEED = BASE_DIR / "seed"

CARD_CSS = """
@page{size:A4;margin:12mm}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Noto Serif SC","Songti SC","SimSun",serif;background:#fff;color:#221E17}
.sheet{display:grid;grid-template-columns:1fr 1fr;gap:10mm}
.card{border:1.4px solid #221E17;background:#F5F1E8;padding:9mm 6mm 7mm;text-align:center;position:relative;page-break-inside:avoid}
.card .k{font-size:9pt;letter-spacing:.42em;color:#948B76}
.card h2{font-size:19pt;font-weight:600;letter-spacing:.14em;margin-top:2mm}
.card .en{font-size:8.5pt;color:#57503F;letter-spacing:.14em;margin-top:1.5mm}
.card .qr{width:44mm;height:44mm;margin:5mm auto 3mm;display:block;border:1px solid #C4BBA2}
.card .hint{font-size:8.5pt;color:#A03A2B;letter-spacing:.2em}
.card .foot{font-size:7.5pt;color:#948B76;margin-top:2.5mm;letter-spacing:.1em}
.card .no{position:absolute;top:4mm;left:5mm;font-size:8pt;color:#A03A2B;letter-spacing:.1em}
.head{margin-bottom:8mm;border-bottom:2px solid #221E17;padding-bottom:4mm}
.head h1{font-size:16pt;letter-spacing:.2em}
.head p{font-size:8.5pt;color:#948B76;margin-top:2mm;letter-spacing:.14em}
"""


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://81.70.40.146").rstrip("/")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE_DIR.parent / "qr"
    out.mkdir(parents=True, exist_ok=True)

    relics = json.loads((SEED / "relics.json").read_text(encoding="utf-8"))
    cards = []
    for r in relics:
        url = "%s/?r=%s" % (base, r["id"])
        img = qrcode.make(url, box_size=10, border=2)
        png = out / ("%s.png" % r["id"])
        img.save(png)
        cards.append((r, url))

    rows = []
    for i, (r, url) in enumerate(cards, 1):
        rows.append(
            '<div class="card"><span class="no">点位 %s · No.%d</span>'
            '<p class="k">锦语 · AI 文化导览</p>'
            "<h2>%s</h2><p class=\"en\">%s · %s</p>"
            '<img class="qr" src="%s.png" alt="">'
            '<p class="hint">扫码听文物开口</p>'
            '<p class="foot">%s</p></div>'
            % (r["point"], i, r["name"], r["enName"], r["era"], r["id"], url))
    # 占位空卡保持排版整齐
    while len(rows) % 2:
        rows.append('<div class="card" style="visibility:hidden"></div>')
    html = (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">"
        "<title>锦语 · 展品二维码标签</title><style>" + CARD_CSS + "</style></head><body>"
        '<div class="head"><h1>锦语 · 展品二维码标签</h1>'
        "<p>钢铁与荣耀 · 成都博物馆特展 · 打印后置于对应展品说明牌旁 · "
        "建议使用 200g 以上卡纸，单张裁切</p></div>"
        '<div class="sheet">' + "".join(rows) + "</div></body></html>")
    (out / "labels.html").write_text(html, encoding="utf-8")
    print("OK -> %s (%d 个二维码 + labels.html)" % (out, len(cards)))
    for r, url in cards:
        print("  %-16s %s" % (r["id"], url))


if __name__ == "__main__":
    main()
