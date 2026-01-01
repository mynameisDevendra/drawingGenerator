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
ROW_HEIGHT_SPACING = 160 

# --- SIDEBAR: SYMBOL UPLOADS ---
st.sidebar.header("🎨 Drawing Symbols")

def side_uploader(label):
    uploaded_file = st.sidebar.file_uploader(f"Upload {label} (PNG)", type=['png'], key=label)
    if uploaded_file:
        img = Image.open(uploaded_file).convert("RGBA")
        return img
    return None

symbol_config = {
    "FUSE": {"img": side_uploader("Fuse"), "key": "FUSE"},
    "CHOKE": {"img": side_uploader("Choke"), "key": "CHK"},
    "CHARGER": {"img": side_uploader("Charger"), "key": "CHGR"},
    "RESISTANCE": {"img": side_uploader("Resistance"), "key": "RS"},
    "RELAY": {"img": side_uploader("Relay"), "key": "RELAY"}
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
                for i in range(1, len(parts)):
                    part = parts[i]
                    pattern = r'([^,\[]+)\[\s*(\d+)\s+[tT][oO]\s+(\d+)\s*\]'
                    match = re.search(pattern, part)
                    if match:
                        func_text = match.group(1).strip().upper()
                        start, end = int(match.group(2)), int(match.group(3))
                        cable_detail = ""
                        if i + 1 < len(parts) and "[" not in parts[i+1]:
                            cable_detail = parts[i+1]
                        
                        for t_num in range(start, end + 1):
                            current_rows.append({
                                "Row ID": rid, 
                                "Function": func_text, 
                                "Terminal Number": str(t_num).zfill(2), 
                                "Cable Detail": cable_detail
                            })
                            
    if current_rows: sheets_data.append({"meta": current_meta, "rows": current_rows})
    return sheets_data

# --- PDF DRAWING UTILS ---
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

# --- CORE PDF PROCESSING ---
def process_multi_sheet_pdf(sheets_list, sig_data, config):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    
    def get_special_info(text):
        if not text: return None, ""
        for _, data in config.items():
            if data["key"] in str(text).upper() and data["img"]:
                clean_name = str(text).upper().replace(data["key"], "").strip()
                return data["img"], clean_name
        return None, str(text)

    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        f_vals = [sig_data['prep'], sig_data['chk1'], sig_data['chk2'], sig_data['app'], meta['location'], meta['station'], meta['sip'], ""]
        
        start_x = draw_page_template(c, width, height, f_vals, meta['sheet'], meta['heading'])
        y_curr = height - 180
        
        for rid, group in df.groupby("Row ID", sort=False):
            if y_curr < (PAGE_MARGIN + 120):
                c.showPage()
                start_x = draw_page_template(c, width, height, f_vals, meta['sheet'], meta['heading'])
                y_curr = height - 180

            c.setFont("Helvetica-Bold", 12)
            c.drawString(PAGE_MARGIN + 30, y_curr + 15, rid)
            group = group.reset_index(drop=True)
            
            # 1. Terminals
            for idx, row in group.iterrows():
                tx = start_x + (idx * FIXED_GAP)
                # Only draw terminal circle if the function is NOT a special symbol
                s_img, _ = get_special_info(row['Function'])
                if not s_img:
                    draw_terminal_symbol(c, tx, y_curr)
                    c.setFont("Helvetica", 8)
                    c.drawCentredString(tx, y_curr - 15, str(row['Terminal Number']))
                
            # 2. Function Grouping (Top)
            func_blocks = group.groupby((group['Function'] != group['Function'].shift()).cumsum())
            for _, block in func_blocks:
                f_text = block['Function'].iloc[0]
                si, ei = block.index[0], block.index[-1]
                xm, xx = start_x + (si * FIXED_GAP), start_x + (ei * FIXED_GAP)
                
                s_img, d_label = get_special_info(f_text)
                if s_img:
                    c.drawInlineImage(s_img, (xm+xx)/2 - 25, y_curr - 5, width=50, height=50)
                    c.setFont("Helvetica-Bold", 10)
                    c.drawCentredString((xm+xx)/2, y_curr + 55, d_label)
                else:
                    c.setLineWidth(0.8)
                    c.line(xm-5, y_curr+50, xx+5, y_curr+50)
                    c.line(xm-5, y_curr+50, xm-5, y_curr+45)
                    c.line(xx+5, y_curr+50, xx+5, y_curr+45)
                    c.setFont("Helvetica-Bold", 10)
                    c.drawCentredString((xm+xx)/2, y_curr+60, f_text)
            
            # 3. Cable Detail Grouping (Bottom)
            cable_blocks = group.groupby((group['Cable Detail'] != group['Cable Detail'].shift()).cumsum())
            for _, block in cable_blocks:
                c_text = block['Cable Detail'].iloc[0]
                if not c_text or str(c_text).strip() == "": continue
                
                si, ei = block.index[0], block.index[-1]
                cxm, cxx = start_x + (si * FIXED_GAP), start_x + (ei * FIXED_GAP)
                
                s_img, d_label = get_special_info(c_text)
                if s_img:
                    # Draw symbol instead of bracket if keyword matched
                    c.drawInlineImage(s_img, (cxm+cxx)/2 - 25, y_curr - 85, width=50, height=50)
                    c.setFont("Helvetica-Bold", 9)
                    c.drawCentredString((cxm+cxx)/2, y_curr - 95, d_label)
                else:
                    c.setLineWidth(0.8)
                    c.line(cxm-5, y_curr - 35, cxx+5, y_curr - 35)
                    c.line(cxm-5, y_curr - 35, cxm-5, y_curr - 30)
                    c.line(cxx+5, y_curr - 35, cxx+5, y_curr - 30)
                    c.setFont("Helvetica-Oblique", 9)
                    c.drawCentredString((cxm+cxx)/2, y_curr - 50, str(c_text))
                
            y_curr -= ROW_HEIGHT_SPACING
        c.showPage()
        
    c.save()
    buffer.seek(0)
    return buffer

# --- MAIN UI ---
st.title("🚉 CTR Drawing Management System")

uploaded_file = st.file_uploader("Upload Drawing TXT", type=["txt"])
if uploaded_file:
    raw_text = uploaded_file.getvalue().decode("utf-8")
    st.session_state.sheets_data = parse_multi_sheet_txt(raw_text)

if 'sheets_data' in st.session_state:
    tabs = st.tabs(["📄 CTR Table Editor", "🖼️ Symbols Setup"])
    
    with tabs[0]:
        sel = st.selectbox("Select Sheet", range(len(st.session_state.sheets_data)), 
                           format_func=lambda x: f"Sheet {st.session_state.sheets_data[x]['meta']['sheet']}")
        df_p = pd.DataFrame(st.session_state.sheets_data[sel]['rows'])
        edited_df = st.data_editor(df_p, num_rows="dynamic", use_container_width=True)
        st.session_state.sheets_data[sel]['rows'] = edited_df.to_dict('records')
        
        col1, col2, col3, col4 = st.columns(4)
        sig_setup = {
            "prep": col1.text_input("Prepared By", "JE/SIG"),
            "chk1": col2.text_input("Checked By (1)", "SSE/SIG"),
            "chk2": col3.text_input("Checked By (2)", "ASTE"),
            "app": col4.text_input("Approved By", "DSTE")
        }
        
        if st.button("🚀 Generate PDF"):
            pdf = process_multi_sheet_pdf(st.session_state.sheets_data, sig_setup, symbol_config)
            st.download_button("📥 Download PDF", pdf, "CTR_Official_Drawing.pdf", "application/pdf")