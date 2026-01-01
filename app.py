import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime
from PIL import Image, ImageDraw

# --- UI CONFIG ---
st.set_page_config(page_title="CTR Drawing System", layout="wide")

# --- SYMBOL UPLOADER HELPER ---
def side_uploader(label):
    uploaded_file = st.sidebar.file_uploader(f"Upload {label} (PNG/JPG)", type=['png', 'jpg', 'jpeg'], key=label)
    if uploaded_file:
        img = Image.open(uploaded_file).convert("RGBA")
        img.thumbnail((100, 100)) 
        st.sidebar.image(img, width=60, caption=f"Active {label}")
        return img
    return None

# --- SIDEBAR ---
st.sidebar.header("🎨 Drawing Symbols")
symbols = {
    "FUSE": side_uploader("Fuse"),
    "CHOKE": side_uploader("Choke"),
    "CHARGER": side_uploader("Charger"),
    "RESISTANCE": side_uploader("Resistance")
}

with st.sidebar.expander("✒️ Signature Setup"):
    sig_data = {
        "prep": st.text_input("Prepared", "JE/SIG"),
        "chk1": st.text_input("SSE", "SSE/SIG"), 
        "chk2": st.text_input("ASTE", "ASTE"),
        "app": st.text_input("DSTE", "DSTE")
    }

# --- CORE PARSING LOGIC ---
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
        elif upper_line.startswith("STATION:"): current_meta["station"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("LOCATION:"): current_meta["location"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("SIP:"): current_meta["sip"] = line.split(":", 1)[1].strip()
        elif upper_line.startswith("HEADING:"): current_meta["heading"] = line.split(":", 1)[1].strip()
        else:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rid = parts[0].upper()
                middle_part = ",".join(parts[1:])
                pattern = r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]'
                matches = re.findall(pattern, middle_part, re.I)
                for match in matches:
                    func_text = match[0].strip().upper()
                    start, end = int(match[1]), int(match[2])
                    for i in range(start, end + 1):
                        current_rows.append({"Row ID": rid, "Function": func_text, "Terminal Number": str(i).zfill(2)})
    if current_rows: sheets_data.append({"meta": current_meta, "rows": current_rows})
    return sheets_data

# --- DRAWING STUDIO LOGIC ---
def generate_schematic_preview(sheets_data, uploaded_symbols):
    canvas_w, canvas_h = 1400, 1000
    img_out = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img_out)
    
    x_start, y_start = 100, 100
    x_curr, y_curr = x_start, y_start

    for sheet in sheets_data:
        df = pd.DataFrame(sheet['rows'])
        if df.empty: continue
        
        groups = df.groupby(['Row ID', 'Function']).agg({'Terminal Number': ['min', 'max']}).reset_index()
        groups.columns = ['Row', 'Function', 'Start', 'End']

        for _, row in groups.iterrows():
            func = str(row['Function']).upper()
            sym_to_draw = None
            
            if "CHR" in func: sym_to_draw = uploaded_symbols.get("CHARGER")
            elif "HR" in func: sym_to_draw = uploaded_symbols.get("FUSE")
            elif "TPR" in func: sym_to_draw = uploaded_symbols.get("CHOKE")
            elif "RR" in func: sym_to_draw = uploaded_symbols.get("RESISTANCE")

            if sym_to_draw:
                img_out.paste(sym_to_draw, (x_curr, y_curr))
                draw.text((x_curr, y_curr + 110), f"{func} ({row['Start']}-{row['End']})", fill="black")
            else:
                draw.rectangle([x_curr, y_curr, x_curr+80, y_curr+80], outline="red", width=2)
                draw.text((x_curr+5, y_curr+30), f"NO SYM\n{func}", fill="red")

            x_curr += 220
            if x_curr > canvas_w - 200:
                x_curr = x_start
                y_curr += 250
                
    return img_out

# --- MAIN APP ---
st.title("🚉 CTR Drawing Studio")

# 1. FILE UPLOADER (Outside tabs so it's always visible)
uploaded_file = st.file_uploader("Upload Drawing TXT File", type=["txt"])

if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    st.session_state.sheets_data = parse_multi_sheet_txt(raw_text)
    st.success("File uploaded and parsed successfully!")

# 2. SHOW TABS ONLY IF DATA EXISTS
if 'sheets_data' in st.session_state:
    tabs = st.tabs(["📄 Data Editor", "🖼️ Drawing Studio"])

    with tabs[0]:
        st.header("Terminal Table Editor")
        sel = st.selectbox("Select Sheet to Edit", range(len(st.session_state.sheets_data)), 
                           format_func=lambda i: f"Sheet {st.session_state.sheets_data[i]['meta']['sheet']}")
        
        df_editor = pd.DataFrame(st.session_state.sheets_data[sel]['rows'])
        edited_df = st.data_editor(df_editor, num_rows="dynamic", use_container_width=True)
        st.session_state.sheets_data[sel]['rows'] = edited_df.to_dict('records')
        
        st.info("The Generate PDF button is generally here in the Table Editor tab.")

    with tabs[1]:
        st.header("Schematic Drawing Preview")
        # THIS IS THE GENERATE BUTTON
        if st.button("🛠️ Generate Schematic Preview"):
            drawing = generate_schematic_preview(st.session_state.sheets_data, symbols)
            st.image(drawing, caption="Generated Layout")
            
            buf = io.BytesIO()
            drawing.save(buf, format="PNG")
            st.download_button("📥 Download Schematic PNG", buf.getvalue(), "schematic.png", "image/png")
else:
    st.warning("Please upload a .txt file to start.")