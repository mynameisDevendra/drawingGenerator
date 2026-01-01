import streamlit as st
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
import re
import io
from datetime import datetime
from PIL import Image

# --- CONSTANTS ---
PAGE_MARGIN = 20
SAFETY_OFFSET = 42.5
FIXED_GAP = 33
PAGE_SIZE = landscape(A3)
ROW_HEIGHT_SPACING = 105 

def parse_txt_with_symbols(raw_text):
    sheets_data = []
    current_meta = {"sheet": 1, "station": "", "location": "", "sip": "", "heading": "TERMINAL CHART"}
    current_rows = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line: continue
        
        # Metadata parsing (Sheet, Station, etc.)
        if line.upper().startswith("SHEET:"):
            if current_rows:
                sheets_data.append({"meta": current_meta.copy(), "rows": current_rows})
                current_rows = []
            val = re.search(r'\d+', line)
            if val: current_meta["sheet"] = int(val.group())
        elif line.upper().startswith("SYMBOL:"):
            # FORMAT: SYMBOL: FUSE [A, 05]
            match = re.search(r'SYMBOL:\s*(\w+)\s*\[(\s*[A-Z]\s*),\s*(\d+)\s*\]', line, re.I)
            if match:
                current_rows.append({
                    "Row ID": match.group(2).strip().upper(),
                    "Function": match.group(1).strip().upper(),
                    "Terminal Number": match.group(3).zfill(2),
                    "is_symbol": True,
                    "Cable Detail": "" # No cable detail for symbols
                })
        else:
            # Standard terminal parsing (unchanged logic for regular terminals)
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 2:
                rid = parts[0].upper()
                middle_part = ",".join(parts[1:-1])
                cable_detail = parts[-1].upper()
                pattern = r'([^,\[]+)\[\s*(\d+)\s+to\s+(\d+)\s*\]'
                matches = re.findall(pattern, middle_part, re.I)
                for match in matches:
                    func_text = match[0].strip().upper()
                    start, end = int(match[1]), int(match[2])
                    for i in range(start, end + 1):
                        current_rows.append({
                            "Row ID": rid, "Function": func_text, 
                            "Terminal Number": str(i).zfill(2), "is_symbol": False,
                            "Cable Detail": cable_detail
                        })
    if current_rows: sheets_data.append({"meta": current_meta, "rows": current_rows})
    return sheets_data

def process_pdf_with_symbols(sheets_list, sig_data, symbol_images):
    buffer = io.BytesIO()
    width, height = PAGE_SIZE
    c = canvas.Canvas(buffer, pagesize=PAGE_SIZE)
    
    for sheet in sheets_list:
        meta = sheet['meta']
        df = pd.DataFrame(sheet['rows'])
        df['sort_key'] = df['Terminal Number'].apply(lambda s: int(s))
        df = df.sort_values(by=['Row ID', 'sort_key'])
        
        # Layout Init
        info_x = PAGE_MARGIN + ((width - (2 * PAGE_MARGIN)) / 15)
        y_curr = height - 160
        
        # Draw Template (Headers/Footers)
        # [Note: Assume draw_page_template is defined as per original script]
        
        for rid, group in df.groupby('Row ID', sort=False):
            chunk = group.to_dict('records')
            x_start = info_x + SAFETY_OFFSET + 20
            
            # Row Label (A, B, C...)
            c.setFont("Helvetica-Bold", 12); c.drawRightString(x_start - 30, y_curr + 15, str(rid))
            
            for idx, t in enumerate(chunk):
                tx = x_start + (idx * FIXED_GAP)
                
                if t['is_symbol']:
                    # 1. DRAW IMAGE
                    sym_name = t['Function']
                    if sym_name in symbol_images:
                        c.drawImage(symbol_images[sym_name], tx - 12, y_curr + 5, width=24, height=30, mask='auto')
                    
                    # 2. DRAW NAME ABOVE ONLY
                    c.setFont("Helvetica-Bold", 10)
                    c.drawCentredString(tx, y_curr + 45, sym_name)
                    
                    # 3. DO NOT DRAW TERMINALS OR NUMBERS (Skipped)
                else:
                    # DRAW STANDARD TERMINAL (Circle, Number, etc.)
                    c.setLineWidth(1); c.line(tx-3, y_curr, tx-3, y_curr+40); c.line(tx+3, y_curr, tx+3, y_curr+40)
                    c.circle(tx, y_curr+40, 3, fill=1); c.circle(tx, y_curr, 3, fill=1)
                    c.setFont("Helvetica-Bold", 8.5); c.drawRightString(tx-8, y_curr+17, str(t['Terminal Number']))

            y_curr -= ROW_HEIGHT_SPACING
        c.showPage()
    c.save(); buffer.seek(0); return buffer