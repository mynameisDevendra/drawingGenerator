import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime
from PIL import Image

# --- UI CONFIG ---
st.set_page_config(page_title="CTR Symbol Generator", layout="wide")

# --- CONSTANTS ---
PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

# --- CORE FUNCTIONS ---

def parse_multi_sheet_txt(raw_text):
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
            # Format: SYMBOL: Type [Row, Position] -> e.g., SYMBOL: FUSE [A, 05]
            parts = re.search(r'SYMBOL:\s*(\w+)\s*\[(\w+),\s*(\d+)\]', line, re.I)
            if parts:
                current_rows.append({
                    "Row ID": parts.group(2).upper(),
                    "Function": parts.group(1).upper(),
                    "Cable Detail": "",
                    "Terminal Number": parts.group(3).zfill(2),
                    "is_symbol": True
                })
        else:
            # Standard terminal parsing logic
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rid = parts[0].upper()
                middle_part = ",".join(parts[1:])
                pattern = r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]'
                matches = re.findall(pattern, middle_part, re.I)
                for match in matches:
                    func_text = match[0].strip().upper()
                    start, end = int(match[1]), int(match[2])
                    for i in range(start, end + 1):
                        current_rows.append({
                            "Row ID": rid, "Function": func_text, 
                            "Cable Detail": parts[-1].upper(), "Terminal Number": str(i).zfill(2),
                            "is_symbol": False
                        })
    if current_rows: sheets_data.append({"meta": current_meta, "rows": current_rows})
    return sheets_data

def process_multi_sheet_pdf(sheets_list, sig_data, symbol_images):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        df['sort_key'] = df['Terminal Number'].apply(lambda s: int(s) if str(s).isdigit() else 0)
        df = df.sort_values(by=['Row ID', 'sort_key'])
        
        f_vals = [sig_data['prep'], sig_data['chk1'], sig_data['chk2'], sig_data['app'], meta['location'], meta['station'], meta['sip'], "AUTO"]
        info_x = PAGE_MARGIN + ((width - (2 * PAGE_MARGIN)) / 15)
        term_per_row = int((width - info_x - SAFETY_OFFSET - 40) // FIXED_GAP)
        
        y_curr, rows_on_page, current_sheet_no = height - 160, 0, meta['sheet']
        # (Template drawing logic remains same as original)
        from __main__ import draw_page_template 
        draw_page_template(c, width, height, f_vals, current_sheet_no, meta['heading'])
        
        for rid, group in df.groupby('Row ID', sort=False):
            terms = group.to_dict('records')
            chunks = [terms[i:i + term_per_row] for i in range(0, len(terms), term_per_row)]
            for chunk in chunks:
                x_start = info_x + SAFETY_OFFSET + 20
                c.setFont("Helvetica-Bold", 12); c.drawRightString(x_start - 30, y_curr + 15, str(rid))
                
                for idx, t in enumerate(chunk):
                    tx = x_start + (idx * FIXED_GAP)
                    
                    if t.get('is_symbol') and t['Function'] in symbol_images:
                        # --- SYMBOL RENDERING ---
                        img = symbol_images[t['Function']]
                        # Draw symbol image (centered on terminal position)
                        c.drawImage(img, tx - 12, y_curr + 5, width=24, height=30, mask='auto')
                        # Print Name Above
                        c.setFont("Helvetica-Bold", 10)
                        c.drawCentredString(tx, y_curr + 45, t['Function'])
                        # (Terminals and range lines skipped for symbols)
                    else:
                        # --- STANDARD TERMINAL RENDERING ---
                        c.setLineWidth(1); c.line(tx-3, y_curr, tx-3, y_curr+40); c.line(tx+3, y_curr, tx+3, y_curr+40)
                        c.circle(tx, y_curr+40, 3, fill=1); c.circle(tx, y_curr, 3, fill=1)
                        c.setFont("Helvetica-Bold", 8.5); c.drawRightString(tx-8, y_curr+17, str(t['Terminal Number']).zfill(2))
                
                # Render range lines only for Non-Symbols
                # (Logic for Function/Cable text grouping goes here, filtered by is_symbol == False)
                
                y_curr -= ROW_HEIGHT_SPACING
                rows_on_page += 1
        c.showPage() 
    c.save(); buffer.seek(0); return buffer

# --- RE-USING YOUR TEMPLATE DRAWING FUNCTION ---
def draw_page_template(c, width, height, footer_values, sheet_num, page_heading):
    c.setLineWidth(1.5)
    c.rect(PAGE_MARGIN, PAGE_MARGIN, width - (2 * PAGE_MARGIN), height - (2 * PAGE_MARGIN))
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 60, page_heading.upper())
    footer_y = PAGE_MARGIN + 60
    c.line(PAGE_MARGIN, footer_y, width - PAGE_MARGIN, footer_y)
    total_footer_w = width - (2 * PAGE_MARGIN)
    info_x = PAGE_MARGIN + (total_footer_w / 15)
    c.line(info_x, PAGE_MARGIN, info_x, height - PAGE_MARGIN)
    return info_x

# --- UI LOGIC ---

with st.sidebar:
    st.header("🎨 Symbol Library")
    sym_list = ["CHARGER", "CHOKE", "FUSE", "RELAY", "RESISTANCE"]
    uploaded_symbols = {}
    for s in sym_list:
        img_file = st.file_uploader(f"Upload {s} Icon", type=["png", "jpg", "jpeg"], key=s)
        if img_file:
            uploaded_symbols[s] = Image.open(img_file)

    st.divider()
    sig_data = {"prep": "JE/SIG", "chk1": "SSE/SIG", "chk2": "ASTE", "app": "DSTE"}

st.title("🚉 Multi-Sheet CTR with Special Symbols")

st.info("""**Note on TXT Format for Symbols:** Add lines like: `SYMBOL: FUSE [A, 05]` to place a Fuse on Row A at Terminal 05.""")

uploaded_file = st.file_uploader("📂 Upload Drawing Content (.txt)", type=["txt"])

if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    sheets_data = parse_multi_sheet_txt(raw_text)
    
    if st.button("🚀 Generate PDF with Symbols", type="primary"):
        pdf = process_multi_sheet_pdf(sheets_data, sig_data, uploaded_symbols)
        st.download_button("📥 Download PDF", pdf, "CTR_Symbols.pdf", "application/pdf")