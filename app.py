import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from PIL import Image

# --- UI CONFIG ---
st.set_page_config(page_title="CTR Drawing System Pro", layout="wide")

# --- CONSTANTS ---
PAGE_MARGIN = 20
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 150 

# --- SYMBOL UPLOADER HELPER ---
def side_uploader(label):
    uploaded_file = st.sidebar.file_uploader(f"Upload {label} (PNG/JPG)", type=['png', 'jpg', 'jpeg'], key=label)
    if uploaded_file:
        img = Image.open(uploaded_file).convert("RGBA")
        return img
    return None

# --- SIDEBAR CONFIG ---
st.sidebar.header("🎨 Drawing Symbols")
symbol_config = {
    "CHARGER": {"img": side_uploader("Charger"), "key": "CHGR"},
    "FUSE": {"img": side_uploader("Fuse"), "key": "HR"},
    "CHOKE": {"img": side_uploader("Choke"), "key": "TPR"},
    "RESISTANCE": {"img": side_uploader("Resistance"), "key": "RR"}
}

with st.sidebar.expander("✒️ Signature Setup"):
    sig_data = {
        "prep": st.text_input("Prepared", "JE/SIG"),
        "chk1": st.text_input("SSE", "SSE/SIG"), 
        "chk2": st.text_input("ASTE", "ASTE"),
        "app": st.text_input("DSTE", "DSTE")
    }

# --- PARSING LOGIC ---
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
                middle_content = ",".join(parts[1:])
                cable_detail = parts[-1] if any(x in parts[-1].upper() for x in ["RR", "TO", "CABLE", "GTY"]) else ""
                
                pattern = r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]'
                matches = re.findall(pattern, middle_content, re.I)
                for match in matches:
                    func_text = match[0].strip().upper()
                    start, end = int(match[1]), int(match[2])
                    for i in range(start, end + 1):
                        current_rows.append({
                            "Row ID": rid, "Function": func_text, 
                            "Terminal Number": str(i).zfill(2), "Cable Detail": cable_detail
                        })
    if current_rows: sheets_data.append({"meta": current_meta, "rows": current_rows})
    return sheets_data

# --- PDF DRAWING HELPERS ---
def draw_terminal_symbol(c, x, y):
    c.setLineWidth(1)
    c.line(x-3, y, x-3, y+40)
    c.line(x+3, y, x+3, y+40)
    c.circle(x, y+40, 3, fill=1)
    c.circle(x, y, 3, fill=1)

def draw_page_template(c, width, height, footer_values, sheet_num, page_heading):
    c.setLineWidth(1.5)
    c.rect(PAGE_MARGIN, PAGE_MARGIN, width - (2 * PAGE_MARGIN), height - (2 * PAGE_MARGIN))
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 60, page_heading.upper())
    footer_y = PAGE_MARGIN + 60
    c.line(PAGE_MARGIN, footer_y, width - PAGE_MARGIN, footer_y)
    total_footer_w = width - (2 * PAGE_MARGIN)
    info_x = PAGE_MARGIN + (total_footer_w / 15)
    headers = ["PREPARED BY", "CHECKED BY", "CHECKED BY", "APPROVED BY", "LOCATION NO", "STATION", "SIP", "SHEET"]
    box_w = (total_footer_w - info_x) / 7
    for i in range(8):
        x = info_x + (i * box_w) if i > 0 else PAGE_MARGIN
        curr_w = info_x - PAGE_MARGIN if i == 0 else box_w
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(x + curr_w/2, footer_y - 15, headers[i])
        val = f"{sheet_num:02}" if i == 7 else str(footer_values[i])
        c.drawCentredString(x + curr_w/2, PAGE_MARGIN + 20, val.upper())
        if i < 7: c.line(x + curr_w, PAGE_MARGIN, x + curr_w, footer_y)
    return info_x + 30

