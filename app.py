import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime
from PIL import Image

# --- CONFIG ---
st.set_page_config(page_title="CTR Drawing Generator", layout="wide")

PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 130  # Increased to fit cable labels
CABLE_BAR_Y_OFFSET = 60   # Height of the grouping bar above terminal

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
                    "is_symbol": True,
                    "cable_name": None
                })
        else:
            # Format: A, CABLE_NAME[01 to 10], SPARE[11 to 12]
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rid = parts[0].upper()
                middle_part = ",".join(parts[1:])
                pattern = r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]'
                matches = re.findall(pattern, middle_part, re.I)
                for m in matches:
                    cable_name, start, end = m[0].strip().upper(), int(m[1]), int(m[2])
                    for i in range(start, end + 1):
                        current_rows.append({
                            "Row ID": rid, 
                            "Function": cable_name, 
                            "Terminal Number": str(i).zfill(2), 
                            "is_symbol": False,
                            "cable_name": cable_name
                        })
    if current_rows: 
        sheets_data.append({"meta": current_meta, "rows": current_rows})
    return sheets_data

def draw_page_template(c, width, height, meta, sheet_no):
    c.setLineWidth(1.5)
    c.rect(PAGE_MARGIN, PAGE_MARGIN, width - (2 * PAGE_MARGIN), height - (2 * PAGE_MARGIN))
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 60, meta['heading'].upper())
    c.setFont("Helvetica-Bold", 10)
    c.drawString(PAGE_MARGIN + 20, PAGE_MARGIN + 35, f"STATION: {meta['station']} | LOCATION: {meta['location']}")
    c.drawRightString(width - PAGE_MARGIN - 20, PAGE_MARGIN + 35, f"SHEET: {sheet_no}")

def generate_pdf(sheets_list, symbol_images):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        df['sort_key'] = pd.to_numeric(df['Terminal Number'])
        df = df.sort_values(['Row ID', 'sort_key'])
        
        y_curr = height - 180
        draw_page_template(c, width, height, meta, meta['sheet'])
        
        info_x = PAGE_MARGIN + ((width - (2 * PAGE_MARGIN)) / 15)
        
        for rid, group in df.groupby('Row ID', sort=False):
            x_start = info_x + SAFETY_OFFSET + 20
            c.setFont("Helvetica-Bold", 12)
            c.drawRightString(x_start - 30, y_curr + 10, str(rid))
            
            chunk = group.to_dict('records')
            
            # --- CABLE GROUPING DRAWING ---
            groups = []
            if chunk:
                curr_g = {"name": chunk[0]['cable_name'], "start": 0, "count": 1}
                for i in range(1, len(chunk)):
                    if chunk[i]['cable_name'] == curr_g['name'] and curr_g['name'] is not None:
                        curr_g['count'] += 1
                    else:
                        groups.append(curr_g)
                        curr_g = {"name": chunk[i]['cable_name'], "start": i, "count": 1}
                groups.append(curr_g)

            for g in groups:
                if g['name']:
                    lx_start = x_start + (g['start'] * FIXED_GAP)
                    lx_end = lx_start + ((g['count'] - 1) * FIXED_GAP)
                    # Draw bracket
                    c.setLineWidth(0.7)
                    c.line(lx_start - 5, y_curr + CABLE_BAR_Y_OFFSET, lx_end + 5, y_curr + CABLE_BAR_Y_OFFSET)
                    c.line(lx_start - 5, y_curr + CABLE_BAR_Y_OFFSET, lx_start - 5, y_curr + CABLE_BAR_Y_OFFSET - 10)
                    c.line(lx_end + 5, y_curr + CABLE_BAR_Y_OFFSET, lx_end + 5, y_curr + CABLE_BAR_Y_OFFSET - 10)
                    # Label
                    c.setFont("Helvetica-BoldOblique", 7)
                    c.drawCentredString((lx_start + lx_end)/2, y_curr + CABLE_BAR_Y_OFFSET + 3, g['name'])

            # --- TERMINAL DRAWING ---
            for idx, t in enumerate(chunk):
                tx = x_start + (idx * FIXED_GAP)
                
                if t.get('is_symbol'):
                    name = t['Function']
                    if name in symbol_images:
                        c.drawImage(symbol_images[name], tx-12, y_curr+5, width=24, height=28, mask='auto')
                    c.setFont("Helvetica-Bold", 8)
                    c.drawCentredString(tx, y_curr + 40, name)
                else:
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
st.sidebar.header("⚙️ Settings & Assets")
symbols_list = ["CHARGER", "CHOKE", "FUSE", "RELAY", "RESISTANCE"]
sym_images = {}

with st.sidebar:
    for s in symbols_list:
        f = st.file_uploader(f"Upload icon for {s}", type=["png", "jpg"], key=s)
        if f: sym_images[s] = Image.open(f)

st.subheader("1. Upload Data")
uploaded_file = st.file_uploader("Choose a TXT file", type=["txt"])

if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    data = parse_txt_with_symbols(raw_text)
    
    if data:
        st.success(f"Parsed {len(data)} sheet(s) successfully.")
        
        st.subheader("2. Review & Generate")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🛠️ Generate PDF Drawing", use_container_width=True):
                pdf_output = generate_pdf(data, sym_images)
                st.session_state['pdf_output'] = pdf_output
        
        if 'pdf_output' in st.session_state:
            with col2:
                st.download_button(
                    label="📥 Download PDF",
                    data=st.session_state['pdf_output'],
                    file_name=f"CTR_Output_{datetime.now().strftime('%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
    else:
        st.error("Could not parse file. Please ensure the format matches 'ROW, CABLE[01 to 10]'.")
else:
    st.info("Awaiting TXT file upload...")