import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from PIL import Image

# --- CONFIG ---
st.set_page_config(page_title="CTR Symbol Generator", layout="wide")

PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 120 # Increased spacing to accommodate cable labels

# --- FUNCTIONS ---

def parse_txt_with_symbols(raw_text):
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
        elif upper_line.startswith("SYMBOL:"):
            match = re.search(r'SYMBOL:\s*(\w+)\s*\[(\w+),\s*(\d+)\]', line, re.I)
            if match:
                current_rows.append({
                    "Row ID": match.group(2).upper(),
                    "Function": match.group(1).upper(),
                    "Terminal Number": match.group(3).zfill(2),
                    "is_symbol": True,
                    "Cable Group": None
                })
        else:
            # Format Expected: A, 24C_TO_P6[01 to 12], 12C_SPARE[13 to 24]
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rid = parts[0].upper()
                for cable_part in parts[1:]:
                    # Pattern to find: CABLE_NAME [ START to END ]
                    pattern = r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]'
                    match = re.search(pattern, cable_part, re.I)
                    if match:
                        cable_name = match.group(1).strip().upper()
                        start, end = int(match.group(2)), int(match.group(3))
                        for i in range(start, end + 1):
                            current_rows.append({
                                "Row ID": rid, 
                                "Function": cable_name, 
                                "Terminal Number": str(i).zfill(2), 
                                "is_symbol": False,
                                "Cable Group": cable_name # This links the terminals to a cable
                            })

    if current_rows: sheets_data.append({"meta": current_meta, "rows": current_rows})
    return sheets_data

def draw_page_template(c, width, height, meta, sheet_no):
    c.setLineWidth(1.5)
    c.rect(PAGE_MARGIN, PAGE_MARGIN, width - (2 * PAGE_MARGIN), height - (2 * PAGE_MARGIN))
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 60, meta['heading'].upper())
    c.setFont("Helvetica-Bold", 10)
    c.drawString(PAGE_MARGIN + 20, PAGE_MARGIN + 20, f"STATION: {meta['station']} | LOCATION: {meta['location']} | SHEET: {sheet_no}")

def generate_pdf(sheets_list, symbol_images):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        df['sort_key'] = pd.to_numeric(df['Terminal Number'])
        df = df.sort_values(['Row ID', 'sort_key'])
        
        y_curr = height - 160
        draw_page_template(c, width, height, meta, meta['sheet'])
        info_x = PAGE_MARGIN + ((width - (2 * PAGE_MARGIN)) / 15)
        
        for rid, group in df.groupby('Row ID', sort=False):
            x_start = info_x + SAFETY_OFFSET + 20
            c.setFont("Helvetica-Bold", 12)
            c.drawRightString(x_start - 30, y_curr + 15, str(rid))
            
            chunk = group.to_dict('records')
            
            # --- CABLE GROUPING LOGIC ---
            # Identify continuous blocks of the same 'Cable Group'
            groups = []
            if len(chunk) > 0:
                current_g = {"name": chunk[0]['Cable Group'], "start_idx": 0, "count": 1}
                for i in range(1, len(chunk)):
                    if chunk[i]['Cable Group'] == current_g['name'] and chunk[i]['Cable Group'] is not None:
                        current_g['count'] += 1
                    else:
                        groups.append(current_g)
                        current_g = {"name": chunk[i]['Cable Group'], "start_idx": i, "count": 1}
                groups.append(current_g)

            # Draw Cable Brackets/Lines
            for g in groups:
                if g['name']:
                    lx_start = x_start + (g['start_idx'] * FIXED_GAP)
                    lx_end = lx_start + ((g['count'] - 1) * FIXED_GAP)
                    
                    # Draw a horizontal line above the terminals
                    c.setLineWidth(0.5)
                    c.line(lx_start - 5, y_curr + 55, lx_end + 5, y_curr + 55)
                    # Draw small vertical ticks at ends
                    c.line(lx_start - 5, y_curr + 55, lx_start - 5, y_curr + 45)
                    c.line(lx_end + 5, y_curr + 55, lx_end + 5, y_curr + 45)
                    
                    # Draw Cable Name
                    c.setFont("Helvetica-Oblique", 7)
                    c.drawCentredString((lx_start + lx_end)/2, y_curr + 58, g['name'])

            # Draw Individual Terminals
            for idx, t in enumerate(chunk):
                tx = x_start + (idx * FIXED_GAP)
                
                if t.get('is_symbol'):
                    name = t['Function']
                    if name in symbol_images:
                        c.drawImage(symbol_images[name], tx-12, y_curr+5, width=24, height=28, mask='auto')
                    c.setFont("Helvetica-Bold", 9)
                    c.drawCentredString(tx, y_curr + 40, name)
                else:
                    c.setLineWidth(1)
                    c.line(tx-3, y_curr, tx-3, y_curr+30)
                    c.line(tx+3, y_curr, tx+3, y_curr+30)
                    c.circle(tx, y_curr+30, 2, fill=1)
                    c.circle(tx, y_curr, 2, fill=1)
                    c.setFont("Helvetica", 8)
                    c.drawCentredString(tx, y_curr + 12, t['Terminal Number'])
            
            y_curr -= ROW_HEIGHT_SPACING
        c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- UI (Remains largely the same) ---
st.title("🚉 CTR Drawing Generator with Cable Grouping")
# ... (Keep the sidebar and file uploader code from your original snippet)