import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.utils import ImageReader
import re
import io
import os
from datetime import datetime

# --- UI CONFIG & DIRECTORY SETUP ---
st.set_page_config(page_title="CTR Generator Pro", layout="wide")

if not os.path.exists("symbols"):
    os.makedirs("symbols")

# --- SYMBOL LIBRARY ---
SYMBOL_LIB = {
    "@CH": {"file": "CHARGER.png", "w": 30, "h": 30, "desc": "Charger Symbol"},
    "@FS": {"file": "FUSE.png", "w": 18, "h": 24, "desc": "Fuse Symbol"},
    "@RY": {"file": "RELAY.png", "w": 28, "h": 22, "desc": "Relay Symbol"},
    "@CK": {"file": "CHOKE (2).png", "w": 25, "h": 20, "desc": "Choke Symbol"},
    "@RT": {"file": "RT.png", "w": 20, "h": 20, "desc": "RT Symbol"},
    "@SP": {"file": None, "w": 0, "h": 0, "desc": "Blank Space Gap"}
}

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
        elif upper_line.startswith("SIP:"):
            current_meta["sip"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("HEADING:"):
            current_meta["heading"] = line.split(":", 1)[1].strip()
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
    if current_rows: sheets_data.append({"meta": current_meta, "rows": current_rows})
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
        y_pos = PAGE_MARGIN + 30 if i in [4, 5, 6, 7] else PAGE_MARGIN + 5
        c.drawCentredString(x_c, y_pos, val.upper())
    return info_x

def process_multi_sheet_pdf(sheets_list, sig_data):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    fs = {'head': 10.0, 'foot': 9.5, 'term': 8.5, 'row': 12.0}
    
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
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
                
                # Pre-process chunk to mark where symbols are
                has_symbol = [any(code in str(t['Function']).upper() for code in SYMBOL_LIB.keys()) for t in chunk]

                for idx, t in enumerate(chunk):
                    tx = x_start + (idx * FIXED_GAP)
                    func_text = str(t['Function']).upper().strip()
                    active_code = next((code for code in SYMBOL_LIB.keys() if code in func_text), None)
                    
                    if active_code == "@SP":
                        t['Function'] = func_text.replace("@SP", "").strip()
                    elif active_code:
                        sym_data = SYMBOL_LIB[active_code]
                        img_path = os.path.join("symbols", sym_data["file"])
                        if os.path.exists(img_path):
                            img = ImageReader(img_path)
                            sw, sh = sym_data["w"], sym_data["h"]
                            c.drawImage(img, tx - (sw/2), (y_curr + 20) - (sh/2), width=sw, height=sh, mask='auto', preserveAspectRatio=True)
                        t['Function'] = func_text.replace(active_code, "").strip()
                    else:
                        c.setLineWidth(1)
                        c.line(tx-3, y_curr, tx-3, y_curr+40); c.line(tx+3, y_curr, tx+3, y_curr+40)
                        c.circle(tx, y_curr+40, 3, fill=1); c.circle(tx, y_curr, 3, fill=1)
                        c.setFont("Helvetica-Bold", fs['term'])
                        c.drawRightString(tx-8, y_curr+17, str(t['Terminal Number']).zfill(2))

                # Labels: Skip Cable Detail if a Symbol is present in that slot
                for key, is_h, y_off in [('Function', True, 53.5), ('Cable Detail', False, -13.5)]:
                    i = 0
                    while i < len(chunk):
                        # NEW: If it's a cable detail row AND a symbol is here, skip drawing text
                        if not is_h and has_symbol[i]: 
                            i += 1
                            continue
                            
                        txt = str(chunk[i][key]).upper().strip()
                        if not txt: 
                            i += 1
                            continue
                        
                        start_i, end_i = i, i
                        while i < len(chunk) and str(chunk[i][key]).upper().strip() == txt:
                            # Also stop grouping if we hit a symbol in cable detail mode
                            if not is_h and has_symbol[i]: break 
                            end_i = i
                            i += 1
                        
                        s_x, e_x = x_start + (start_i * FIXED_GAP), x_start + (end_i * FIXED_GAP)
                        c.setLineWidth(0.8); c.line(s_x-5, y_curr+y_off, e_x+5, y_curr+y_off)
                        tick = 5 if is_h else -5
                        c.line(s_x-5, y_curr+y_off, s_x-5, y_curr+y_off-tick); c.line(e_x+5, y_curr+y_off, e_x+5, y_curr+y_off-tick)
                        c.setFont("Helvetica-Bold", fs['head' if is_h else 'foot'])
                        c.drawCentredString((s_x+e_x)/2, y_curr+y_off+(12 if is_h else -20), txt)
                        
                y_curr -= ROW_HEIGHT_SPACING
                rows_on_page += 1
        c.showPage() 
    c.save(); buffer.seek(0); return buffer

# --- UI LOGIC ---

with st.sidebar:
    st.header("📤 Symbol Management")
    uploaded_sym = st.file_uploader("Upload PNG library", type=["png"], accept_multiple_files=True)
    if uploaded_sym:
        for file in uploaded_sym:
            with open(os.path.join("symbols", file.name), "wb") as f:
                f.write(file.getbuffer())
        st.success(f"Loaded {len(uploaded_sym)} images.")

    st.divider()
    st.markdown("### 🔣 Keywords")
    for k, v in SYMBOL_LIB.items():
        st.write(f"**{k}** : {v['desc']}")
    
    st.divider()
    with st.expander("✒️ Signatures"):
        sig_data = {"prep": st.text_input("Prepared", "JE/SIG"), "chk1": st.text_input("SSE", "SSE/SIG"), 
                    "chk2": st.text_input("ASTE", "ASTE"), "app": st.text_input("DSTE", "DSTE")}

st.title("🚉 CTR Generator Pro (Symbol Cable Correction)")

uploaded_file = st.file_uploader("📂 Upload .txt list", type=["txt"])

if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    st.session_state.sheets_data = parse_multi_sheet_txt(raw_text)

if 'sheets_data' in st.session_state:
    sheet_names = [f"Sheet {s['meta']['sheet']}: {s['meta']['location']}" for s in st.session_state.sheets_data]
    sel_idx = st.selectbox("Select Sheet", range(len(sheet_names)), format_func=lambda i: sheet_names[i])
    curr_rows = st.session_state.sheets_data[sel_idx]['rows']
    edited_df = st.data_editor(pd.DataFrame(curr_rows), num_rows="dynamic", use_container_width=True)
    st.session_state.sheets_data[sel_idx]['rows'] = edited_df.to_dict('records')

    if st.button("🚀 Generate PDF", type="primary", use_container_width=True):
        pdf = process_multi_sheet_pdf(st.session_state.sheets_data, sig_data)
        st.download_button("📥 Download PDF", pdf, f"CTR_{datetime.now().strftime('%d%m%Y')}.pdf", "application/pdf", use_container_width=True)