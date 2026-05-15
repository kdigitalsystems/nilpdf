import io
from pypdf import PdfWriter, PdfReader

def process_merge(js_buffers):
    merger = PdfWriter()
    # Explicitly convert JS array to Python list
    for buf in js_buffers.to_py():
        reader = PdfReader(io.BytesIO(buf))
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
    for idx in page_indices.to_py():
        if 0 <= idx < len(reader.pages):
            writer.add_page(reader.pages[idx])
    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()

def process_reorder(js_buf, new_order):
    reader = PdfReader(io.BytesIO(js_buf.to_py()))
    if reader.is_encrypted:
        reader.decrypt("")
    writer = PdfWriter()
    for idx in new_order.to_py():
        if 0 <= idx < len(reader.pages):
            writer.add_page(reader.pages[idx])
    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()
