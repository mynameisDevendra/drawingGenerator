import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, A3, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
import re
import io

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
    
    # Selection Arrangement for A3 or A4
    if page_size_choice == "A3":
        selected_size = landscape(A3)
        # Increase spacing for A3
        x_start, row_height, gap = 120, 220, 40 
    else:
        selected_size = landscape(A4)
        x_start, row_height, gap = 120, 180, 35

    c = canvas.Canvas(buffer, pagesize=selected_size)
    width, height = selected_size
    y_current = height - 120
    
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
st.title("🚉 Railway Terminal Drawing Automation")

with st.sidebar:
    st.header("Page Configuration")
    # Selection Arrangement for Page Size
    page_size = st.selectbox("Select Page Size", ["A4", "A3"], index=0)
    
    st.header("Font Settings (Points)")
    h_fs = st.number_input("Header Font Size", value=10.0)
    f_fs = st.number_input("Footer Font Size", value=9.0)
    t_fs = st.number_input("Terminal ID Font Size", value=8.0)
    r_fs = st.number_input("Row ID Font Size", value=16.0)

st.subheader("Terminal Data")
st.info("Edit the table below. Use the '+' button to add terminals. Identical Headers/Footers will be grouped.")

# Example dataframe
df_input = pd.DataFrame([
    {"Row ID": "A", "Header": "DID HHG", "Footer": "S-30 CTR1", "Terminal ID": "01"},
    {"Row ID": "A", "Header": "DID HHG", "Footer": "S-30 CTR1", "Terminal ID": "02"}
])

edited_df = st.data_editor(df_input, num_rows="dynamic", use_container_width=True)

if st.button("🚀 Generate PDF Drawing"):
    if not edited_df.empty:
        pdf_buffer = process_terminal_drawing(edited_df, h_fs, f_fs, t_fs, r_fs, page_size)
        st.success(f"Drawing Generated for {page_size}!")
        st.download_button(
            label=f"⬇️ Download {page_size} PDF",
            data=pdf_buffer,
            file_name=f"Terminal_Layout_{page_size}.pdf",
            mime="application/pdf"
        )
    else:
        st.error("Please enter terminal data first.")