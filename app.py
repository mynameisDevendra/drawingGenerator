import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
import re
import io

# --- LAYOUT CONSTANTS ---
PAGE_MARGIN = 20  
SAFETY_OFFSET = 42.5  # 1.5 cm distance

def draw_page_template(c, width, height, footer_data, left_col_data):
    """
    Draws the full-length left column and 6-box footer with user-defined text.
    """
    c.setLineWidth(1.5)
    # 1. Outer Peripheral Boundary
    c.rect(PAGE_MARGIN, PAGE_MARGIN, width - (2 * PAGE_MARGIN), height - (2 * PAGE_MARGIN))
    
    # 2. Bottom Title Block Line
    footer_y = PAGE_MARGIN + 60
    c.line(PAGE_MARGIN, footer_y, width - PAGE_MARGIN, footer_y)
    
    # 3. Left Column (Width matched to 1st footer box)
    # Total width of footer = width - 2*PAGE_MARGIN. Divided by 6 boxes.
    box_width = (width - (2 * PAGE_MARGIN)) / 6
    info_column_x = PAGE_MARGIN + box_width 
    c.line(info_column_x, PAGE_MARGIN, info_column_x, height - PAGE_MARGIN)
    
    # 4. Left Information Box (Top Left Partition)
    info_box_height = 80
    c.line(PAGE_MARGIN, height - PAGE_MARGIN - info_box_height, info_column_x, height - PAGE_MARGIN - info_box_height)
    
    # 5. Draw 6 Footer Boxes
    for i in range(1, 6):
        x_pos = PAGE_MARGIN + (i * box_width)
        c.line(x_pos, PAGE_MARGIN, x_pos, footer_y)
    
    # --- FILLING EDITABLE TEXT ---
    
    # Left Column Text [cite: 1, 88]
    c.setFont("Helvetica-Bold", 7)
    c.drawString(PAGE_MARGIN + 3, height - PAGE_MARGIN - 15, left_col_data['line1'].upper())
    c.setFont("Helvetica", 6)
    c.drawString(PAGE_MARGIN + 3, height - PAGE_MARGIN - 30, left_col_data['line2'].upper())
    c.drawString(PAGE_MARGIN + 3, height - PAGE_MARGIN - 40, left_col_data['line3'].upper())

    # Footer Boxes Text 
    c.setFont("Helvetica-Bold", 7)
    labels = ["box1", "box2", "box3", "box4", "box5", "box6"]
    for i, label in enumerate(labels):
        x_center = PAGE_MARGIN + (i * box_width) + (box_width / 2)
        text = footer_data[label]
        # Split text by newline if user entered multiple lines
        lines = text.split('\n')
        for j, line in enumerate(lines):
            c.drawCentredString(x_center, footer_y - 15 - (j * 10), line.upper())

    return info_column_x

# --- CORE LOGIC (Terminal Drawing & Sequencing) ---

def get_dynamic_font_size(text, font_name, max_width, start_size):
    size = float(start_size)
    while size > 4:
        width = stringWidth(text, font_name, size)
        if width <= max_width: return size
        size -= 0.5
    return 4

def draw_terminal(c, x, y, term_id, term_font_size):
    c.setLineWidth(1)
    c.line(x - 3, y, x - 3, y + 40) # [cite: 2-7]
    c.line(x + 3, y, x + 3, y + 40) # [cite: 2-7]
    c.setFillColorRGB(0, 0, 0)
    c.circle(x, y + 40, 3, stroke=1, fill=1) # [cite: 2-7, 9]
    c.circle(x, y, 3, stroke=1, fill=1)      # [cite: 2-7, 9]
    c.setFont("Helvetica-Bold", term_font_size)
    c.drawRightString(x - 8, y + 17, str(term_id).zfill(2)) 

def draw_bracket_label(c, x1, x2, y, text, is_header, user_font_size):
    c.setLineWidth(0.8)
    c.line(x1, y, x2, y)
    mid = (x1 + x2) / 2
    max_w = (x2 - x1) + 10 
    font_size = get_dynamic_font_size(text, "Helvetica-Bold", max_w, user_font_size)
    c.setFont("Helvetica-Bold", font_size)
    if is_header:
        c.line(x1, y, x1, y - 5); c.line(x2, y, x2, y - 5); c.line(mid, y, mid, y + 5)
        c.drawCentredString(mid, y + 8, str(text)) # [cite: 2-8]
    else:
        c.line(x1, y, x1, y + 5); c.line(x2, y, x2, y + 5); c.line(mid, y, mid, y - 5)
        c.drawCentredString(mid, y - (font_size + 6), str(text))

