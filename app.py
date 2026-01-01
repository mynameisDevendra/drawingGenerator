import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# --- UI CONFIG & CUSTOM CSS ---
st.set_page_config(page_title="CTR Generator Pro & Drawing Studio", layout="wide")

st.markdown("""
    <style>
    div[data-baseweb="select"] { cursor: pointer !important; }
    .stSelectbox div { cursor: pointer !important; }
    </style>
    """, unsafe_allow_html=True)

# --- CONSTANTS ---
PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

SAMPLE_CONTENT = """HEADING: SAMPLE TERMINAL CHART
STATION: KUR
SIP: SIP/KUR/2025/01

SHEET: 01
LOCATION: GTY-01
A, 12HR [01 to 02], 12HHR [03 to 04], 12DR [05 to 06], SP [07 to 10], KTINPR [11 to 12], CHRPR [13 to 14], SP [15 to 30], 30C RR to GTY-01
B, 12HG [01 to 04], 12HHG [05 to 08], 12DG [09 to 12], SP [13 to 24], 24C RR to GTY-01
B, 16TPR [01 to 02], SP [03 to 06], 06C RR to GTY-01
"""

# --- SIDEBAR: SYMBOL UPLOADS ---
st.sidebar.header("🎨 Drawing Symbols")

def side_uploader(label):
    uploaded_file = st.sidebar.file_uploader(f"Upload {label} (PNG)", type=['png'], key=label)
    if uploaded_file:
        img = Image.open(uploaded_file).convert("RGBA")
        img.thumbnail((100, 100)) 
        st.sidebar.image(img, width=40)
        return img
    return None

symbols = {
    "FUSE": side_uploader("Fuse"),
    "CHOKE": side_uploader("Choke"),
    "CHARGER": side_uploader("Charger"),
    "RESISTANCE": side_uploader("Resistance")
}

# --- CORE FUNCTIONS (PDF GENERATION) ---

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

    headers = ["PREPARED BY", "CHECKED BY", "CHECKED BY", "APPROVED BY", "LOCATION NO / GOOMTY / RR", "STATION", "SIP", "SHEET NO."]
    
    for i in range(8):
        x_start = PAGE_MARGIN if i == 0 else dividers[i-1]
        x_end = dividers[i]
        x_c = (x_start + x_end) / 2
        c.setFont("Helvetica-Bold", 9.0)
        c.drawCentredString(x_c, footer_y - 12, headers[i])
        val = f"{sheet_num:02}" if i == 7 else str(footer_values[i])
        
        if i in [4, 5, 6, 7]:
            c.drawCentredString(x_c, PAGE_MARGIN + 30, val.upper())
        else:
            c.drawCentredString(x_c, PAGE_MARGIN + 5, val.upper())
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
                    c.showPage(); current_sheet_no += 1
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
                        c.drawCentredString((s_x+e_x)/2, y_curr + y_off + (12 if is_h else -20), txt)
                y_curr -= ROW_HEIGHT_SPACING; rows_on_page += 1
        c.showPage() 
    c.save(); buffer.seek(0); return buffer

# --- DRAWING STUDIO: IMPROVED LOGIC ---

