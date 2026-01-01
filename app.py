import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime
from PIL import Image, ImageDraw

# --- UI CONFIG ---
st.set_page_config(page_title="CTR Drawing System Pro", layout="wide")

# --- CONSTANTS ---
PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

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

# --- PARSING & PDF LOGIC ---
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
                        current_rows.append({"Row ID": rid, "Function": func_text, "Terminal Number": str(i).zfill(2), "Cable Detail": ""})
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
    headers = ["PREPARED BY", "CHECKED BY", "CHECKED BY", "APPROVED BY", "LOC/GOOMTY", "STATION", "SIP", "SHEET"]
    for i in range(8):
        x_start = PAGE_MARGIN if i == 0 else dividers[i-1]
        x_end = dividers[i]
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString((x_start+x_end)/2, footer_y - 12, headers[i])
        val = f"{sheet_num:02}" if i == 7 else str(footer_values[i])
        c.drawCentredString((x_start+x_end)/2, PAGE_MARGIN + 20, val.upper())
    return info_x

def process_multi_sheet_pdf(sheets_list, sig_data):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        f_vals = [sig_data['prep'], sig_data['chk1'], sig_data['chk2'], sig_data['app'], meta['location'], meta['station'], meta['sip'], ""]
        info_x = draw_page_template(c, width, height, f_vals, meta['sheet'], meta['heading'])
        # Simple rendering for the PDF terminals
        y_curr = height - 150
        for rid, group in df.groupby("Row ID"):
            c.setFont("Helvetica-Bold", 12)
            c.drawString(info_x + 20, y_curr, f"ROW {rid}: " + ", ".join(group['Function'].unique()))
            y_curr -= 30
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- DRAWING STUDIO LOGIC ---
def generate_schematic_preview(sheets_data, uploaded_symbols):
    canvas_w, canvas_h = 1400, 1000
    img_out = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img_out)
    x_curr, y_curr = 100, 100
    for sheet in sheets_data:
        df = pd.DataFrame(sheet['rows'])
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
                draw.text((x_curr, y_curr + 110), f"{func}", fill="black")
            else:
                draw.rectangle([x_curr, y_curr, x_curr+80, y_curr+80], outline="red", width=2)
                draw.text((x_curr+5, y_curr+30), f"MISSING\n{func}", fill="red")
            x_curr += 220
            if x_curr > canvas_w - 200:
                x_curr = 100; y_curr += 250
    return img_out

# --- MAIN APP ---
st.title("🚉 CTR Drawing Management System")

uploaded_file = st.file_uploader("Step 1: Upload Drawing TXT File", type=["txt"])

if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    st.session_state.sheets_data = parse_multi_sheet_txt(raw_text)

if 'sheets_data' in st.session_state:
    tabs = st.tabs(["📄 Data Editor & PDF", "🖼️ Drawing Studio"])

    with tabs[0]:
        st.header("1. Edit Terminal Data")
        sel = st.selectbox("Select Sheet", range(len(st.session_state.sheets_data)), 
                           format_func=lambda i: f"Sheet {st.session_state.sheets_data[i]['meta']['sheet']}")
        
        df_editor = pd.DataFrame(st.session_state.sheets_data[sel]['rows'])
        edited_df = st.data_editor(df_editor, num_rows="dynamic", use_container_width=True)
        st.session_state.sheets_data[sel]['rows'] = edited_df.to_dict('records')
        
        st.divider()
        st.header("2. Finalize Document")
        # THIS IS THE PDF GENERATE BUTTON
        if st.button("🚀 Generate Technical PDF Document", use_container_width=True):
            pdf_file = process_multi_sheet_pdf(st.session_state.sheets_data, sig_data)
            st.download_button("📥 Download Official PDF", pdf_file, "CTR_Official_Report.pdf", "application/pdf", use_container_width=True)

    with tabs[1]:
        st.header("Component Schematic Preview")
        if st.button("🛠️ Generate Schematic Preview"):
            drawing = generate_schematic_preview(st.session_state.sheets_data, symbols)
            st.image(drawing)
            buf = io.BytesIO()
            drawing.save(buf, format="PNG")
            st.download_button("📥 Download PNG", buf.getvalue(), "schematic.png", "image/png")