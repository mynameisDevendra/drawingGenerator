import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
import re
import io

# --- LAYOUT CONSTANTS ---
# Margins based on standard engineering drawing layouts
MARGIN = 20

def draw_page_template(c, width, height, page_size):
    """
    Draws the permanent peripheral boundary, title block, and right margin info.
    Based on standard railway signaling drawing formats[cite: 1, 85, 100].
    """
    # 1. Outer Peripheral Boundary
    c.setLineWidth(1.5)
    c.rect(MARGIN, MARGIN, width - (2 * MARGIN), height - (2 * MARGIN))
    
    # 2. Bottom Title Block (Lowest Footer) 
    # Height of footer is approx 60 points
    footer_y = MARGIN + 60
    c.line(MARGIN, footer_y, width - MARGIN, footer_y)
    
    # Vertical dividers for Title Block sections
    # Prepared By | Checked | Approved | Location | Project Info | Sheet No
    dividers = [width * 0.2, width * 0.45, width * 0.65, width * 0.85]
    for x in dividers:
        c.line(x, MARGIN, x, footer_y)
    
    # Text in Title Block [cite: 85, 86, 100]
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN + 5, footer_y - 12, "PREPARED BY")
    c.drawString(width * 0.2 + 5, footer_y - 12, "CHECKED")
    c.drawString(width * 0.45 + 5, footer_y - 12, "APPROVED")
    
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width * 0.55, MARGIN + 35, "SOUTH GOOTY")
    c.drawCentredString(width * 0.55, MARGIN + 20, "CTR-1")
    
    c.setFont("Helvetica-Bold", 11)
    c.drawString(width * 0.65 + 10, MARGIN + 40, "BAITARANI ROAD")
    c.setFont("Helvetica", 8)
    c.drawString(width * 0.65 + 10, MARGIN + 25, "SIP.ECoR.KUR.BTV.03")
    
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width * 0.925, MARGIN + 25, "SH NO: 009")

    # 3. Right Margin Information (Project Reference) [cite: 2, 88]
    right_margin_x = width - 150
    # Boundary for right margin info box
    c.rect(MARGIN, height - 100, 160, 80) # Left side box in reference
    c.setFont("Helvetica-Bold", 7)
    c.drawString(MARGIN + 5, height - 35, "COMPLETION DRAWING")
    c.drawString(MARGIN + 5, height - 55, "PCSTE'S REFERENCE NO.7132/24")

# --- CORE DRAWING LOGIC ---

def get_dynamic_font_size(text, font_name, max_width, start_size, min_size=5):
    size = float(start_size)
    while size > min_size:
        width = stringWidth(text, font_name, size)
        if width <= max_width: return size
        size -= 0.5
    return min_size

def draw_terminal(c, x, y, term_id, term_font_size):
    c.setLineWidth(1)
    c.setStrokeColorRGB(0, 0, 0)
    c.line(x - 3, y, x - 3, y + 40) 
    c.line(x + 3, y, x + 3, y + 40) 
    c.setFillColorRGB(0, 0, 0)
    c.circle(x, y + 40, 3, stroke=1, fill=1) 
    c.circle(x, y, 3, stroke=1, fill=1)      
    c.setFont("Helvetica-Bold", term_font_size)
    c.drawRightString(x - 8, y + 17, str(term_id).zfill(2)) 

def draw_bracket_label(c, x1, x2, y, text, is_header, user_font_size):
    c.setLineWidth(0.8)
    c.line(x1, y, x2, y)
    mid = (x1 + x2) / 2
    max_w = (x2 - x1) + 10 
    font_name = "Helvetica-Bold"
    final_font_size = get_dynamic_font_size(text, font_name, max_w, user_font_size)
    c.setFont(font_name, final_font_size)
    
    if is_header:
        c.line(x1, y, x1, y - 5)
        c.line(x2, y, x2, y - 5)
        c.line(mid, y, mid, y + 5)
        c.drawCentredString(mid, y + 10, str(text))
    else:
        c.line(x1, y, x1, y + 5)
        c.line(x2, y, x2, y + 5)
        c.line(mid, y, mid, y - 5)
        c.drawCentredString(mid, y - (final_font_size + 8), str(text))

