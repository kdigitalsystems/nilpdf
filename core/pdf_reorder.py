import js
from pyscript import document
import io
from pypdf import PdfWriter, PdfReader
from pyodide.ffi import to_js

async def reorder_pdf():
    status_div = document.getElementById("reorder-status")
    file_input = document.getElementById('reorder-upload')
    
    # The JS UI will write the new page order into this hidden input field as "2,0,1,3"
    new_order_str = document.getElementById('new-page-order').value
    
    if file_input.files.length != 1:
        status_div.innerText = "Error: Please upload a PDF to reorder."
        status_div.className = "status-message text-red"
        return

    if not new_order_str:
        status_div.innerText = "Error: No page order detected."
        return

    status_div.innerText = "Reconstructing binary..."
    status_div.className = "status-message"
    
    try:
        # Read the file
        file = file_input.files.item(0)
        buf = await file.arrayBuffer()
        reader = PdfReader(io.BytesIO(buf.to_bytes()))
        
        if reader.is_encrypted:
            reader.decrypt("")
            if reader.is_encrypted:
                raise ValueError("File is password protected. Please unlock it first.")

        # Parse the new order array (e.g., "2,0,1,3" -> [2, 0, 1, 3])
        page_indices = [int(x) for x in new_order_str.split(',')]
        
        # Build the new PDF
        writer = PdfWriter()
        for idx in page_indices:
            writer.add_page(reader.pages[idx])
            
        # Export
        out_stream = io.BytesIO()
        writer.write(out_stream)
        
        js_array = js.Uint8Array.new(to_js(out_stream.getvalue()))
        blob = js.Blob.new([js_array], type="application/pdf")
        url = js.URL.createObjectURL(blob)
        
        link = document.createElement("a")
        link.href = url
        link.download = f"Reordered_{file.name}"
        link.click()
        
        js.URL.revokeObjectURL(url)
        status_div.innerText = "Successfully saved new PDF order."
        status_div.className = "status-message text-green"

    except Exception as e:
        status_div.innerText = f"Error: {str(e)}"
        status_div.className = "status-message text-red"
