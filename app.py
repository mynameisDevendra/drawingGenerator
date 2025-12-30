import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
import re
import io

# --- LAYOUT CONSTANTS ---
PAGE_MARGIN = 20  # Distance from paper edge
SAFETY_OFFSET = 42.5  # 1.5 cm distance from left margin line

def draw_page_template(c, width, height):
    """
    Draws the full-length peripheral boundary and engineering title block.
    """
    c.setLineWidth(1.5)
    # Full length peripheral boundary from top to bottom
    c.rect(PAGE_MARGIN, PAGE_MARGIN, width - (2 * PAGE_MARGIN), height - (2 * PAGE_MARGIN))
    
    # Title Block Footer (60 pts high) [cite: 85, 100]
    footer_y = PAGE_MARGIN + 60
    c.line(PAGE_MARGIN, footer_y, width - PAGE_MARGIN, footer_y)
    
    # Section Dividers [cite: 54, 89, 81]
    dividers = [width * 0.2, width * 0.45, width * 0.65, width * 0.85]
    for x in dividers:
        c.line(x, PAGE_MARGIN, x, footer_y)
    
    # Labels
    c.setFont("Helvetica-Bold", 8)
    c.drawString(PAGE_MARGIN + 5, footer_y - 12, "PREPARED BY")
    c.drawString(width * 0.2 + 5, footer_y - 12, "CHECKED")
    c.drawString(width * 0.45 + 5, footer_y - 12, "APPROVED")
    
    # Center Info [cite: 85]
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width * 0.55, PAGE_MARGIN + 35, "SOUTH GOOTY")
    c.drawCentredString(width * 0.55, PAGE_MARGIN + 20, "CTR-1")
    
    # Station Info [cite: 86, 87]
    c.setFont("Helvetica-Bold", 11)
    c.drawString(width * 0.65 + 10, PAGE_MARGIN + 40, "BAITARANI ROAD")
    c.setFont("Helvetica", 8)
    c.drawString(width * 0.65 + 10, PAGE_MARGIN + 25, "SIP.ECoR.KUR.BTV.03")
    c.drawCentredString(width * 0.925, PAGE_MARGIN + 25, "SH NO: 009")

    # Left Information Box [cite: 1, 52]
    c.setLineWidth(1)
    c.rect(PAGE_MARGIN, height - 100, 160, 80)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(PAGE_MARGIN + 5, height - 35, "COMPLETION DRAWING")
    c.drawString(PAGE_MARGIN + 5, height - 55, "PCSTE'S REFERENCE NO.7132/24")

# --- CORE DRAWING LOGIC ---

def get_dynamic_font_size(text, font_name, max_width, start_size):
    size = float(start_size)
    while size > 5:
        width = stringWidth(text, font_name, size)
        if width <= max_width: return size
        size -= 0.5
    return 5

def draw_terminal(c, x, y, term_id, term_font_size):
    """Draws vertical terminal with parallel lines and solid circles [cite: 2-7, 9]."""
    c.setLineWidth(1)
    c.line(x - 3, y, x - 3, y + 40) 
    c.line(x + 3, y, x + 3, y + 40) 
    c.setFillColorRGB(0, 0, 0)
    c.circle(x, y + 40, 3, stroke=1, fill=1) 
    c.circle(x, y, 3, stroke=1, fill=1)      
    c.setFont("Helvetica-Bold", term_font_size)
    c.drawRightString(x - 8, y + 17, str(term_id).zfill(2)) 

def draw_bracket_label(c, x1, x2, y, text, is_header, user_font_size):
    """Draws grouping brackets with auto-scaled text [cite: 2-8]."""
    c.setLineWidth(0.8)
    c.line(x1, y, x2, y)
    mid = (x1 + x2) / 2
    max_w = (x2 - x1) + 10 
    font_size = get_dynamic_font_size(text, "Helvetica-Bold", max_w, user_font_size)
    c.setFont("Helvetica-Bold", font_size)
    if is_header:
        c.line(x1, y, x1, y - 5); c.line(x2, y, x2, y - 5); c.line(mid, y, mid, y + 5)
        c.drawCentredString(mid, y + 10, str(text))
    else:
        c.line(x1, y, x1, y + 5); c.line(x2, y, x2, y + 5); c.line(mid, y, mid, y - 5)
        c.drawCentredString(mid, y - (font_size + 8), str(text))

def process_terminal_drawing(df, header_fs, footer_fs, term_id_fs, row_id_fs, page_size_choice):
    buffer = io.BytesIO()
    selected_size = landscape(A3) if page_size_choice == "A3" else landscape(A4)
    c = canvas.Canvas(buffer, pagesize=selected_size)
    width, height = selected_size
    
    draw_page_template(c, width, height)
    
    # Logic for 1.5cm offset from the leftmost margin line
    x_start = PAGE_MARGIN + SAFETY_OFFSET + 40 # Total horizontal start
    y_current = height - 150
    gap = 40 if page_size_choice == "A3" else 35
    row_height = 180
    
    # Sorting and Drawing
    df = df.dropna(subset=['Terminal ID'])
    df['sort_key'] = df['Terminal ID'].apply(lambda s: int(re.findall(r'\d+', str(s))[0]) if re.findall(r'\d+', str(s)) else 0)
    df = df.sort_values(by=['Row ID', 'sort_key'])
    
    rows = df.groupby('Row ID')
    for rid, group in rows:
        terminals = group.to_dict('records')
        # Row Identifier A, B, C... [cite: 24, 29, 49, 53, 101]
        c.setFont("Helvetica-Bold", row_id_fs)
        c.drawRightString(x_start - 35, y_current + 15, rid)

        for idx, term in enumerate(terminals):
            draw_terminal(c, x_start + (idx * gap), y_current, term['Terminal ID'], term_id_fs)

        # Header/Footer Grouping logic [cite: 4-12, 14-23]
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

    c.save(); buffer.seek(0)
    return buffer

# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Railway Terminal Designer", layout="wide")
st.title("🚉 Professional Terminal Layout (1.5cm Margin Offset)")

with st.sidebar:
    page_size = st.selectbox("Page Size", ["A4", "A3"])
    h_fs = st.number_input("Header Font Size", value=9.0)
    f_fs = st.number_input("Footer Font Size", value=8.0)
    t_fs = st.number_input("Terminal Font Size", value=7.0)
    r_fs = st.number_input("Row ID Font Size", value=14.0)

df_input = pd.DataFrame([
    {"Row ID": "A", "Header": "DID HHG (3RD)", "Footer": "101-30C TO LOC-89", "Terminal ID": "01"},
    {"Row ID": "A", "Header": "DID HHG (3RD)", "Footer": "101-30C TO LOC-89", "Terminal ID": "02"}
])
edited_df = st.data_editor(df_input, num_rows="dynamic", use_container_width=True)

if st.button("🚀 Generate PDF"):
    pdf_buffer = process_terminal_drawing(edited_df, h_fs, f_fs, t_fs, r_fs, page_size)
    st.download_button("⬇️ Download PDF", data=pdf_buffer, file_name="Signaling_Drawing.pdf", mime="application/pdf")