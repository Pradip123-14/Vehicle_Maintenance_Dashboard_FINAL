import re, io, os
from pathlib import Path
import pandas as pd
import streamlit as st
import fitz
from PIL import Image

APP_TITLE = "Vehicle Maintenance Invoice Extractor"
ITEM_COLS = ["Invoice No.", "Invoice Date", "Vendor Name", "Vehicle Number", "Item Code", "Item Name / Description", "Category", "Qty", "Unit", "Rate per Qty", "Taxable Amount", "GST Rate %", "CGST", "SGST", "IGST", "Total GST", "Total Amount", "Review Status", "Source Filename"]
SUMMARY_COLS = ["Invoice No.", "Invoice Date", "Vendor Name", "Vehicle Number", "Parts Taxable", "Labour Taxable", "Total Taxable", "CGST", "SGST", "IGST", "Extracted Item Total", "Invoice Net Bill (as printed)", "Reconciliation / Review"]
REPORT_COLS = ["Source Filename", "Detected Invoice No.", "Detected Vendor", "Detected Vehicle", "Items Extracted", "Printed Invoice Total", "Status / Review"]

def clean(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()
def num(s):
    if s is None: return None
    s=str(s).replace(',', '').replace('₹','').strip()
    if not s or s in {'-','—'}: return None
    try: return float(s)
    except: return None
def money_all(text):
    return [float(x.replace(',','')) for x in re.findall(r'(?<![A-Za-z])\d[\d,]*\.\d{2}', text)]
def first(pattern, text, flags=re.I|re.M):
    m=re.search(pattern,text,flags)
    return clean(m.group(1)) if m else ''
def extract_text(upload):
    name=upload.name
    raw=upload.getvalue()
    if name.lower().endswith('.pdf'):
        doc=fitz.open(stream=raw,filetype='pdf')
        return '\n'.join(p.get_text('text', sort=True) for p in doc)
    im=Image.open(io.BytesIO(raw)).convert('RGB')
    # OCR is optional. PyMuPDF has no OCR engine; use pytesseract if installed and Tesseract is installed on Windows.
    try:
        import pytesseract
        return pytesseract.image_to_string(im)
    except Exception:
        return ''
def metadata(text, filename):
    invoice = first(r'(?:Invoice\s*(?:No\.?|Number)|Bill\s*No\.?|Tax\s*Invoice\s*No\.?|Bill\.No\.)\s*[:#]?\s*([A-Z0-9][A-Z0-9./_-]{1,})', text)
    # avoid dates, GSTIN, job card, IRN and generic labels
    if invoice and re.fullmatch(r'(?i)(date|invoice|bill|no|number)', invoice): invoice=''
    date = first(r'(?:Bill\s*Date|Invoice\s*Date|Date)\s*:?\s*(\d{1,2}[/-][A-Za-z0-9]{1,3}[/-]\d{2,4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', text)
    if not date:
        date=first(r'(?:Bill\s*Date|Invoice\s*Date|Date)\s*:?\s*(\d{1,2}-[A-Z]{3}-\d{2,4})',text)
    vendor=''
    for pat in [r'^\s*(Star Motor Works)\s*$',r'For\s+([A-Z][A-Z0-9 &().-]{4,}(?:PVT\.?|PRIVATE|LTD\.?|LIMITED|AUTOMOTIVE|MOTORS)[A-Z0-9 &().-]*)',r'^\s*([A-Z][A-Za-z &().-]*(?:Automotives|Automotive|Motors|Vehicles|Service))\s*$']:
        vendor=first(pat,text)
        if vendor: break
    if not vendor:
        if 'FORT POINT AUTOMOTIVE' in text.upper(): vendor='FORT POINT AUTOMOTIVE (CARS) PVT.'
        elif 'STAR MOTOR WORKS' in text.upper(): vendor='Star Motor Works'
        else: vendor=''
    vehicle=first(r'(?:Registration\s*No\.?|Reg\.?\s*No\.?)\s*:?\s*([A-Z]{2}\s*\d{1,2}\s*[A-Z]{1,3}\s*\d{3,4})',text)
    vehicle=re.sub(r'\s+','',vehicle).upper()
    # Fallback from vehicle-like registration printed elsewhere, not from filename.
    if not vehicle:
        vehicle=first(r'\b([A-Z]{2}\d{1,2}[A-Z]{1,3}\d{3,4})\b',text)
    total=None
    total_patterns=[r'Net Bill Amount\s*(?:\(Rounded\))?\s*:?\s*([\d,]+\.\d{2})',r'Total Amount With GST\s*\(Rs\.\)\s*:?\s*([\d,]+(?:\.\d{1,2})?)',r'Grand Total\s*:?\s*([\d,]+\.\d{2})',r'Total Invoice Value\s*:?\s*([\d,]+\.\d{2})']
    for p in total_patterns:
        total=num(first(p,text))
        if total is not None: break
    if total is None:
        # use amount in words only as no numeric total is reliable: leave blank
        total=None
    return {'invoice':invoice,'date':date,'vendor':vendor,'vehicle':vehicle,'printed_total':total}

def parse_star(text, meta, filename):
    """Parse Star Motor Works' column-aligned tax invoice text.

    PyMuPDF's text extraction places the product description before HSN/SAC and
    the numeric columns after it. Wrapped descriptions are appended to the prior
    item. Category is determined by the Services section and SAC 998729.
    """
    rows = []
    section = 'Parts'
    last_row = None
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    num_re = re.compile(r'(?<![A-Za-z])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,3})?')
    for line in lines:
        if re.fullmatch(r'Services', line, re.I):
            section = 'Labour'
            last_row = None
            continue
        if re.search(r'^(?:Grand\s+Total|Total\s*:|Taxable Products Amount|CGST on Products|SGST on Products|IGST on Products|Total Amount With GST|Total Tax|For Star Motor Works)', line, re.I):
            last_row = None
            continue
        # Start of a numbered item. Keep the text before the HSN as the description.
        m = re.match(r'^\s*(\d{1,2})[.)]?\s+(.+)$', line)
        if m:
            serial = m.group(1)
            rest = m.group(2)
            # Locate the HSN/SAC immediately before the numeric columns.
            hsn_match = re.search(r'\b(998729|\d{4,8})\b(?=\s)', rest)
            if hsn_match:
                hsn = hsn_match.group(1)
                desc = clean(rest[:hsn_match.start()])
                tail = rest[hsn_match.end():]
                values = [num(x) for x in num_re.findall(tail)]
                # Expected: qty, rate, amount, discount, taxable, CGST rate/amount,
                # SGST rate/amount, IGST rate/amount, line total.
                if len(values) >= 12:
                    qty, rate, amount, discount, taxable = values[:5]
                    cgst_rate, cgst = values[5:7]
                    sgst_rate, sgst = values[7:9]
                    igst_rate, igst = values[9:11]
                    total = values[11]
                    cat = 'Labour' if hsn == '998729' or section == 'Labour' else 'Parts'
                    gst = (cgst_rate or 0) + (sgst_rate or 0) + (igst_rate or 0)
                    row = make_row(meta, filename, hsn, desc, cat, qty, 'Nos', rate,
                                   taxable, gst, cgst or 0, sgst or 0, igst or 0,
                                   total, 'Extracted from Star Motor table; verify against PDF')
                    rows.append(row)
                    last_row = row
                    continue
            # If the numbered line is not an item row, do not treat it as a continuation.
            last_row = None
            continue
        # Wrapped descriptions such as REFURBISHED, LAMP, REPAIR, etc.
        if last_row and not re.search(r'^(?:Total|Grand Total|Taxable|CGST|SGST|IGST|HSN/SAC)', line, re.I):
            if not re.search(r'\d[\d,.]*\s*$', line) and not re.fullmatch(r'[\d,. ]+', line):
                last_row['Item Name / Description'] = clean(last_row['Item Name / Description'] + ' ' + line)
    return rows

def parse_maruti(text, meta, filename):
    rows=[]; section='Parts'; in_table=False
    lines=[clean(x) for x in text.splitlines() if clean(x)]
    # Maruti job-card line pattern: serial, part code, description, batch, HSN, optional GST rate, qty, rate, taxable, tax paid, labour charges.
    for line in lines:
        if re.fullmatch(r'Parts',line,re.I): section='Parts'; in_table=True; continue
        if re.fullmatch(r'Labour',line,re.I): section='Labour'; in_table=True; continue
        if not in_table: continue
        if re.search(r'^(Recommendations|Sub Total|Less Discount|CGST @|SGST @|Net Bill Amount|For FORT POINT|Gate Pass|Total Tax)',line,re.I): in_table=False; continue
        # part rows contain HSN (4-8 digits) and quantity/rate/taxable figures
        m=re.match(r'^\d{1,2}\s+([A-Z0-9-]{4,})\s+(.+?)\s+(?:[A-Z]{2,3}\s+)?(\d{4,8})(?:\s+(\d{1,2})%)?\s+(\d+\.\d{3})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})',line)
        if m and section=='Parts':
            code,desc,hsn,ratepct,qty,rate,taxable,taxpaid=m.groups(); q=num(qty); rt=num(rate); tax=num(taxable); taxpaid=num(taxpaid) or 0
            # Some DLR/RCC parts are not taxable on this invoice; don't infer GST when tax is zero.
            gst=num(ratepct) or (18 if tax and taxpaid else 0)
            c=round(tax*gst/200,2) if gst else 0; s=c; ig=0; amount=round((tax or 0)+c+s,2)
            rows.append(make_row(meta,filename,code,desc,'Parts',q,'Nos',rt,tax,gst,c,s,ig,amount,'Extracted; verify tax/discount treatment'))
            continue
        # Labour lines: code then description then SAC 998729 and amount at end; quantity/rate usually absent.
        m=re.match(r'^\d{1,2}\s+([A-Z0-9]{4,})\s+(.+?)\s+998729\b.*?([\d,]+\.\d{2})\s*$',line)
        if m and section=='Labour':
            code,desc,amount=m.groups(); amt=num(amount) or 0
            if amt==0: continue
            gst=18; c=round(amt*0.09,2); s=c
            rows.append(make_row(meta,filename,code,desc,'Labour',1,'Job',amt,amt,gst,c,s,0,round(amt+c+s,2),'Extracted; verify against PDF'))
    return rows

def parse_generic(text, meta, filename):
    # Conservative fallback: only records explicit numbered lines with HSN/SAC and a taxable/amount-like pair.
    rows=[]
    for line in [clean(x) for x in text.splitlines() if clean(x)]:
        m=re.match(r'^(\d{1,2})\s+(.+?)\s+(\d{4,8})\s+(\d+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$',line)
        if m:
            _,desc,hsn,qty,rate,amt=m.groups(); tax=num(amt); q=num(qty); rt=num(rate)
            rows.append(make_row(meta,filename,hsn,desc,'Labour' if hsn=='998729' else 'Parts',q,'Nos',rt,tax,0,0,0,0,tax,'Fallback; manual review required'))
    return rows

def make_row(meta, filename, code, desc, cat, qty, unit, rate, taxable, gst, cgst, sgst, igst, total, status):
    vals=[meta['invoice'],meta['date'],meta['vendor'],meta['vehicle'],str(code or ''),clean(desc),cat,qty,unit,rate,taxable,gst,cgst,sgst,igst,(cgst or 0)+(sgst or 0)+(igst or 0),total,status,filename]
    return dict(zip(ITEM_COLS,vals))

def extract_one(upload):
    text=extract_text(upload); meta=metadata(text,upload.name)
    if not text.strip():
        return meta, [], 'No readable PDF text. For scanned images/PDFs, install Tesseract OCR or review manually.'
    rows=[]
    if 'STAR MOTOR WORKS' in text.upper(): rows=parse_star(text,meta,upload.name)
    if not rows and ('Job Card Retail' in text or 'Reg.No.' in text): rows=parse_maruti(text,meta,upload.name)
    if not rows: rows=parse_generic(text,meta,upload.name)
    status='Extracted items; review values' if rows else 'No item rows extracted; manual review required'
    if not meta['invoice']: status += ' | Invoice number not detected'
    if not meta['printed_total']: status += ' | Printed total not detected'
    return meta,rows,status

def make_summary(item_df, reports):
    out=[]
    for r in reports:
        fname=r['Source Filename']; group=item_df[item_df['Source Filename']==fname] if not item_df.empty else pd.DataFrame(columns=ITEM_COLS)
        parts=pd.to_numeric(group.loc[group['Category'].str.lower()=='parts','Taxable Amount'],errors='coerce').fillna(0).sum() if len(group) else 0
        labour=pd.to_numeric(group.loc[group['Category'].str.lower().isin(['labour','service']),'Taxable Amount'],errors='coerce').fillna(0).sum() if len(group) else 0
        cg=pd.to_numeric(group['CGST'],errors='coerce').fillna(0).sum() if len(group) else 0
        sg=pd.to_numeric(group['SGST'],errors='coerce').fillna(0).sum() if len(group) else 0
        ig=pd.to_numeric(group['IGST'],errors='coerce').fillna(0).sum() if len(group) else 0
        total_taxable=parts+labour
        extracted=pd.to_numeric(group['Total Amount'],errors='coerce').fillna(0).sum() if len(group) else 0
        printed=r['Printed Invoice Total']
        rec='No items extracted; manual review required' if group.empty else 'Review: extracted total vs printed total'
        if printed is not None and not pd.isna(printed) and not group.empty:
            rec=f'Difference {extracted-float(printed):.2f}; verify discounts/rounding/tax'
        out.append(dict(zip(SUMMARY_COLS,[r['Detected Invoice No.'],r.get('Invoice Date',''),r['Detected Vendor'],r['Detected Vehicle'],round(parts,2),round(labour,2),round(total_taxable,2),round(cg,2),round(sg,2),round(ig,2),round(extracted,2),printed,rec])))
    return pd.DataFrame(out,columns=SUMMARY_COLS)

st.set_page_config(page_title=APP_TITLE,layout='wide')
st.title(APP_TITLE)
st.write('Upload invoices in bulk. Filenames may be anything; invoice details are extracted from invoice content. Output columns follow the agreed sample workbook.')
st.warning('Extraction is best-effort. Verify every item and total against the source invoice before posting to Tally. Scanned PDFs require OCR support.')
files=st.file_uploader('Upload PDF invoices or images',type=['pdf','png','jpg','jpeg','tif','tiff','bmp','webp'],accept_multiple_files=True)
if files and st.button('Process invoices',type='primary'):
    allrows=[]; reports=[]
    bar=st.progress(0)
    for i,f in enumerate(files):
        meta,rows,status=extract_one(f)
        allrows.extend(rows)
        reports.append({'Source Filename':f.name,'Detected Invoice No.':meta['invoice'],'Detected Vendor':meta['vendor'],'Detected Vehicle':meta['vehicle'],'Items Extracted':len(rows),'Printed Invoice Total':meta['printed_total'],'Status / Review':status,'Invoice Date':meta['date']})
        bar.progress((i+1)/len(files))
    item_df=pd.DataFrame(allrows,columns=ITEM_COLS)
    summary_df=make_summary(item_df,reports)
    report_df=pd.DataFrame(reports,columns=REPORT_COLS)
    st.subheader('Processing report')
    st.dataframe(report_df,use_container_width=True,hide_index=True)
    st.subheader('Item Details preview')
    st.dataframe(item_df,use_container_width=True,hide_index=True)
    st.subheader('Invoice Summary preview')
    st.dataframe(summary_df,use_container_width=True,hide_index=True)
    output=io.BytesIO()
    with pd.ExcelWriter(output,engine='openpyxl') as writer:
        item_df.to_excel(writer,index=False,sheet_name='Item Details')
        summary_df.to_excel(writer,index=False,sheet_name='Invoice Summary')
        report_df.to_excel(writer,index=False,sheet_name='Processing Report')
        for ws in writer.book.worksheets:
            ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
            for col in ws.columns:
                maxlen=max((len(str(c.value or '')) for c in list(col)[:200]),default=10)
                ws.column_dimensions[col[0].column_letter].width=min(max(maxlen+2,12),38)
    st.download_button('Download Excel output',data=output.getvalue(),file_name='Vehicle_Maintenance_Invoice_Output.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
