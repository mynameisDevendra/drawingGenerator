import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime

# --- UI CONFIG ---
st.set_page_config(page_title="CTR Generator Pro", layout="wide")

# Initialize Session State for sheets_data if not present
if 'sheets_data' not in st.session_state:
    st.session_state.sheets_data = []

# --- CONSTANTS ---
PAGE_MARGIN, SAFETY_OFFSET, FIXED_GAP = 20, 42.5, 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

# --- CORE PARSING LOGIC ---
def parse_multi_sheet_txt(raw_text):
    sheets_data = []
    current_meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    current_rows = []
    
    # Keyword list for terminal-only (not cable) connections
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

# --- PDF GENERATION & TEMPLATE (Omitted for brevity, use existing draw functions) ---
# ... [Include draw_group_line, draw_page_template, process_multi_sheet_pdf here] ...

# --- MAIN UI ---
st.title("🚉 Multi-Sheet CTR Generator")

# 1. FILE UPLOADER (Keep this at the top level)
uploaded_file = st.file_uploader("📂 Step 1: Upload Drawing Content (.txt)", type=["txt"])

if uploaded_file:
    # Only parse if we haven't already or if a new file is uploaded
    raw_text = uploaded_file.getvalue().decode("utf-8")
    parsed = parse_multi_sheet_txt(raw_text)
    # Store in session state to prevent disappearance
    if not st.session_state.sheets_data or st.button("Reload File Data"):
        st.session_state.sheets_data = parsed

# 2. EDITING SECTION
if st.session_state.sheets_data:
    st.divider()
    sheet_names = [f"Sheet {s['meta']['sheet']}: {s['meta']['location']}" for s in st.session_state.sheets_data]
    sel_idx = st.selectbox("Select Sheet to Edit", range(len(sheet_names)), format_func=lambda i: sheet_names[i])
    
    # Use data_editor to allow changes
    curr_rows = st.session_state.sheets_data[sel_idx]['rows']
    edited_df = st.data_editor(pd.DataFrame(curr_rows), num_rows="dynamic", use_container_width=True, key=f"editor_{sel_idx}")
    
    # Save edits back to session state
    st.session_state.sheets_data[sel_idx]['rows'] = edited_df.to_dict('records')

    # 3. GENERATION
    st.sidebar.header("📜 Signatures")
    sig_data = {
        "prep": st.sidebar.text_input("Prepared", "JE/SIG"),
        "chk1": st.sidebar.text_input("Checked 1", "SSE/SIG"),
        "chk2": st.sidebar.text_input("Checked 2", "ASTE"),
        "app": st.sidebar.text_input("Approved", "DSTE")
    }

    if st.button("🚀 Generate PDF Drawing", type="primary"):
        # Ensure you include the process_multi_sheet_pdf function here
        pdf = process_multi_sheet_pdf(st.session_state.sheets_data, sig_data)
        st.download_button("📥 Download PDF", pdf, f"CTR_{datetime.now().strftime('%d%m%Y')}.pdf", "application/pdf")