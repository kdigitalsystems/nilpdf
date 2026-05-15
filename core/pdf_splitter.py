import js
from pyscript import document
import io
from pypdf import PdfWriter, PdfReader
from pyodide.ffi import to_js

def parse_page_ranges(range_str, max_pages):
    """Converts a string like '1, 3-5' into a list of 0-indexed page numbers."""
    pages = set()
    if not range_str.strip():
        raise ValueError("Page range cannot be empty.")
        
    for part in range_str.replace(" ", "").split(","):
        if "-" in part:
            start, end = part.split("-")
            for p in range(int(start), int(end) + 1):
                pages.add(p - 1) # Convert to 0-indexed
        else:
            pages.add(int(part) - 1)
            
    # Filter valid pages and sort
    valid_pages = sorted([p for p in pages if 0 <= p < max_pages])
    if not valid_pages:
        raise ValueError("No valid pages found in that range.")
    return valid_pages

async def split_pdf():
    status_div = document.getElementById("split-status")
    file_input = document.getElementById('split-upload')
    range_input = document.getElementById('page-range').value
    
    if file_input.files.length != 1:
        status_div.innerText = "Error: Please select exactly one PDF to split."
        status_div.className = "status-message text-red"
        return

    status_div.innerText = "Extracting pages in memory..."
    status_div.className = "status-message"
    
    try:
        file = file_input.files.item(0)
        buf = await file.arrayBuffer()
        
        reader = PdfReader(io.BytesIO(buf.to_bytes()))
        
        if reader.is_encrypted:
            reader.decrypt("")
            if reader.is_encrypted:
                raise ValueError("File is password protected. Please unlock it first.")

        # Parse user input against the actual document length
        target_pages = parse_page_ranges(range_input, len(reader.pages))
        
        writer = PdfWriter()
        for page_num in target_pages:
            writer.add_page(reader.pages[page_num])
            
        out_stream = io.BytesIO()
        writer.write(out_stream)
        
        js_array = js.Uint8Array.new(to_js(out_stream.getvalue()))
        blob = js.Blob.new([js_array], type="application/pdf")
        url = js.URL.createObjectURL(blob)
        
        link = document.createElement("a")
        link.href = url
        link.download = f"Extracted_{file.name}"
        link.click()
        
        js.URL.revokeObjectURL(url)
        status_div.innerText = f"Successfully extracted {len(target_pages)} pages."
        status_div.className = "status-message text-green"

    except ValueError as ve:
        status_div.innerText = str(ve)
        status_div.className = "status-message text-red"
    except Exception as e:
        status_div.innerText = f"Extraction Error: {str(e)}"
        status_div.className = "status-message text-red"
