import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.utils import ImageReader
import re
import io
from datetime import datetime

# --- UI CONFIG & CUSTOM CSS ---
st.set_page_config(page_title="CTR Generator Pro", layout="wide")

st.markdown("""
    <style>
    div[data-baseweb="select"] { cursor: pointer !important; }
    .stSelectbox div { cursor: pointer !important; }
    </style>
    """, unsafe_allow_html=True)

# --- CONSTANTS ---
PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

SAMPLE_CONTENT = """HEADING: SAMPLE TERMINAL CHART
STATION: KUR
SIP: SIP/KUR/2025/01

SHEET: 01
LOCATION: GTY-01
A, 12HR [01 to 02], 12HHR [03 to 04], SP [05 to 10], 10C RR to GTY-01
B, 12HG [01 to 04], SP [05 to 12], 12C RR to GTY-01
@CHARGER: 50, 450, 60, 60, Primary Charger
@CHOKE: 150, 450, 40, 40, Filter Choke

SHEET: 02
LOCATION: LOC-02 
A, 24TPR [01 to 02], 12C GTY-01 to LOC-02
@CHARGER: 400, 450, 50, 50, Standby Unit
"""

# --- CORE FUNCTIONS ---

def parse_multi_sheet_txt(raw_text):
    sheets_data = []
    current_meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    current_rows = []
    current_symbols = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line: continue
        upper_line = line.upper()
        
        if upper_line.startswith("SHEET:"):
            if current_rows or current_symbols:
                sheets_data.append({"meta": current_meta.copy(), "rows": current_rows, "symbols": current_symbols})
                current_rows, current_symbols = [], []
            val = re.search(r'\d+', line)
            if val: current_meta["sheet"] = int(val.group())
        elif upper_line.startswith("STATION:"):
            current_meta["station"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("LOCATION:"):
            current_meta["location"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("SIP:"):
            current_meta["sip"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("HEADING:"):
            current_meta["heading"] = line.split(":", 1)[1].strip()
        
        # New Symbol Parsing Logic
        elif upper_line.startswith("@CHARGER:") or upper_line.startswith("@CHOKE:"):
            parts = line.split(':', 1)
            sym_type = parts[0][1:].strip().upper()
            params = parts[1].strip().split(',')
            if len(params) >= 4:
                try:
                    current_symbols.append({
                        "type": sym_type,
                        "x": float(params[0]), "y": float(params[1]),
                        "w": float(params[2]), "h": float(params[3]),
                        "label": params[4].strip() if len(params) > 4 else ""
                    })
                except ValueError: pass

        else:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rid = parts[0].upper()
                middle_part = ",".join(parts[1:])
                last_part = parts[-1].upper()
                term_keywords = ["SPARE", "RESERVED", "NI", "E3", "TERMINAL", "BLOCK", "LINK", "RESERVE", "SP"]
                is_cable = not any(key in last_part for key in term_keywords)
                cable_detail = last_part if (is_cable and len(parts) >= 3) else ""
                
                pattern = r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]'
                matches = re.findall(pattern, middle_part, re.I)
                for match in matches:
                    func_text = match[0].strip().upper()
                    start, end = int(match[1]), int(match[2])
                    for i in range(start, end + 1):
                        current_rows.append({
                            "Row ID": rid, "Function": func_text, 
                            "Cable Detail": cable_detail, "Terminal Number": str(i).zfill(2)
                        })
    if current_rows or current_symbols:
        sheets_data.append({"meta": current_meta, "rows": current_rows, "symbols": current_symbols})
    return sheets_data

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
    
    remaining_w = total_footer_w - (total_footer_w / 15)
    box_w = remaining_w / 7 
    dividers = [info_x + (i * box_w) for i in range(8)] 
    for x in dividers[:-1]: c.line(x, PAGE_MARGIN, x, footer_y)

    headers = ["PREPARED BY", "CHECKED BY", "CHECKED BY", "APPROVED BY", "LOCATION", "STATION", "SIP", "SHEET NO."]
    for i in range(8):
        x_start = PAGE_MARGIN if i == 0 else dividers[i-1]
        x_end = dividers[i]
        x_c = (x_start + x_end) / 2
        c.setFont("Helvetica-Bold", 9.0)
        c.drawCentredString(x_c, footer_y - 12, headers[i])
        val = f"{sheet_num:02}" if i == 7 else str(footer_values[i])
        if i in [4, 5, 6, 7]:
            c.drawCentredString(x_c, PAGE_MARGIN + 30, val.upper())
        else:
            c.drawCentredString(x_c, PAGE_MARGIN + 5, val.upper())
    return info_x

def process_multi_sheet_pdf(sheets_list, sig_data, symbols_map):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    
    fs = {'head': 10.0, 'foot': 9.5, 'term': 8.5, 'row': 12.0}
    
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        if not df.empty:
            df['sort_key'] = df['Terminal Number'].apply(lambda s: int(re.findall(r'\d+', str(s))[0]) if re.findall(r'\d+', str(s)) else 0)
            df = df.sort_values(by=['Row ID', 'sort_key'])
        
        f_vals = [sig_data['prep'], sig_data['chk1'], sig_data['chk2'], sig_data['app'], meta['location'], meta['station'], meta['sip'], ""]
        info_x = PAGE_MARGIN + ((width - (2 * PAGE_MARGIN)) / 15)
        term_per_row = int((width - info_x - SAFETY_OFFSET - 40) // FIXED_GAP)
        
        y_curr, rows_on_page, current_sheet_no = height - 160, 0, meta['sheet']
        draw_page_template(c, width, height, f_vals, current_sheet_no, meta['heading'])
        
        # Draw Symbols for this sheet
        for sym in sheet.get('symbols', []):
            img_data = symbols_map.get(sym['type'])
            if img_data:
                # Convert top-down UI coords to bottom-up PDF coords
                # x is relative to left margin, y is relative to top margin
                pdf_x = PAGE_MARGIN + sym['x']
                pdf_y = height - PAGE_MARGIN - sym['y'] - sym['h']
                c.drawImage(ImageReader(io.BytesIO(img_data)), pdf_x, pdf_y, width=sym['w'], height=sym['h'], mask='auto')
                if sym['label']:
                    c.setFont("Helvetica", 8)
                    c.drawCentredString(pdf_x + sym['w']/2, pdf_y - 10, sym['label'])

        for rid, group in df.groupby('Row ID', sort=False):
            terms = group.to_dict('records')
            chunks = [terms[i:i + term_per_row] for i in range(0, len(terms), term_per_row)]
            for chunk in chunks:
                if rows_on_page >= 6:
                    c.showPage()
                    current_sheet_no += 1
                    draw_page_template(c, width, height, f_vals, current_sheet_no, meta['heading'])
                    y_curr, rows_on_page = height - 160, 0
                
                x_start = info_x + SAFETY_OFFSET + 20
                c.setFont("Helvetica-Bold", fs['row']); c.drawRightString(x_start - 30, y_curr + 15, str(rid))
                
                for idx, t in enumerate(chunk):
                    tx = x_start + (idx * FIXED_GAP)
                    c.setLineWidth(1); c.line(tx-3, y_curr, tx-3, y_curr+40); c.line(tx+3, y_curr, tx+3, y_curr+40)
                    c.circle(tx, y_curr+40, 3, fill=1); c.circle(tx, y_curr, 3, fill=1)
                    c.setFont("Helvetica-Bold", fs['term']); c.drawRightString(tx-8, y_curr+17, str(t['Terminal Number']).zfill(2))
                
                for key, is_h, y_off in [('Function', True, 53.5), ('Cable Detail', False, -13.5)]:
                    i = 0
                    while i < len(chunk):
                        txt = str(chunk[i][key]).upper().strip()
                        if not txt: i += 1; continue
                        start_i, end_i = i, i
                        while i < len(chunk) and str(chunk[i][key]).upper().strip() == txt: end_i = i; i += 1
                        s_x, e_x = x_start + (start_i * FIXED_GAP), x_start + (end_i * FIXED_GAP)
                        c.line(s_x-5, y_curr+y_off, e_x+5, y_curr+y_off) # Simplfied group line
                        c.setFont("Helvetica-Bold", fs['head' if is_h else 'foot'])
                        c.drawCentredString((s_x+e_x)/2, y_curr + y_off + (12 if is_h else -20), txt)
                y_curr -= ROW_HEIGHT_SPACING
                rows_on_page += 1
        c.showPage() 
    c.save(); buffer.seek(0); return buffer

# --- UI LOGIC ---

with st.sidebar:
    st.header("📂 Resources")
    st.download_button("📥 Sample TXT", SAMPLE_CONTENT, "sample.txt", "text/plain", use_container_width=True)
    
    st.divider()
    st.header("🎨 Symbol Upload")
    charger_img = st.file_uploader("Charger Image", type=['png', 'jpg'])
    choke_img = st.file_uploader("Choke Image", type=['png', 'jpg'])
    
    st.divider()
    sig_data = {
        "prep": st.text_input("Prepared By", "JE/SIG"),
        "chk1": st.text_input("Checked By (SSE)", "SSE/SIG"),
        "chk2": st.text_input("Checked By (ASTE)", "ASTE"),
        "app": st.text_input("Approved By", "DSTE")
    }

st.title("🚉 CTR Generator with Symbol Placement")

uploaded_file = st.file_uploader("Upload .txt Drawing Data", type=["txt"])

if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    sheets = parse_multi_sheet_txt(raw_text)
    
    if sheets:
        st.success(f"Parsed {len(sheets)} sheets.")
        
        if st.button("🚀 Generate PDF", type="primary", use_container_width=True):
            s_map = {}
            if charger_img: s_map["CHARGER"] = charger_img.getvalue()
            if choke_img: s_map["CHOKE"] = choke_img.getvalue()
            
            pdf_out = process_multi_sheet_pdf(sheets, sig_data, s_map)
            st.download_button("📥 Download PDF", pdf_out, "CTR_Drawing.pdf", "application/pdf", use_container_width=True)