import streamlit as st
import re, io
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.utils import ImageReader
from datetime import datetime

# ================= CONFIG =================
st.set_page_config(page_title="CTR Generator", layout="wide")

PAGE_SIZE = landscape(A3)
PAGE_MARGIN = 20
FIXED_GAP = 33
TERMINAL_HEIGHT = 40
SYMBOL_HEIGHT = TERMINAL_HEIGHT * 2
ROW_GAP = 120

SYMBOL_TYPES = {"CHARGER", "BATTERY", "RELAY", "SMPS"}

# ================= PARSER =================
def parse_txt(text):
    sheets = []
    sheet = None

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        u = line.upper()

        if u.startswith("SHEET:"):
            if sheet:
                sheets.append(sheet)
            sheet = {
                "meta": {},
                "rows": []
            }
            sheet["meta"]["sheet"] = int(re.search(r"\d+", line).group())

        elif any(u.startswith(k) for k in ["HEADING:", "STATION:", "LOCATION:", "SIP:"]):
            k, v = line.split(":", 1)
            sheet["meta"][k.strip().lower()] = v.strip()

        else:
            # ROW LINE
            rid, rest = line.split(",", 1)
            rid = rid.strip().upper()

            blocks = []
            cable = None

            for part in rest.split(","):
                part = part.strip()
                m = re.match(r'([A-Z0-9_]+)\[\s*(\d+)\s*TO\s*(\d+)\s*\]', part, re.I)
                if m:
                    blocks.append({
                        "type": m.group(1).upper(),
                        "start": int(m.group(2)),
                        "end": int(m.group(3))
                    })
                else:
                    cable = part

            sheet["rows"].append({
                "row": rid,
                "blocks": blocks,
                "cable": cable
            })

    if sheet:
        sheets.append(sheet)

    return sheets

# ================= DRAW HELPERS =================
def draw_page(c, w, h, meta):
    c.setLineWidth(1.5)
    c.rect(PAGE_MARGIN, PAGE_MARGIN, w-2*PAGE_MARGIN, h-2*PAGE_MARGIN)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w/2, h-50, meta.get("heading", ""))
    c.setFont("Helvetica", 9)
    c.drawString(PAGE_MARGIN+10, h-70, meta.get("station", ""))
    c.drawRightString(w-PAGE_MARGIN-10, h-70, meta.get("sip", ""))

def draw_terminal(c, x, y, num):
    c.line(x-3, y, x-3, y+TERMINAL_HEIGHT)
    c.line(x+3, y, x+3, y+TERMINAL_HEIGHT)
    c.circle(x, y, 3, fill=1)
    c.circle(x, y+TERMINAL_HEIGHT, 3, fill=1)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x, y+15, f"{num:02}")

def draw_group(c, x1, x2, y, text, above=True):
    c.line(x1, y, x2, y)
    c.line(x1, y, x1, y+(5 if above else -5))
    c.line(x2, y, x2, y+(5 if above else -5))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString((x1+x2)/2, y+(10 if above else -15), text)

def draw_symbol(c, img, x1, x2, y):
    img.seek(0)
    c.drawImage(
        ImageReader(img),
        x1,
        y,
        width=(x2-x1),
        height=SYMBOL_HEIGHT,
        preserveAspectRatio=False,
        mask="auto"
    )

# ================= PDF ENGINE =================
def generate_pdf(sheets, symbol_images):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE_SIZE)
    w, h = PAGE_SIZE

    for sheet in sheets:
        draw_page(c, w, h, sheet["meta"])
        y = h - 140
        x0 = PAGE_MARGIN + 100

        for row in sheet["rows"]:
            rid = row["row"]
            c.setFont("Helvetica-Bold", 12)
            c.drawRightString(x0-40, y+15, rid)

            blocks = row["blocks"]
            max_t = max(b["end"] for b in blocks)

            # Draw terminals & symbols
            for b in blocks:
                start, end, typ = b["start"], b["end"], b["type"]
                x1 = x0 + (start-1)*FIXED_GAP
                x2 = x0 + end*FIXED_GAP

                if typ in SYMBOL_TYPES:
                    img = symbol_images.get(typ)
                    if img:
                        draw_symbol(c, img, x1, x2, y)
                    draw_group(c, x1, x2, y+SYMBOL_HEIGHT+10, typ, above=True)
                else:
                    for t in range(start, end+1):
                        tx = x0 + (t-1)*FIXED_GAP
                        draw_terminal(c, tx, y, t)
                    draw_group(c, x1, x2, y+TERMINAL_HEIGHT+10, typ, above=True)

            # Cable detail (full row)
            if row["cable"]:
                x1 = x0
                x2 = x0 + max_t*FIXED_GAP
                draw_group(c, x1, x2, y-15, row["cable"], above=False)

            y -= ROW_GAP

        c.showPage()

    c.save()
    buf.seek(0)
    return buf

# ================= UI =================
st.title("🚉 CTR Generator (Final Format)")

txt = st.file_uploader("Upload TXT Input", type=["txt"])
imgs = st.file_uploader("Upload Symbol PNGs (CHARGER, BATTERY, etc.)", type=["png"], accept_multiple_files=True)

symbols = {}
if imgs:
    for f in imgs:
        symbols[f.name.replace(".png", "").upper()] = io.BytesIO(f.getvalue())

if txt and st.button("Generate PDF"):
    sheets = parse_txt(txt.getvalue().decode())
    pdf = generate_pdf(sheets, symbols)
    st.download_button("Download PDF", pdf, f"CTR_{datetime.now().strftime('%d%m%Y')}.pdf")
