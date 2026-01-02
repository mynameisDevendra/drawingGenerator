import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.utils import ImageReader
import re
import io
from datetime import datetime

# ================= PAGE CONFIG =================
st.set_page_config(page_title="CTR Generator Pro", layout="wide")

# ================= CONSTANTS =================
PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)

TERMINAL_HEIGHT = 40
ROW_HEIGHT_SPACING = 105
BLOCK_SYMBOL_HEIGHT = TERMINAL_HEIGHT * 2

# ================= SAMPLE =================
SAMPLE_CONTENT = """HEADING: SAMPLE TERMINAL CHART
STATION: KUR
SIP: SIP/KUR/2025/01

SHEET: 01
LOCATION: GTY-01

A, 12HR [01 to 08], 08C RR TO GTY-01

SYMBOL, A, [02 to 05], CHARGER
"""

# ================= TXT PARSER =================
def parse_multi_sheet_txt(raw_text):
    sheets = []
    meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    rows, symbols = [], []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        u = line.upper()

        if u.startswith("SHEET:"):
            if rows:
                sheets.append({"meta": meta.copy(), "rows": rows, "symbols": symbols})
                rows, symbols = [], []
            meta["sheet"] = int(re.search(r"\d+", line).group())

        elif u.startswith("STATION:"):
            meta["station"] = line.split(":", 1)[1].strip()

        elif u.startswith("LOCATION:"):
            meta["location"] = line.split(":", 1)[1].strip()

        elif u.startswith("SIP:"):
            meta["sip"] = line.split(":", 1)[1].strip()

        elif u.startswith("HEADING:"):
            meta["heading"] = line.split(":", 1)[1].strip()

        elif u.startswith("SYMBOL"):
            parts = [p.strip() for p in line.split(",")]
            m = re.search(r"\[(\d+)\s*(?:TO|to)\s*(\d+)\]", parts[2])
            if m:
                symbols.append({
                    "row": parts[1].upper(),
                    "start": m.group(1).zfill(2),
                    "end": m.group(2).zfill(2),
                    "symbol": parts[3].upper()
                })

        else:
            parts = [p.strip() for p in line.split(",")]
            rid = parts[0].upper()
            middle = ",".join(parts[1:])
            pat = r'([^,\[]+)\[\s*(\d+)\s*(?:TO|to)\s*(\d+)\s*\]'
            for f, s, e in re.findall(pat, middle):
                for i in range(int(s), int(e) + 1):
                    rows.append({
                        "Row ID": rid,
                        "Function": f.upper(),
                        "Terminal Number": str(i).zfill(2)
                    })

    if rows:
        sheets.append({"meta": meta, "rows": rows, "symbols": symbols})

    return sheets

# ================= DRAW HELPERS =================
def draw_page(c, w, h, heading):
    c.setLineWidth(1.5)
    c.rect(PAGE_MARGIN, PAGE_MARGIN, w - 2 * PAGE_MARGIN, h - 2 * PAGE_MARGIN)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 60, heading)

def draw_block_symbol(c, img_bytes, x1, x2, y):
    img_bytes.seek(0)
    img = ImageReader(img_bytes)
    c.drawImage(
        img,
        x1,
        y - 20,
        width=(x2 - x1),
        height=BLOCK_SYMBOL_HEIGHT,
        preserveAspectRatio=False,
        mask="auto"
    )

# ================= PDF ENGINE =================
def process_multi_sheet_pdf(sheets, symbol_images):
    buffer = io.BytesIO()
    w, h = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)

    for sheet in sheets:
        df = pd.DataFrame(sheet["rows"])
        df["num"] = df["Terminal Number"].astype(int)
        df = df.sort_values(["Row ID", "num"])

        draw_page(c, w, h, sheet["meta"]["heading"])

        info_x = PAGE_MARGIN + ((w - 2 * PAGE_MARGIN) / 15)
        term_per_row = max(1, int((w - info_x - SAFETY_OFFSET - 60) // FIXED_GAP))

        y = h - 160
        rows_used = 0

        # ---- BLOCKED TERMINALS ----
        blocked = set()
        for s in sheet["symbols"]:
            for t in range(int(s["start"]), int(s["end"]) + 1):
                blocked.add((s["row"], str(t).zfill(2)))

        for rid, grp in df.groupby("Row ID", sort=False):
            chunks = [grp.iloc[i:i + term_per_row] for i in range(0, len(grp), term_per_row)]

            for chunk in chunks:
                if rows_used >= 6:
                    c.showPage()
                    draw_page(c, w, h, sheet["meta"]["heading"])
                    y = h - 160
                    rows_used = 0

                x0 = info_x + SAFETY_OFFSET + 20
                c.setFont("Helvetica-Bold", 12)
                c.drawRightString(x0 - 30, y + 15, rid)

                # ---- DRAW TERMINALS ----
                for idx in range(len(chunk)):
                    tno = chunk.iloc[idx]["Terminal Number"]
                    tx = x0 + idx * FIXED_GAP

                    if (rid, tno) not in blocked:
                        c.line(tx - 3, y, tx - 3, y + TERMINAL_HEIGHT)
                        c.line(tx + 3, y, tx + 3, y + TERMINAL_HEIGHT)
                        c.circle(tx, y, 3, fill=1)
                        c.circle(tx, y + TERMINAL_HEIGHT, 3, fill=1)
                        c.setFont("Helvetica-Bold", 8.5)
                        c.drawCentredString(tx, y + 17, tno)

                # ---- DRAW BLOCK SYMBOLS ----
                for s in sheet["symbols"]:
                    if s["row"] != rid:
                        continue

                    start = int(s["start"])
                    end = int(s["end"])
                    first = int(chunk.iloc[0]["Terminal Number"])
                    last = int(chunk.iloc[-1]["Terminal Number"])

                    if start < first or end > last:
                        continue

                    x1 = x0 + (start - first) * FIXED_GAP - FIXED_GAP / 2
                    x2 = x0 + (end - first) * FIXED_GAP + FIXED_GAP / 2

                    img = symbol_images.get(s["symbol"])
                    if img:
                        draw_block_symbol(c, img, x1, x2, y)

                y -= ROW_HEIGHT_SPACING
                rows_used += 1

        c.showPage()

    c.save()
    buffer.seek(0)
    return buffer

# ================= UI =================
with st.sidebar:
    st.header("📂 Resources")
    st.download_button("📥 Sample TXT", SAMPLE_CONTENT, "sample_ctr.txt")

    st.subheader("🧩 Upload Symbols (PNG)")
    uploaded = st.file_uploader("Upload PNG files", type=["png"], accept_multiple_files=True)

symbol_images = {}
if uploaded:
    for f in uploaded:
        symbol_images[f.name.replace(".png", "").upper()] = io.BytesIO(f.getvalue())

st.title("🚉 CTR Generator – Block Symbols")

txt = st.file_uploader("Upload Drawing TXT", type=["txt"])
if txt:
    st.session_state.sheets = parse_multi_sheet_txt(txt.getvalue().decode())

if "sheets" in st.session_state:
    if st.button("🚀 Generate PDF", use_container_width=True):
        st.session_state.pdf = process_multi_sheet_pdf(
            st.session_state.sheets,
            symbol_images
        )

if "pdf" in st.session_state:
    st.download_button(
        "📥 Download PDF",
        st.session_state.pdf,
        f"CTR_{datetime.now().strftime('%d%m%Y')}.pdf",
        "application/pdf",
        use_container_width=True
    )