def extract_number(s):
    nums = re.findall(r'\d+', str(s))
    return int(nums[0]) if nums else 0

def process_terminal_drawing(df, header_fs, footer_fs, term_id_fs, row_id_fs, page_size_choice):
    buffer = io.BytesIO()
    
    if page_size_choice == "A3":
        selected_size = landscape(A3)
        x_start, row_height, gap = 180, 200, 40 
    else:
        selected_size = landscape(A4)
        x_start, row_height, gap = 160, 160, 35

    c = canvas.Canvas(buffer, pagesize=selected_size)
    width, height = selected_size
    
    # 1. DRAW PERMANENT PAGE TEMPLATE
    draw_page_template(c, width, height, page_size_choice)
    
    # Starting vertical position (accounting for template)
    y_current = height - 160
    
    # Cleaning and Sorting
    df = df.dropna(subset=['Terminal ID'])
    df = df[df['Terminal ID'] != ""]
    df['sort_key'] = df['Terminal ID'].apply(extract_number)
    df = df.sort_values(by=['Row ID', 'sort_key'])
    
    rows = {}
    for _, item in df.iterrows():
        rid = str(item['Row ID']) if pd.notna(item['Row ID']) and item['Row ID'] != "" else "Default"
        if rid not in rows: rows[rid] = []
        rows[rid].append(item.to_dict())

    for rid, terminals in rows.items():
        # Draw Row ID (A, B, C...) [cite: 1, 29, 49, 53, 101]
        c.setFont("Helvetica-Bold", row_id_fs)
        c.drawRightString(x_start - 35, y_current + 15, rid)

        for idx, term in enumerate(terminals):
            draw_terminal(c, x_start + (idx * gap), y_current, term['Terminal ID'], term_id_fs)

        for type_key, is_h, y_off in [('Header', True, 53.5), ('Footer', False, -13.5)]:
            i = 0
            while i < len(terminals):
                txt = str(terminals[i][type_key])
                s_x = x_start + (i * gap)
                j = i
                while j < len(terminals) and str(terminals[j][type_key]) == txt:
                    e_x = x_start + (j * gap)
                    j += 1
                draw_bracket_label(c, s_x - 5, e_x + 5, y_current + y_off, txt, is_h, header_fs if is_h else footer_fs)
                i = j
        y_current -= row_height

    c.save()
    buffer.seek(0)
    return buffer

# --- STREAMLIT INTERFACE ---

st.set_page_config(page_title="Railway Terminal Designer", layout="wide")
st.title("🚉 Professional Terminal Drawing Layout")

with st.sidebar:
    st.header("Page Configuration")
    page_size = st.selectbox("Select Page Size", ["A4", "A3"], index=0)
    
    st.header("Font Settings")
    h_fs = st.number_input("Header Font Size", value=9.0)
    f_fs = st.number_input("Footer Font Size", value=8.0)
    t_fs = st.number_input("Terminal ID Font Size", value=7.0)
    r_fs = st.number_input("Row ID Font Size", value=14.0)

st.subheader("Drawing Data")
df_input = pd.DataFrame([
    {"Row ID": "A", "Header": "DID HHG (3RD)", "Footer": "101-30C TO LOC-89", "Terminal ID": "01"},
    {"Row ID": "A", "Header": "DID HHG (3RD)", "Footer": "101-30C TO LOC-89", "Terminal ID": "02"}
])

edited_df = st.data_editor(df_input, num_rows="dynamic", use_container_width=True)

if st.button("🚀 Generate Professional Drawing"):
    if not edited_df.empty:
        pdf_buffer = process_terminal_drawing(edited_df, h_fs, f_fs, t_fs, r_fs, page_size)
        st.success(f"Professional Layout Generated for {page_size}!")
        st.download_button(
            label=f"⬇️ Download {page_size} PDF",
            data=pdf_buffer,
            file_name=f"Signaling_Drawing_{page_size}.pdf",
            mime="application/pdf"
        )