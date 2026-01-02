import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.utils import ImageReader
import re
import io
from datetime import datetime

# --- UI CONFIG ---
st.set_page_config(page_title="CTR Generator Pro", layout="wide")

# --- CONSTANTS ---
PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

SAMPLE_CONTENT = """HEADING: TERMINAL CHART WITH DYNAMIC PLACEMENT
STATION: KUR
SIP: SIP/KUR/2026/01

SHEET: 01
LOCATION: GTY-01
A, 12HR [01 to 02], 12HHR [03 to 04], SP [05 to 10], 10C RR to GTY-01
B, 12HG [01 to 04], SP [05 to 12], 12C RR to GTY-01
@CHARGER: A, [01 to 04], Main Charger
@CHOKE: B, [05 to 08], Line Choke
"""

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
        
        # New Relative Symbol Parsing: @CHARGER: ROW, [START to END], Label
        elif upper_line.startswith("@"):
            match = re.match(r'@(CHARGER|CHOKE):\s*([A-Z]),\s*\[(\d+)\s*TO\s*(\d+)\](?:,\s*(.*))?', line, re.I)
            if match:
                current_symbols.append({
                    "type": match.group(1).upper(),
                    "row": match.group(2).upper(),
                    "start": int(match.group(3)),
                    "end": int(match.group(4)),
                    "label": match.group(5).strip() if match.group(5) else ""
                })
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
                            "Cable Detail": cable_detail, "Terminal Number": str(i).zfill(2),
                            "Num": i
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
    
    headers = ["PREPARED BY", "CHECKED BY", "CHECKED BY", "APPROVED BY", "LOCATION", "STATION", "SIP", "SHEET NO."]
    box_w = (total_footer_w - (total_footer_w / 15)) / 7
    for i in range(8):
        x_c = (info_x + (i * box_w)) - (box_w/2) if i > 0 else (PAGE_MARGIN + info_x)/2
        c.setFont("Helvetica-Bold", 9.0)
        c.drawCentredString(x_c, footer_y - 12, headers[i])
        val = f"{sheet_num:02}" if i == 7 else str(footer_values[i])
        c.drawCentredString(x_c, PAGE_MARGIN + (30 if i >= 4 else 5), val.upper())
    return info_x

def process_multi_sheet_pdf(sheets_list, sig_data, symbols_map):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        info_x = draw_page_template(c, width, height, [sig_data['prep'], sig_data['chk1'], sig_data['chk2'], sig_data['app'], meta['location'], meta['station'], meta['sip'], ""], meta['sheet'], meta['heading'])
        
        y_curr = height - 160
        row_y_map = {} # To track where each row ID is drawn for symbol placement
        
        if not df.empty:
            df = df.sort_values(by=['Row ID', 'Num'])
            for rid, group in df.groupby('Row ID', sort=False):
                row_y_map[rid] = y_curr
                x_start = info_x + SAFETY_OFFSET + 20
                
                # Draw Row ID
                c.setFont("Helvetica-Bold", 12)
                c.drawRightString(x_start - 30, y_curr + 15, str(rid))
                
                # Draw Terminals
                for idx, t in enumerate(group.to_dict('records')):
                    tx = x_start + (idx * FIXED_GAP)
                    c.circle(tx, y_curr+40, 3, fill=1)
                    c.circle(tx, y_curr, 3, fill=1)
                    c.setFont("Helvetica-Bold", 8.5)
                    c.drawCentredString(tx, y_curr+17, str(t['Terminal Number']).zfill(2))
                    
                    # Store X coordinate back into DF for symbol calculation
                    df.loc[(df['Row ID'] == rid) & (df['Num'] == t['Num']), 'x_coord'] = tx

                y_curr -= ROW_HEIGHT_SPACING

        # --- DRAW SYMBOLS BASED ON TERMINAL POSITIONS ---
        for sym in sheet.get('symbols', []):
            if sym['type'] in symbols_map and sym['row'] in row_y_map:
                try:
                    # Filter df for the specific row and terminal range
                    row_data = df[(df['Row ID'] == sym['row']) & (df['Num'] >= sym['start']) & (df['Num'] <= sym['end'])]
                    if not row_data.empty:
                        x_min = row_data['x_coord'].min()
                        x_max = row_data['x_coord'].max()
                        center_x = (x_min + x_max) / 2
                        target_y = row_y_map[sym['row']] + 75 # Place it above the terminals
                        
                        img_reader = ImageReader(io.BytesIO(symbols_map[sym['type']]))
                        sw, sh = 45, 45 # Default size for symbols
                        c.drawImage(img_reader, center_x - (sw/2), target_y, width=sw, height=sh, mask='auto')
                        
                        if sym['label']:
                            c.setFont("Helvetica-Bold", 8)
                            c.drawCentredString(center_x, target_y + sh + 5, sym['label'].upper())
                except Exception as e:
                    st.error(f"Placement Error: {e}")

        c.showPage() 
    c.save(); buffer.seek(0); return buffer

# --- UI LOGIC ---
with st.sidebar:
    st.header("🖼️ Equipment Assets")
    charger_img = st.file_uploader("Charger Image", type=['png', 'jpg'])
    choke_img = st.file_uploader("Choke Image", type=['png', 'jpg'])
    st.download_button("📥 Sample TXT", SAMPLE_CONTENT, "sample.txt", "text/plain")
    sig_data = {"prep": st.text_input("Prepared", "JE"), "chk1": st.text_input("SSE", "SSE"), "chk2": st.text_input("ASTE", "ASTE"), "app": st.text_input("DSTE", "DSTE")}

st.title("🚉 Dynamic CTR Placement")
uploaded_file = st.file_uploader("Upload .txt", type=["txt"])

if uploaded_file:
    sheets = parse_multi_sheet_txt(uploaded_file.getvalue().decode("utf-8"))
    if st.button("🚀 Generate PDF", use_container_width=True):
        s_map = {}
        if charger_img: s_map["CHARGER"] = charger_img.getvalue()
        if choke_img: s_map["CHOKE"] = choke_img.getvalue()
        pdf = process_multi_sheet_pdf(sheets, sig_data, s_map)
        st.download_button("📥 Download", pdf, "CTR_Final.pdf", "application/pdf")