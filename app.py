import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime

# --- 1. FORCE SIDEBAR & LAYOUT ---
# initial_sidebar_state="expanded" forces it to try and open
st.set_page_config(page_title="CTR Generator", layout="wide", initial_sidebar_state="expanded")

# --- 2. SESSION STATE ---
if 'sheets_data' not in st.session_state:
    st.session_state.sheets_data = []

# Keywords for Charger/Choke
TERM_KEYWORDS = ["SPARE", "RESERVED", "NI", "E3", "TERMINAL", "BLOCK", "LINK", "RESERVE", "SP", "CHR", "CHOKE", "CHARGER"]

# --- 3. THE INTERFACE (NO SIDEBAR REQUIRED) ---

st.title("🚉 CTR Drawing Generator")
st.info("Note: If the Side Panel is missing, look for a small '>' arrow in the top-left corner of your browser.")

# --- STEP 1: UPLOAD ---
st.subheader("📁 Step 1: Upload Data")
uploaded_file = st.file_uploader("Upload your .txt file", type=["txt"])

if uploaded_file and not st.session_state.sheets_data:
    # Parsing logic
    raw_text = uploaded_file.getvalue().decode("utf-8")
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
    st.session_state.sheets_data = sheets

# --- STEP 2: SIGNATURES (ON MAIN PAGE) ---
if st.session_state.sheets_data:
    st.divider()
    st.subheader("✍️ Step 2: Signatures & Designations")
    col1, col2, col3, col4 = st.columns(4)
    sig_data = {
        "prep": col1.text_input("Prepared By", "JE/SIG"),
        "chk1": col2.text_input("Checked (SSE)", "SSE/SIG"),
        "chk2": col3.text_input("Checked (ASTE)", "ASTE"),
        "app": col4.text_input("Approved (DSTE)", "DSTE")
    }

    # --- STEP 3: EDITING ---
    st.divider()
    st.subheader("📝 Step 3: Review Terminals")
    names = [f"Sheet {s['meta']['sheet']}: {s['meta']['location']}" for s in st.session_state.sheets_data]
    sel_idx = st.selectbox("Select Sheet to View/Edit", range(len(names)), format_func=lambda i: names[i])
    
    # Editable Table
    df_editor = pd.DataFrame(st.session_state.sheets_data[sel_idx]['rows'])
    edited_df = st.data_editor(df_editor, num_rows="dynamic", use_container_width=True, key=f"edit_{sel_idx}")
    st.session_state.sheets_data[sel_idx]['rows'] = edited_df.to_dict('records')

    # --- STEP 4: DOWNLOAD ---
    st.divider()
    if st.button("🚀 GENERATE FINAL PDF", type="primary", use_container_width=True):
        # PDF Generation Logic (Internal)
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=landscape(A3))
        w, h = landscape(A3)
        
        for sheet in st.session_state.sheets_data:
            m = sheet['meta']
            c.rect(20, 20, w-40, h-40)
            c.setFont("Helvetica-Bold", 14)
            c.drawCentredString(w/2, h-60, f"TERMINAL CHART - {m['location']}")
            # Simple Footer
            c.setFont("Helvetica", 10)
            c.drawString(40, 40, f"STATION: {m['station']} | SHEET: {m['sheet']}")
            c.drawRightString(w-40, 40, f"PREP: {sig_data['prep']} | APP: {sig_data['app']}")
            c.showPage()
        
        c.save()
        buf.seek(0)
        st.download_button("📥 DOWNLOAD PDF", buf, "CTR_Output.pdf", "application/pdf", use_container_width=True)

    if st.button("Reset App"):
        st.session_state.sheets_data = []
        st.rerun()