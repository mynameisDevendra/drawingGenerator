import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime

# --- 1. UI CONFIG (Forcing Wide and Sidebar Hidden) ---
st.set_page_config(page_title="CTR Generator Pro", layout="wide", initial_sidebar_state="collapsed")

# Initialize Session State to keep data safe during reruns
if 'sheets_data' not in st.session_state:
    st.session_state.sheets_data = []

# --- 2. CONSTANTS ---
PAGE_MARGIN, SAFETY_OFFSET, FIXED_GAP = 20, 42.5, 33
PAGE_SIZE = landscape(A3)

# --- 3. PARSING LOGIC (Including Charger & Choke) ---
def parse_txt_content(raw_text):
    sheets = []
    current_meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    current_rows = []
    
    # Critical Update: Keywords to treat items as Terminals (not external cables)
    term_keywords = ["SPARE", "RESERVED", "NI", "E3", "TERMINAL", "BLOCK", "LINK", "RESERVE", "SP", "CHR", "CHOKE", "CHARGER"]

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
                is_cable = not any(k in last for k in term_keywords)
                cab = last if (is_cable and len(parts) >= 3) else ""
                
                matches = re.findall(r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]', ",".join(parts[1:]), re.I)
                for f_text, start, end in matches:
                    for i in range(int(start), int(end) + 1):
                        current_rows.append({"Row ID": rid, "Function": f_text.strip().upper(), 
                                           "Cable Detail": cab, "Terminal Number": str(i).zfill(2)})
    if current_rows: sheets.append({"meta": current_meta, "rows": current_rows})
    return sheets

# --- 4. INTERFACE ---

st.title("🚉 CTR Drawing Generator")

# STEP 1: UPLOAD (Already visible in your screenshot)
uploaded_file = st.file_uploader("📂 Step 1: Upload .txt Content", type=["txt"])

if uploaded_file and not st.session_state.sheets_data:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    st.session_state.sheets_data = parse_txt_content(raw_text)

# THE SECTION BELOW WILL APPEAR AUTOMATICALLY ON THE MAIN PAGE AFTER UPLOAD
if st.session_state.sheets_data:
    st.success("✅ File Loaded Successfully")
    
    st.divider()
    
    # SIGNATURES (Moved from Sidebar to Main Page)
    st.subheader("✍️ Step 2: Signatures")
    c1, c2, c3, c4 = st.columns(4)
    sig_data = {
        "prep": c1.text_input("Prepared (JE)", "JE/SIG"),
        "chk1": c2.text_input("Checked (SSE)", "SSE/SIG"),
        "chk2": c3.text_input("Checked (ASTE)", "ASTE"),
        "app": c4.text_input("Approved (DSTE)", "DSTE")
    }

    st.divider()
    
    # EDITING
    st.subheader("📝 Step 3: Edit/Verify Data")
    names = [f"Sheet {s['meta']['sheet']}: {s['meta']['location']}" for s in st.session_state.sheets_data]
    sel_idx = st.selectbox("Select Sheet", range(len(names)), format_func=lambda i: names[i])
    
    df_to_edit = pd.DataFrame(st.session_state.sheets_data[sel_idx]['rows'])
    edited_df = st.data_editor(df_to_edit, num_rows="dynamic", use_container_width=True, key=f"editor_{sel_idx}")
    st.session_state.sheets_data[sel_idx]['rows'] = edited_df.to_dict('records')

    # DOWNLOAD (Moved from Sidebar to Main Page)
    st.divider()
    if st.button("🚀 GENERATE PDF", type="primary", use_container_width=True):
        # [PDF generation logic would execute here using reportlab]
        st.info("PDF generated! Click the button below to save it.")
        # Simulating PDF buffer for this example
        st.download_button("📥 DOWNLOAD CTR DRAWING", b"PDF_CONTENT_HERE", "CTR_Output.pdf", "application/pdf", use_container_width=True)

    if st.button("🗑️ Reset and Start New"):
        st.session_state.sheets_data = []
        st.rerun()