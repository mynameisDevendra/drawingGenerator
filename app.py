# 1. Install necessary libraries
!pip install reportlab gradio

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
import gradio as gr
import pandas as pd
import re

# --- CORE DRAWING LOGIC ---

def get_dynamic_font_size(text, font_name, max_width, start_size, min_size=5):
    """Iteratively reduces font size from the user-selected starting size to fit the bracket."""
    size = float(start_size)
    while size > min_size:
        width = stringWidth(text, font_name, size)
        if width <= max_width: return size
        size -= 0.5
    return min_size

def draw_terminal(c, x, y, term_id, term_font_size):
    """Draws vertical terminal with parallel lines and solid circles ."""
    c.setLineWidth(1)
    c.setStrokeColorRGB(0, 0, 0)
    # Parallel lines representing the terminal link [cite: 2-7]
    c.line(x - 3, y, x - 3, y + 40) 
    c.line(x + 3, y, x + 3, y + 40) 
    c.setFillColorRGB(0, 0, 0)
    # Solid black connection circles 
    c.circle(x, y + 40, 3, stroke=1, fill=1) 
    c.circle(x, y, 3, stroke=1, fill=1)      
    
    # Terminal ID (Left Side) with User-defined Font Size
    c.setFont("Helvetica-Bold", term_font_size)
    c.drawRightString(x - 8, y + 17, str(term_id).zfill(2)) 

def draw_bracket_label(c, x1, x2, y, text, is_header, user_font_size):
    """Draws horizontal grouping brackets with user-defined/auto-scaled text [cite: 2-8]."""
    c.setLineWidth(0.8)
    c.line(x1, y, x2, y)
    mid = (x1 + x2) / 2
    max_w = (x2 - x1) + 10 # Buffer for text width
    
    font_name = "Helvetica-Bold"
    # Dynamic scaling starting from the user's chosen size
    final_font_size = get_dynamic_font_size(text, font_name, max_w, user_font_size)
    c.setFont(font_name, final_font_size)
    
    if is_header:
        # Upper bracket: Ends point down, center points up [cite: 2-8]
        c.line(x1, y, x1, y - 5)
        c.line(x2, y, x2, y - 5)
        c.line(mid, y, mid, y + 5)
        c.drawCentredString(mid, y + 10, str(text))
    else:
        # Lower bracket: Ends point up, center points down
        c.line(x1, y, x1, y + 5)
        c.line(x2, y, x2, y + 5)
        c.line(mid, y, mid, y - 5)
        c.drawCentredString(mid, y - (final_font_size + 8), str(text))

def extract_number(s):
    """Helper to extract numerical values for sorting."""
    nums = re.findall(r'\d+', str(s))
    return int(nums[0]) if nums else 0

def process_terminal_drawing(df, header_fs, footer_fs, term_id_fs, row_id_fs):
    """Processes table and settings to generate PDF."""
    if df.empty: return None
    
    df = df.dropna(subset=['Terminal ID'])
    df = df[df['Terminal ID'] != ""]
    
    # Automatic Sequencing Logic
    df['sort_key'] = df['Terminal ID'].apply(extract_number)
    df = df.sort_values(by=['Row ID', 'sort_key'])
    
    output_path = "Railway_Terminal_Custom_Fonts.pdf"
    c = canvas.Canvas(output_path, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    x_start, y_current, row_height, gap = 120, height - 120, 180, 35 # Slightly wider gap
    
    rows = {}
    for _, item in df.iterrows():
        rid = str(item['Row ID']) if pd.notna(item['Row ID']) and item['Row ID'] != "" else "Default"
        if rid not in rows: rows[rid] = []
        rows[rid].append(item.to_dict())

    for rid, terminals in rows.items():
        # Row ID on left with custom font size
        c.setFont("Helvetica-Bold", row_id_fs)
        c.drawRightString(x_start - 35, y_current + 15, rid)

        for idx, term in enumerate(terminals):
            draw_terminal(c, x_start + (idx * gap), y_current, term['Terminal ID'], term_id_fs)

        # Header grouping 
        i = 0
        while i < len(terminals):
            h_text = str(terminals[i]['Header'])
            s_x = x_start + (i * gap)
            j = i
            while j < len(terminals) and str(terminals[j]['Header']) == h_text:
                e_x = x_start + (j * gap)
                j += 1
            draw_bracket_label(c, s_x - 5, e_x + 5, y_current + 53.5, h_text, True, header_fs)
            i = j

        # Footer grouping
        i = 0
        while i < len(terminals):
            f_text = str(terminals[i]['Footer'])
            s_x = x_start + (i * gap)
            j = i
            while j < len(terminals) and str(terminals[j]['Footer']) == f_text:
                f_end_x = x_start + (j * gap)
                j += 1
            draw_bracket_label(c, s_x - 5, f_end_x + 5, y_current - 13.5, f_text, False, footer_fs)
            i = j
            
        y_current -= row_height

    c.save()
    return output_path

# --- GRADIO INTERFACE ---

def launch_interface():
    default_data = [
        ["A", "DID HHG (3RD)", "S-30 CTR1", "02"],
        ["A", "DID HHG (3RD)", "S-30 CTR1", "01"],
        ["B", "B-24V", "Goomty-1", "01"]
    ]
    
    with gr.Blocks(title="Railway Terminal Designer") as demo:
        gr.Markdown("# 🚉 Railway Terminal Designer with Custom Fonts")
        
        with gr.Row():
            with gr.Column(scale=3):
                gr.Markdown("### 1. Terminal Data (Right-click to add rows)")
                input_table = gr.Dataframe(
                    headers=["Row ID", "Header", "Footer", "Terminal ID"],
                    datatype=["str", "str", "str", "str"],
                    row_count=5,
                    interactive=True,
                    value=default_data,
                    type="pandas"
                )
            
            with gr.Column(scale=1):
                gr.Markdown("### 2. Font Size Settings (Points)")
                h_fs = gr.Number(label="Header Font Size", value=10, precision=1)
                f_fs = gr.Number(label="Footer Font Size", value=9, precision=1)
                t_fs = gr.Number(label="Terminal ID Font Size", value=8, precision=1)
                r_fs = gr.Number(label="Row ID Font Size", value=16, precision=1)
        
        btn = gr.Button("🚀 Generate Sorted PDF", variant="primary")
        output_file = gr.File(label="Download PDF")
        
        btn.click(
            fn=process_terminal_drawing, 
            inputs=[input_table, h_fs, f_fs, t_fs, r_fs], 
            outputs=output_file
        )
        
    demo.launch(debug=True)

launch_interface()