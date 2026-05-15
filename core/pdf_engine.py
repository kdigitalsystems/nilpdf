import io
from pypdf import PdfWriter, PdfReader

def _ensure_py(data):
    """Helper to handle both Browser (Pyodide) and Native Python (CI) inputs."""
    return data.to_py() if hasattr(data, 'to_py') else data

def process_merge(js_buffers):
    merger = PdfWriter()
    for buf in _ensure_py(js_buffers):
        reader = PdfReader(io.BytesIO(buf))
        if reader.is_encrypted:
            reader.decrypt("")
        merger.append(reader)
    out_stream = io.BytesIO()
    merger.write(out_stream)
    return out_stream.getvalue()

def process_split(js_buf, page_indices):
    reader = PdfReader(io.BytesIO(_ensure_py(js_buf)))
    if reader.is_encrypted:
        reader.decrypt("")
    writer = PdfWriter()
    for idx in _ensure_py(page_indices):
        if 0 <= idx < len(reader.pages):
            writer.add_page(reader.pages[idx])
    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()

def process_reorder(js_buf, new_order):
    reader = PdfReader(io.BytesIO(_ensure_py(js_buf)))
    if reader.is_encrypted:
        reader.decrypt("")
    writer = PdfWriter()
    for idx in _ensure_py(new_order):
        if 0 <= idx < len(reader.pages):
            writer.add_page(reader.pages[idx])
    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()
