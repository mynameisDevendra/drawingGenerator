import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime

# --- 1. BASIC PAGE SETUP ---
# This must be the first Streamlit command
st.set_page_config(page_title="CTR Generator", layout="wide")

# --- 2. THE ABSOLUTE FIRST THING: UPLOAD BOX ---
st.header("🚉 CTR Drawing Generator")
uploaded_file = st.file_uploader("📂 UPLOAD YOUR .TXT FILE HERE", type=["txt"])

# --- 3. SESSION STATE & DATA PROCESSING ---
if 'sheets_data' not in st.session_state:
    st.session_state.sheets_data = []

# Terminal keywords including Charger and Choke
TERM_KEYWORDS = ["SPARE", "RESERVED", "NI", "E3", "TERMINAL", "BLOCK", "LINK", "RESERVE", "SP", "CHR", "CHOKE", "CHARGER"]

def parse_txt(raw_text):
    sheets = []
    current_meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    current_rows = []
    
    for line in raw_text.splitlines():
        line = line.strip()
        if not line: continue
        up = line.upper()
        
        if up.startswith("SHEET:"):
            if current_rows: sheets.append({"meta": current_meta.copy(), "rows": current_rows})
            current_rows = []
            val = re.search(r'\d+', line)
            current_meta["sheet"] = int(val.group()) if val else 1
        elif up.startswith("STATION:"): current_meta["station"] = line.split(":", 1)[1].strip()
        elif up.startswith("LOCATION:"): current_meta["location"] = line.split(":", 1)[1].strip()
        elif up.startswith("SIP:"): current_meta["sip"] = line.split(":", 1)[1].strip()
        elif up.startswith("HEADING:"): current_meta["heading"] = line.split(":", 1)[1].strip()
        else:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rid, last = parts[0].upper(), parts[-1].upper()
                is_cable = not any(k in last for k in TERM_KEYWORDS)
                cab = last if (is_cable and len(parts) >= 3) else ""
                matches = re.findall(r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]', ",".join(parts[1:]), re.I)
                for f_text, start, end in matches:
                    for i in range(int(start), int(end) + 1):
                        current_rows.append({"Row ID": rid, "Function": f_text.strip().upper(), 
                                           "Cable Detail": cab, "Terminal Number": str(i).zfill(2)})
    if current_rows: sheets.append({"meta": current_meta, "rows": current_rows})
    return sheets

# --- 4. PDF ENGINE ---
def draw_line(c, x1, x2, y, top=True):
    c.setLineWidth(0.8)
    c.line(x1, y, x2, y)
    t = 5 if top else -5
    c.line(x1, y, x1, y-t); c.line(x2, y, x2, y-t)

def generate_pdf(data, sigs):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A3))
    w, h = landscape(A3)
    
    for sheet in data:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        df['sort'] = df['Terminal Number'].apply(lambda x: int(re.findall(r'\d+', str(x))[0]) if re.findall(r'\d+', str(x)) else 0)
        df = df.sort_values(by=['Row ID', 'sort'])
        
        # Draw Border & Footer
        c.rect(20, 20, w-40, h-40)
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(w/2, h-60, meta['heading'].upper())
        
        # Basic Footer Text
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, 40, f"STATION: {meta['station']}  |  LOCATION: {meta['location']}  |  SIP: {meta['sip']}  |  SHEET: {meta['sheet']}")
        c.drawRightString(w-40, 40, f"PREP: {sigs['prep']} | CHK: {sigs['chk']} | APP: {sigs['app']}")
        
        # Draw Rows
        y = h - 150
        gap = 33
        for rid, group in df.groupby('Row ID', sort=False):
            x = 100
            c.setFont("Helvetica-Bold", 12)
            c.drawString(60, y+15, rid)
            for _, row in group.iterrows():
                # Draw terminal circles
                c.circle(x, y+40, 3, fill=1); c.circle(x, y, 3, fill=1)
                c.line(x-3, y, x-3, y+40); c.line(x+3, y, x+3, y+40)
                c.setFont("Helvetica-Bold", 8)
                c.drawCentredString(x, y+17, row['Terminal Number'])
                x += gap
            y -= 100
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- 5. LOGIC FLOW ---
if uploaded_file:
    # Only process if session state is empty
    if not st.session_state.sheets_data:
        raw = uploaded_file.getvalue().decode("utf-8")
        st.session_state.sheets_data = parse_txt(raw)

if st.session_state.sheets_data:
    st.success("File Uploaded Successfully!")
    
    st.subheader("✍️ Signature Details")
    c1, c2, c3 = st.columns(3)
    sigs = {
        "prep": c1.text_input("Prepared By", "JE/SIG"),
        "chk": c2.text_input("Checked By", "SSE/SIG"),
        "app": c3.text_input("Approved By", "DSTE")
    }

    st.subheader("📝 Edit Sheet Data")
    names = [f"Sheet {s['meta']['sheet']}: {s['meta']['location']}" for s in st.session_state.sheets_data]
    idx = st.selectbox("Select Sheet", range(len(names)), format_func=lambda i: names[i])
    
    edited = st.data_editor(pd.DataFrame(st.session_state.sheets_data[idx]['rows']), num_rows="dynamic", use_container_width=True)
    st.session_state.sheets_data[idx]['rows'] = edited.to_dict('records')

    if st.button("🚀 GENERATE PDF", type="primary"):
        final_pdf = generate_pdf(st.session_state.sheets_data, sigs)
        st.download_button("📥 DOWNLOAD NOW", final_pdf, "CTR_Drawing.pdf", "application/pdf")

    if st.button("RESET"):
        st.session_state.sheets_data = []
        st.rerun()