def process_multi_sheet_pdf(sheets_list, sig_data, config):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    
    def get_special_info(func_name):
        for _, data in config.items():
            if data["key"] in func_name.upper() and data["img"]:
                # Remove the keyword from the name (e.g., 'CHGR 14T' -> '14T')
                clean_name = func_name.upper().replace(data["key"], "").strip()
                return data["img"], clean_name
        return None, func_name

    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        f_vals = [sig_data['prep'], sig_data['chk1'], sig_data['chk2'], sig_data['app'], meta['location'], meta['station'], meta['sip'], ""]
        start_x = draw_page_template(c, width, height, f_vals, meta['sheet'], meta['heading'])
        y_curr = height - 180
        
        for rid, group in df.groupby("Row ID", sort=False):
            c.setFont("Helvetica-Bold", 12)
            c.drawString(PAGE_MARGIN + 30, y_curr + 15, rid)
            group = group.reset_index(drop=True)
            
            # --- TERMINAL DRAWING ---
            for idx, row in group.iterrows():
                tx = start_x + (idx * FIXED_GAP)
                img, _ = get_special_info(row['Function'])
                # Only draw terminal link and number if NOT a special symbol
                if not img:
                    draw_terminal_symbol(c, tx, y_curr)
                    c.setFont("Helvetica", 8)
                    c.drawCentredString(tx, y_curr - 15, row['Terminal Number'])
                
            # --- OVERLAY SYMBOLS & LABELS ---
            func_groups = group.groupby(['Function', (group['Function'] != group['Function'].shift()).cumsum()]).agg(
                {'Terminal Number': ['min', 'max'], 'Function': 'first'}
            ).reset_index(drop=True)
            func_groups.columns = ['Start', 'End', 'Function']
            
            row_min_x, row_max_x = start_x, start_x
            for _, f_row in func_groups.iterrows():
                start_idx = group.index[group['Terminal Number'] == f_row['Start']][0]
                end_idx = group.index[group['Terminal Number'] == f_row['End']][0]
                x_min, x_max = start_x + (start_idx * FIXED_GAP), start_x + (end_idx * FIXED_GAP)
                row_max_x = max(row_max_x, x_max)
                
                special_img, display_name = get_special_info(f_row['Function'])
                
                if special_img:
                    # DRAW IMAGE & CLEAN NAME (No Brackets, No Numbers)
                    img_w, img_h = 50, 50
                    c.drawInlineImage(special_img, (x_min + x_max)/2 - img_w/2, y_curr - 5, width=img_w, height=img_h)
                    c.setFont("Helvetica-Bold", 10)
                    c.drawCentredString((x_min + x_max)/2, y_curr + 55, display_name)
                else:
                    # DRAW STANDARD BRACKETS & FULL NAME
                    c.setLineWidth(0.8)
                    c.line(x_min - 5, y_curr + 50, x_max + 5, y_curr + 50)
                    c.line(x_min - 5, y_curr + 50, x_min - 5, y_curr + 45)
                    c.line(x_max + 5, y_curr + 50, x_max + 5, y_curr + 45)
                    c.setFont("Helvetica-Bold", 10)
                    c.drawCentredString((x_min + x_max)/2, y_curr + 60, f_row['Function'])
            
            # --- CABLE DETAIL BRACKET ---
            cable_txt = group['Cable Detail'].iloc[0]
            if cable_txt:
                c.setLineWidth(0.8)
                c.line(row_min_x - 5, y_curr - 35, row_max_x + 5, y_curr - 35)
                c.line(row_min_x - 5, y_curr - 35, row_min_x - 5, y_curr - 30)
                c.line(row_max_x + 5, y_curr - 35, row_max_x + 5, y_curr - 30)
                c.setFont("Helvetica-Oblique", 9)
                c.drawCentredString((row_min_x + row_max_x)/2, y_curr - 50, cable_txt)
            y_curr -= ROW_HEIGHT_SPACING
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- MAIN APP ---
st.title("🚉 CTR Drawing Management System")
uploaded_file = st.file_uploader("Step 1: Upload Drawing TXT File", type=["txt"])
if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    st.session_state.sheets_data = parse_multi_sheet_txt(raw_text)

if 'sheets_data' in st.session_state:
    tabs = st.tabs(["📄 Data Editor & PDF Generation", "🖼️ Symbol Management"])
    with tabs[0]:
        sel = st.selectbox("Select Sheet", range(len(st.session_state.sheets_data)), 
                           format_func=lambda i: f"Sheet {st.session_state.sheets_data[i]['meta']['sheet']} - {st.session_state.sheets_data[i]['meta']['location']}")
        df_editor = pd.DataFrame(st.session_state.sheets_data[sel]['rows'])
        edited_df = st.data_editor(df_editor, num_rows="dynamic", use_container_width=True)
        st.session_state.sheets_data[sel]['rows'] = edited_df.to_dict('records')
        if st.button("🚀 Generate Final Technical PDF", use_container_width=True):
            pdf_file = process_multi_sheet_pdf(st.session_state.sheets_data, sig_data, symbol_config)
            st.download_button("📥 Download Official CTR PDF", pdf_file, f"CTR_Output.pdf", "application/pdf")