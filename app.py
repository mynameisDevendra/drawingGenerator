import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime
from PIL import Image

# --- CONFIG ---
st.set_page_config(page_title="CTR Symbol Generator", layout="wide")

PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

# --- FUNCTIONS ---

def parse_txt_with_symbols(raw_text):
    sheets_data = []
    current_meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    current_rows = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line: continue
        
        upper_line = line.upper()
        if upper_line.startswith("SHEET:"):
            if current_rows:
                sheets_data.append({"meta": current_meta.copy(), "rows": current_rows})
                current_rows = []
            val = re.search(r'\d+', line)
            if val: current_meta["sheet"] = int(val.group())
        elif upper_line.startswith("STATION:"):
            current_meta["station"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("LOCATION:"):
            current_meta["location"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("SYMBOL:"):
            # Format: SYMBOL: FUSE [A, 05]
            match = re.search(r'SYMBOL:\s*(\w+)\s*\[(\w+),\s*(\d+)\]', line, re.I)
            if match:
                current_rows.append({
                    "Row ID": match.group(2).upper(),
                    "Function": match.group(1).upper(),
                    "Terminal Number": match.group(3).zfill(2),
                    "is_symbol": True
                })
        else:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rid = parts[0].upper()
                middle_part = ",".join(parts[1:])
                pattern = r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]'
                matches = re.findall(pattern, middle_part, re.I)
                for m in matches:
                    func, start, end = m[0].strip().upper(), int(m[1]), int(m[2])
                    for i in range(start, end + 1):
                        current_rows.append({
                            "Row ID": rid, "Function": func, 
                            "Terminal Number": str(i).zfill(2), "is_symbol": False
                        })
    if current_rows: sheets_data.append({"meta": current_meta, "rows": current_rows})
    return sheets_data

def draw_page_template(c, width, height, meta, sheet_no):
    c.setLineWidth(1.5)
    c.rect(PAGE_MARGIN, PAGE_MARGIN, width - (2 * PAGE_MARGIN), height - (2 * PAGE_MARGIN))
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 60, meta['heading'].upper())
    # Simple footer for visibility
    c.setFont("Helvetica-Bold", 10)
    c.drawString(PAGE_MARGIN + 20, PAGE_MARGIN + 20, f"STATION: {meta['station']} | LOCATION: {meta['location']} | SHEET: {sheet_no}")

def generate_pdf(sheets_list, symbol_images):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        df['sort_key'] = pd.to_numeric(df['Terminal Number'])
        df = df.sort_values(['Row ID', 'sort_key'])
        
        y_curr = height - 160
        draw_page_template(c, width, height, meta, meta['sheet'])
        
        info_x = PAGE_MARGIN + ((width - (2 * PAGE_MARGIN)) / 15)
        
        for rid, group in df.groupby('Row ID', sort=False):
            x_start = info_x + SAFETY_OFFSET + 20
            c.setFont("Helvetica-Bold", 12)
            c.drawRightString(x_start - 30, y_curr + 15, str(rid))
            
            chunk = group.to_dict('records')
            for idx, t in enumerate(chunk):
                tx = x_start + (idx * FIXED_GAP)
                
                if t.get('is_symbol'):
                    # --- SYMBOL ONLY ---
                    name = t['Function']
                    if name in symbol_images:
                        c.drawImage(symbol_images[name], tx-12, y_curr+5, width=24, height=28, mask='auto')
                    c.setFont("Helvetica-Bold", 9)
                    c.drawCentredString(tx, y_curr + 40, name)
                    # NO terminals, NO numbers printed here
                else:
                    # --- NORMAL TERMINAL ---
                    c.setLineWidth(1)
                    c.line(tx-3, y_curr, tx-3, y_curr+30)
                    c.line(tx+3, y_curr, tx+3, y_curr+30)
                    c.circle(tx, y_curr+30, 2, fill=1)
                    c.circle(tx, y_curr, 2, fill=1)
                    c.setFont("Helvetica", 8)
                    c.drawCentredString(tx, y_curr + 12, t['Terminal Number'])
            
            y_curr -= ROW_HEIGHT_SPACING
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- UI ---
st.title("🚉 CTR Drawing Generator")

with st.sidebar:
    st.header("1. Upload Symbols")
    symbols = ["CHARGER", "CHOKE", "FUSE", "RELAY", "RESISTANCE"]
    sym_images = {}
    for s in symbols:
        f = st.file_uploader(f"Icon for {s}", type=["png", "jpg"], key=s)
        if f: sym_images[s] = Image.open(f)

uploaded_file = st.file_uploader("2. Upload TXT File", type=["txt"])

if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    data = parse_txt_with_symbols(raw_text)
    
    if st.button("Generate Drawing"):
        out_pdf = generate_pdf(data, sym_images)
        st.download_button("Download PDF", out_pdf, "CTR_Drawing.pdf")