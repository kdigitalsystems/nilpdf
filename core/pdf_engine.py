import io
from pypdf import PdfWriter, PdfReader

def process_merge(js_buffers):
    merger = PdfWriter()
    # Iterate through the JavaScript array of Uint8Arrays
    for js_buf in js_buffers:
        # Convert JS memory to Python memory
        reader = PdfReader(io.BytesIO(js_buf.to_py()))
        if reader.is_encrypted:
            reader.decrypt("")
        merger.append(reader)
        
    out_stream = io.BytesIO()
    merger.write(out_stream)
    return out_stream.getvalue()

def process_split(js_buf, page_indices):
    reader = PdfReader(io.BytesIO(js_buf.to_py()))
    if reader.is_encrypted:
        reader.decrypt("")
        
    writer = PdfWriter()
    # page_indices is passed in from JS as a clean list of integers
    for idx in page_indices:
        writer.add_page(reader.pages[idx])
        
    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()

def process_reorder(js_buf, new_order):
    reader = PdfReader(io.BytesIO(js_buf.to_py()))
    if reader.is_encrypted:
        reader.decrypt("")
        
    writer = PdfWriter()
    for idx in new_order:
        writer.add_page(reader.pages[idx])
        
    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()
