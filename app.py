import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime

# --- 1. UI CONFIG ---
st.set_page_config(page_title="CTR Generator Pro", layout="wide", initial_sidebar_state="expanded")

# Initialize Session State
if 'sheets_data' not in st.session_state:
    st.session_state.sheets_data = []

# --- 2. CONSTANTS ---
PAGE_MARGIN, SAFETY_OFFSET, FIXED_GAP = 20, 42.5, 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

# --- 3. HELPER FUNCTIONS ---

def draw_group_line(c, x1, x2, y, is_top=True):
    c.setLineWidth(0.8)
    c.line(x1, y, x2, y)
    tick_size = 5 if is_top else -5
    c.line(x1, y, x1, y - tick_size)
    c.line(x2, y, x2, y - tick_size)

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
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(x_c, footer_y - 12, headers[i])
        val = f"{sheet_num:02}" if i == 7 else str(footer_values[i])
        c.drawCentredString(x_c, PAGE_MARGIN + 20, val.upper())
    return info_x

def parse_multi_sheet_txt(raw_text):
    sheets_data = []
    current_meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    current_rows = []
    term_keywords = ["SPARE", "RESERVED", "NI", "E3", "TERMINAL", "BLOCK", "LINK", "RESERVE", "SP", "CHR", "CHOKE", "CHARGER"]

    for line in raw_text.splitlines():
        line = line.strip()
        if not line: continue
        upper_line = line.upper()
        
        if upper_line.startswith("SHEET:"):
            if current_rows:
                sheets_data.append({"meta": current_meta.copy(), "rows": current_rows})
                current_rows = []
            val = re.search(r'\d+', line); current_meta["sheet"] = int(val.group()) if val else 1
        elif upper_line.startswith("STATION:"): current_meta["station"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("LOCATION:"): current_meta["location"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("SIP:"): current_meta["sip"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("HEADING:"): current_meta["heading"] = line.split(":", 1)[1].strip()
        else:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rid, last_part = parts[0].upper(), parts[-1].upper()
                is_cable = not any(key in last_part for key in term_keywords)
                cable_detail = last_part if (is_cable and len(parts) >= 3) else ""
                matches = re.findall(r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]', ",".join(parts[1:]), re.I)
                for func_text, start, end in matches:
                    for i in range(int(start), int(end) + 1):
                        current_rows.append({"Row ID": rid, "Function": func_text.strip().upper(), 
                                           "Cable Detail": cable_detail, "Terminal Number": str(i).zfill(2)})
    if current_rows: sheets_data.append({"meta": current_meta, "rows": current_rows})
    return sheets_data

def process_multi_sheet_pdf(sheets_list, sig_data):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    fs = {'head': 10.0, 'foot': 9.5, 'term': 8.5, 'row': 12.0}
    
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        if df.empty: continue
        df['sort_key'] = df['Terminal Number'].apply(lambda s: int(re.findall(r'\d+', str(s))[0]) if re.findall(r'\d+', str(s)) else 0)
        df = df.sort_values(by=['Row ID', 'sort_key'])
        
        f_vals = [sig_data['prep'], sig_data['chk1'], sig_data['chk2'], sig_data['app'], meta['location'], meta['station'], meta['sip'], "AUTO"]
        info_x = PAGE_MARGIN + ((width - (2 * PAGE_MARGIN)) / 15)
        term_per_row = int((width - info_x - SAFETY_OFFSET - 40) // FIXED_GAP)
        
        y_curr, rows_on_page, current_sheet_no = height - 160, 0, meta['sheet']
        draw_page_template(c, width, height, f_vals, current_sheet_no, meta['heading'])
        
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
                        draw_group_line(c, s_x-5, e_x+5, y_curr + y_off, is_top=is_h)
                        c.setFont("Helvetica-Bold", fs['head' if is_h else 'foot'])
                        text_y = y_curr + y_off + (12 if is_h else -20)
                        c.drawCentredString((s_x+e_x)/2, text_y, txt)
                y_curr -= ROW_HEIGHT_SPACING
                rows_on_page += 1
        c.showPage() 
    c.save(); buffer.seek(0); return buffer

# --- 4. MAIN INTERFACE ---
st.title("🚉 CTR Drawing Generator")

# File Upload (Main Page)
uploaded_file = st.file_uploader("📂 Step 1: Upload Your .txt File", type=["txt"])

if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    if not st.session_state.sheets_data:
        st.session_state.sheets_data = parse_multi_sheet_txt(raw_text)

if st.session_state.sheets_data:
    st.divider()
    
    # Signatures (Now on Main Page for visibility)
    st.subheader("✍️ Step 2: Signature Details")
    col1, col2, col3, col4 = st.columns(4)
    sig_data = {
        "prep": col1.text_input("Prepared By", "JE/SIG"),
        "chk1": col2.text_input("Checked (SSE)", "SSE/SIG"),
        "chk2": col3.text_input("Checked (ASTE)", "ASTE"),
        "app": col4.text_input("Approved (DSTE)", "DSTE")
    }

    # Data Editor
    st.subheader("📝 Step 3: Review & Edit Terminals")
    sheet_names = [f"Sheet {s['meta']['sheet']}: {s['meta']['location']}" for s in st.session_state.sheets_data]
    sel_idx = st.selectbox("Select Sheet", range(len(sheet_names)), format_func=lambda i: sheet_names[i])
    
    curr_rows = st.session_state.sheets_data[sel_idx]['rows']
    edited_df = st.data_editor(pd.DataFrame(curr_rows), num_rows="dynamic", use_container_width=True, key=f"ed_{sel_idx}")
    st.session_state.sheets_data[sel_idx]['rows'] = edited_df.to_dict('records')

    # Generation
    if st.button("🚀 Generate & Download PDF", type="primary", use_container_width=True):
        pdf_output = process_multi_sheet_pdf(st.session_state.sheets_data, sig_data)
        st.download_button("📥 Click Here to Download", pdf_output, f"CTR_{datetime.now().strftime('%H%M%S')}.pdf", "application/pdf", use_container_width=True)

    if st.button("🗑️ Clear All Data"):
        st.session_state.sheets_data = []
        st.rerun()