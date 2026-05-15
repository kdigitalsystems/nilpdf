import js
from pyscript import document
import io
from pypdf import PdfWriter
from pyodide.ffi import to_js

async def merge_pdfs():
    status_div = document.getElementById("status")
    status_div.innerText = "Processing locally..."
    status_div.className = ""
    
    try:
        # 1. Grab the DOM elements
        file1_input = document.getElementById('pdf1')
        file2_input = document.getElementById('pdf2')
        
        if file1_input.files.length == 0 or file2_input.files.length == 0:
            status_div.innerText = "Please select both PDFs."
            status_div.className = "text-red"
            return

        # 2. Read files natively into JS ArrayBuffers, then cast to Python bytes
        buf1 = await file1_input.files.item(0).arrayBuffer()
        buf2 = await file2_input.files.item(0).arrayBuffer()
        
        bytes1 = buf1.to_bytes()
        bytes2 = buf2.to_bytes()

        # 3. Execute Standard Python logic (pypdf)
        merger = PdfWriter()
        merger.append(io.BytesIO(bytes1))
        merger.append(io.BytesIO(bytes2))
        
        # 4. Save to a virtual memory buffer
        out_stream = io.BytesIO()
        merger.write(out_stream)
        out_data = out_stream.getvalue()

        # 5. Send back to JavaScript for download
        js_array = js.Uint8Array.new(to_js(out_data))
        blob = js.Blob.new([js_array], type="application/pdf")
        url = js.URL.createObjectURL(blob)
        
        link = document.createElement("a")
        link.href = url
        link.download = "Merged_Private.pdf"
        link.click()
        
        # Clean up memory
        js.URL.revokeObjectURL(url)
        
        status_div.innerText = "Success! File downloaded."
        status_div.className = "text-green"

    except Exception as e:
        status_div.innerText = f"Error: {str(e)}"
        status_div.className = "text-red"