def process_terminal_drawing(df, fs_config, footer_data, left_col_data, page_size):
    buffer = io.BytesIO()
    selected_size = landscape(A3) if page_size == "A3" else landscape(A4)
    c = canvas.Canvas(buffer, pagesize=selected_size)
    width, height = selected_size
    
    info_column_x = draw_page_template(c, width, height, footer_data, left_col_data)
    
    x_start = info_column_x + SAFETY_OFFSET + 15
    y_current = height - 150
    gap = 38 if page_size == "A3" else 32
    row_height = 160
    
    df = df.dropna(subset=['Terminal ID'])
    df['sort_key'] = df['Terminal ID'].apply(lambda s: int(re.findall(r'\d+', str(s))[0]) if re.findall(r'\d+', str(s)) else 0)
    df = df.sort_values(by=['Row ID', 'sort_key'])
    
    rows = df.groupby('Row ID')
    for rid, group in rows:
        terminals = group.to_dict('records')
        c.setFont("Helvetica-Bold", fs_config['row'])
        c.drawRightString(x_start - 30, y_current + 15, str(rid))

        for idx, term in enumerate(terminals):
            draw_terminal(c, x_start + (idx * gap), y_current, term['Terminal ID'], fs_config['term'])

        for type_key, is_h, y_off in [('Header', True, 53.5), ('Footer', False, -13.5)]:
            i = 0
            while i < len(terminals):
                txt = str(terminals[i][type_key])
                s_x = x_start + (i * gap)
                j = i
                while j < len(terminals) and str(terminals[j][type_key]) == txt:
                    e_x = x_start + (j * gap)
                    j += 1
                draw_bracket_label(c, s_x - 5, e_x + 5, y_current + y_off, txt, is_h, fs_config['head' if is_h else 'foot'])
                i = j
        y_current -= row_height

    c.save(); buffer.seek(0)
    return buffer

# --- STREAMLIT INTERFACE ---
st.set_page_config(page_title="Railway Terminal Designer", layout="wide")
st.title("🚉 Custom Engineering Layout Generator")

with st.sidebar:
    st.header("1. Page & Font Settings")
    page_size = st.selectbox("Page Size", ["A4", "A3"])
    fs_config = {
        'head': st.number_input("Header Font", value=8.0),
        'foot': st.number_input("Footer Font", value=7.0),
        'term': st.number_input("Terminal Font", value=7.0),
        'row': st.number_input("Row ID Font", value=12.0)
    }

    st.header("2. Left Column Info")
    left_col = {
        'line1': st.text_input("Line 1 (Bold)", value="COMPLETION DRAWING"),
        'line2': st.text_input("Line 2", value="PCSTE'S REF NO."),
        'line3': st.text_input("Line 3", value="7132/24")
    }

    st.header("3. Bottom Footer (6 Boxes)")
    footer = {
        'box1': st.text_area("Box 1 (Prepared By)", value="PREPARED BY\nNOVALINE INFRA", height=70),
        'box2': st.text_area("Box 2 (Checked)", value="CHECKED BY\nSSE/SIG", height=70),
        'box3': st.text_area("Box 3 (Approved)", value="APPROVED BY\nDY.CSTE", height=70),
        'box4': st.text_area("Box 4 (Location)", value="SOUTH GOOTY\nCTR-1", height=70),
        'box5': st.text_area("Box 5 (Station)", value="BAITARANI ROAD\nSIP.ECOR.BTV.03", height=70),
        'box6': st.text_area("Box 6 (Sheet Info)", value="SH NO: 009", height=70)
    }

st.subheader("Terminal Data Input")
df_input = pd.DataFrame([
    {"Row ID": "A", "Header": "DID HHG (3RD)", "Footer": "101-30C TO LOC-89", "Terminal ID": "01"},
    {"Row ID": "A", "Header": "DID HHG (3RD)", "Footer": "101-30C TO LOC-89", "Terminal ID": "02"}
])
edited_df = st.data_editor(df_input, num_rows="dynamic", use_container_width=True)

if st.button("🚀 Generate PDF Drawing"):
    pdf_buffer = process_terminal_drawing(edited_df, fs_config, footer, left_col, page_size)
    st.download_button("⬇️ Download PDF", data=pdf_buffer, file_name="Custom_Signaling_Plan.pdf", mime="application/pdf")