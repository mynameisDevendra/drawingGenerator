import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="CTR Generator Pro", layout="wide")

# ---------------- CONSTANTS ----------------
PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105

# ---------------- SAMPLE ----------------
SAMPLE_CONTENT = """HEADING: SAMPLE TERMINAL CHART
STATION: KUR
SIP: SIP/KUR/2025/01

SHEET: 01
LOCATION: GTY-01
A, 12HR [01 to 04], 04C RR TO GTY-01

SYMBOL, A, 02, RELAY
SYMBOL, A, 03, FUSE
"""

# ---------------- TXT PARSER ----------------
def parse_multi_sheet_txt(raw_text):
    sheets_data = []
    current_meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    current_rows = []
    symbols = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        upper = line.upper()

        if upper.startswith("SHEET:"):
            if current_rows:
                sheets_data.append({
                    "meta": current_meta.copy(),
                    "rows": current_rows,
                    "symbols": symbols
                })
                current_rows, symbols = [], []

            val = re.search(r"\d+", line)
            if val:
                current_meta["sheet"] = int(val.group())

        elif upper.startswith("STATION:"):
            current_meta["station"] = line.split(":", 1)[1].strip()

        elif upper.startswith("LOCATION:"):
            current_meta["location"] = line.split(":", 1)[1].strip()

        elif upper.startswith("SIP:"):
            current_meta["sip"] = line.split(":", 1)[1].strip()

        elif upper.startswith("HEADING:"):
            current_meta["heading"] = line.split(":", 1)[1].strip()

        elif upper.startswith("SYMBOL"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                symbols.append({
                    "row": parts[1].upper(),
                    "terminal": parts[2].zfill(2),
                    "symbol": parts[3].upper()
                })

        else:
            parts = [p.strip() for p in line.split(",")]
            rid = parts[0].upper()
            middle = ",".join(parts[1:])
            pattern = r'([^,\[]+)\[\s*(\d+)\s*(?:to|TO)\s*(\d+)\s*\]'
            matches = re.findall(pattern, middle)

            for m in matches:
                func = m[0].strip().upper()
                for i in range(int(m[1]), int(m[2]) + 1):
                    current_rows.append({
                        "Row ID": rid,
                        "Function": func,
                        "Cable Detail": "",
                        "Terminal Number": str(i).zfill(2)
                    })

    if current_rows:
        sheets_data.append({
            "meta": current_meta,
            "rows": current_rows,
            "symbols": symbols
        })

    return sheets_data

# ---------------- DRAW HELPERS ----------------
def draw_page_template(c, width, height, footer, sheet_no, heading):
    c.setLineWidth(1.5)
    c.rect(PAGE_MARGIN, PAGE_MARGIN, width - 2*PAGE_MARGIN, height - 2*PAGE_MARGIN)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width/2, height - 60, heading)

def draw_inline_symbol(c, img, x, y, size=14):
    c.drawImage(
        img,
        x - size/2,
        y + 18,
        width=size,
        height=size,
        preserveAspectRatio=True,
        mask="auto"
    )

# ---------------- PDF ENGINE ----------------
def process_multi_sheet_pdf(sheets, sig_data, symbol_images):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)

    for sheet in sheets:
        meta = sheet["meta"]
        df = pd.DataFrame(sheet["rows"])

        if df.empty:
            c.drawString(100, height/2, "NO DATA FOUND")
            c.showPage()
            continue

        df["sort"] = df["Terminal Number"].astype(int)
        df = df.sort_values(["Row ID", "sort"])

        draw_page_template(c, width, height, sig_data, meta["sheet"], meta["heading"])

        info_x = PAGE_MARGIN + ((width - (2 * PAGE_MARGIN)) / 15)
        term_per_row = max(1, int((width - info_x - SAFETY_OFFSET - 60) // FIXED_GAP))

        y = height - 160
        rows_used = 0

        for rid, grp in df.groupby("Row ID", sort=False):
            chunks = [grp.iloc[i:i+term_per_row] for i in range(0, len(grp), term_per_row)]

            for chunk in chunks:
                if rows_used >= 6:
                    c.showPage()
                    draw_page_template(c, width, height, sig_data, meta["sheet"], meta["heading"])
                    y = height - 160
                    rows_used = 0

                x0 = info_x + SAFETY_OFFSET + 20
                c.setFont("Helvetica-Bold", 12)
                c.drawRightString(x0 - 30, y + 15, rid)

                for idx, row in enumerate(chunk.itertuples()):
                    tx = x0 + idx * FIXED_GAP

                    c.line(tx-3, y, tx-3, y+40)
                    c.line(tx+3, y, tx+3, y+40)
                    c.circle(tx, y, 3, fill=1)
                    c.circle(tx, y+40, 3, fill=1)

                    c.setFont("Helvetica-Bold", 8.5)
                    c.drawCentredString(tx, y+17, row._4)

                    # INLINE SYMBOL
                    for sym in sheet.get("symbols", []):
                        if sym["row"] == rid and sym["terminal"] == row._4:
                            img = symbol_images.get(sym["symbol"])
                            if img:
                                draw_inline_symbol(c, img, tx, y)

                y -= ROW_HEIGHT_SPACING
                rows_used += 1

        c.showPage()

    c.save()
    buffer.seek(0)
    return buffer

# ---------------- UI ----------------
with st.sidebar:
    st.header("📂 Resources")
    st.download_button("Download Sample TXT", SAMPLE_CONTENT, "sample_ctr.txt")

    st.subheader("🧩 Upload Symbols (PNG)")
    uploaded_symbols = st.file_uploader(
        "Upload PNG symbols",
        type=["png"],
        accept_multiple_files=True
    )

    sig_data = {
        "prep": st.text_input("Prepared By", "JE/SIG"),
        "chk1": st.text_input("Checked By", "SSE/SIG"),
        "chk2": st.text_input("Checked By", "ASTE"),
        "app": st.text_input("Approved By", "DSTE"),
    }

symbol_images = {}
if uploaded_symbols:
    for f in uploaded_symbols:
        symbol_images[f.name.replace(".png", "").upper()] = io.BytesIO(f.getvalue())

st.title("🚉 CTR Generator with Inline Symbols")

uploaded_file = st.file_uploader("Upload TXT", type=["txt"])

if uploaded_file:
    raw = uploaded_file.getvalue().decode("utf-8")
    st.session_state.sheets = parse_multi_sheet_txt(raw)

if "sheets" in st.session_state:
    if st.button("🚀 Generate PDF", use_container_width=True):
        st.session_state.pdf = process_multi_sheet_pdf(
            st.session_state.sheets,
            sig_data,
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
