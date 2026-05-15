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


def process_anonymize(js_buf):
    reader = PdfReader(io.BytesIO(_ensure_py(js_buf)))
    if reader.is_encrypted:
        reader.decrypt("")

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    # 1. THE STANDARD SCRUB
    # We overwrite with empty strings to force the keys to exist but be blank.
    writer.add_metadata({
        "/Author": "",
        "/Creator": "",
        "/Producer": "LocalPDF (Private)",
        "/Subject": "",
        "/Title": "",
        "/Keywords": "",
        "/CreationDate": "D:19700101000000Z", # Unix Epoch (neutral date)
        "/ModDate": "D:19700101000000Z"
    })

    # 2. THE NUCLEAR SCRUB (XMP Data)
    # Modern PDFs store an XML stream that many viewers prioritize.
    # We explicitly wipe the XMP metadata to ensure total anonymity.
    writer._xmp_metadata = None

    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()