def generate_schematic_preview(sheets_data, uploaded_symbols):
    canvas_w, canvas_h = 1400, 800
    img_out = Image.new("RGBA", (canvas_w, canvas_h), "white")
    draw = ImageDraw.Draw(img_out)
    
    x_offset, y_offset = 80, 80
    
    for sheet in sheets_data:
        df = pd.DataFrame(sheet['rows'])
        if df.empty: continue
        
        # GROUP BY FUNCTION TO AVOID DUPLICATE SYMBOLS FOR EVERY TERMINAL
        summary = df.groupby(['Row ID', 'Function']).agg({'Terminal Number': ['min', 'max']}).reset_index()
        summary.columns = ['Row', 'Function', 'Start', 'End']

        for _, row in summary.iterrows():
            func = str(row['Function']).upper()
            sym_to_draw = None
            
            # Precise Matching
            if "CHR" in func and uploaded_symbols["CHARGER"]: 
                sym_to_draw = uploaded_symbols["CHARGER"]
            elif "TPR" in func and uploaded_symbols["CHOKE"]: 
                sym_to_draw = uploaded_symbols["CHOKE"]
            elif "RR" in func and uploaded_symbols["RESISTANCE"]: 
                sym_to_draw = uploaded_symbols["RESISTANCE"]
            elif "HR" in func and uploaded_symbols["FUSE"]: 
                sym_to_draw = uploaded_symbols["FUSE"]

            if sym_to_draw:
                # Paste the actual uploaded symbol
                img_out.paste(sym_to_draw, (x_offset, y_offset), sym_to_draw)
                # Add Label
                label = f"{func}\n({row['Start']}-{row['End']})"
                draw.text((x_offset, y_offset + 105), label, fill="black")
            else:
                # If no symbol, draw a generic terminal block placeholder
                draw.rectangle([x_offset, y_offset, x_offset+60, y_offset+40], outline="blue", width=2)
                draw.text((x_offset+5, y_offset+45), func[:8], fill="blue")

            x_offset += 150
            if x_offset > canvas_w - 150:
                x_offset = 80
                y_offset += 180
    
    return img_out

# --- MAIN UI LOGIC ---

with st.sidebar:
    st.header("📂 Data & Config")
    st.download_button("📥 Sample TXT", SAMPLE_CONTENT, "sample.txt", "text/plain", use_container_width=True)
    with st.expander("✒️ Signature Setup"):
        sig_data = {
            "prep": st.text_input("Prepared", "JE/SIG"),
            "chk1": st.text_input("SSE", "SSE/SIG"), 
            "chk2": st.text_input("ASTE", "ASTE"),
            "app": st.text_input("DSTE", "DSTE")
        }

st.title("🚉 CTR Drawing Management System")

tabs = st.tabs(["📄 CTR Table Editor", "🖼️ Drawing Studio (Symbols)"])

with tabs[0]:
    uploaded_file = st.file_uploader("Upload Drawing TXT", type=["txt"])
    if uploaded_file:
        raw_text = uploaded_file.getvalue().decode("utf-8")
        st.session_state.sheets_data = parse_multi_sheet_txt(raw_text)

    if 'sheets_data' in st.session_state:
        sheet_names = [f"Sheet {s['meta']['sheet']}: {s['meta']['location']}" for s in st.session_state.sheets_data]
        sel_idx = st.selectbox("Select Sheet to Edit", range(len(sheet_names)), format_func=lambda i: sheet_names[i])
        
        curr_rows = st.session_state.sheets_data[sel_idx]['rows']
        edited_df = st.data_editor(pd.DataFrame(curr_rows), num_rows="dynamic", use_container_width=True)
        st.session_state.sheets_data[sel_idx]['rows'] = edited_df.to_dict('records')
        
        col1, col2 = st.columns(2)
        if col1.button("🚀 Generate Technical PDF", use_container_width=True):
            pdf = process_multi_sheet_pdf(st.session_state.sheets_data, sig_data)
            st.download_button("📥 Download PDF", pdf, "CTR_Output.pdf", "application/pdf", use_container_width=True)

with tabs[1]:
    st.header("Component Layout Preview")
    st.info("Symbols are grouped by function. Upload PNGs in the sidebar to see them here.")
    
    if 'sheets_data' in st.session_state:
        if st.button("🛠️ Generate Schematic Preview"):
            drawing = generate_schematic_preview(st.session_state.sheets_data, symbols)
            st.image(drawing, caption="Visual Component Layout")
            
            buf = io.BytesIO()
            drawing.save(buf, format="PNG")
            st.download_button("📥 Download Schematic PNG", buf.getvalue(), "schematic.png", "image/png")
    else:
        st.warning("Please upload a .txt file in the first tab first.")