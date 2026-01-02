import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime

# --- UI CONFIG ---
st.set_page_config(page_title="CTR Generator Pro", layout="wide")

# Initialize Session State
if 'sheets_data' not in st.session_state:
    st.session_state.sheets_data = []

# --- CONSTANTS ---
PAGE_MARGIN, SAFETY_OFFSET, FIXED_GAP = 20, 42.5, 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

# --- FUNCTIONS ---

def parse_multi_sheet_txt(raw_text):
    sheets_data = []
    current_meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    current_rows = []
    
    # Includes Charger (CHR/CHARGER) and Choke logic
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

def generate_pdf(sheets_list, sig_data):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    w, h = PAGE_SIZE
    
    for sheet in sheets_list:
        meta = sheet['meta']
        # Drawing standard frame and headers
        c.rect(PAGE_MARGIN, PAGE_MARGIN, w - (2*PAGE_MARGIN), h - (2*PAGE_MARGIN))
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(w/2, h-60, meta['heading'].upper())
        
        # Simple Footer with signatures
        c.setFont("Helvetica", 10)
        footer_text = f"STATION: {meta['station']} | LOC: {meta['location']} | SIP: {meta['sip']} | SHEET: {meta['sheet']}"
        c.drawString(40, 40, footer_text)
        c.drawRightString(w-40, 40, f"PREP: {sig_data['prep']} | CHK: {sig_data['chk']} | APP: {sig_data['app']}")
        
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- MAIN UI ---
st.title("🚉 CTR Drawing Generator")

# 1. UPLOADER
uploaded_file = st.file_uploader("📂 Step 1: Upload Your .txt File", type=["txt"])

if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    if not st.session_state.sheets_data:
        st.session_state.sheets_data = parse_multi_sheet_txt(raw_text)

# 2. ACTIONS (Only shows after upload)
if st.session_state.sheets_data:
    st.divider()
    st.subheader("✍️ Step 2: Signature Details")
    c1, c2, c3 = st.columns(3)
    sig_data = {
        "prep": c1.text_input("Prepared By", "JE/SIG"),
        "chk": c2.text_input("Checked By", "SSE/SIG"),
        "app": c3.text_input("Approved By", "DSTE")
    }

    st.subheader("📝 Step 3: Edit Data")
    sheet_names = [f"Sheet {s['meta']['sheet']}: {s['meta']['location']}" for s in st.session_state.sheets_data]
    sel_idx = st.selectbox("Select Sheet", range(len(sheet_names)), format_func=lambda i: sheet_names[i])
    
    edited_df = st.data_editor(pd.DataFrame(st.session_state.sheets_data[sel_idx]['rows']), num_rows="dynamic", use_container_width=True)
    st.session_state.sheets_data[sel_idx]['rows'] = edited_df.to_dict('records')

    if st.button("🚀 GENERATE PDF", type="primary", use_container_width=True):
        pdf = generate_pdf(st.session_state.sheets_data, sig_data)
        st.download_button("📥 DOWNLOAD PDF", pdf, "CTR_Drawing.pdf", "application/pdf", use_container_width=True)