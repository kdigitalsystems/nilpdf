import js
from pyscript import document
import io
from pypdf import PdfWriter, PdfReader
from pyodide.ffi import to_js

async def merge_pdfs():
    status_div = document.getElementById("status")
    file_input = document.getElementById('pdf-upload')
    
    if file_input.files.length < 2:
        status_div.innerText = "Error: Please select at least two PDFs to merge."
        status_div.className = "status-message text-red"
        return

    status_div.innerText = f"Fusing {file_input.files.length} files in memory..."
    status_div.className = "status-message"
    
    try:
        merger = PdfWriter()
        
        for i in range(file_input.files.length):
            file = file_input.files.item(i)
            buf = await file.arrayBuffer()
            file_bytes = buf.to_bytes()
            
            # Use PdfReader to inspect the file before merging
            reader = PdfReader(io.BytesIO(file_bytes))
            
            # Handle Encryption
            if reader.is_encrypted:
                # Attempt to decrypt with a blank password (common for restriction-only encryption)
                reader.decrypt("")
                
                # If it is STILL encrypted, it requires a real password
                if reader.is_encrypted:
                    raise ValueError(f"'{file.name}' is password protected. Please unlock it first.")
            
            # Append the inspected (and potentially decrypted) reader
            merger.append(reader)
            
        # Write to virtual RAM buffer
        out_stream = io.BytesIO()
        merger.write(out_stream)
        out_data = out_stream.getvalue()

        # Export back to JS context
        js_array = js.Uint8Array.new(to_js(out_data))
        blob = js.Blob.new([js_array], type="application/pdf")
        url = js.URL.createObjectURL(blob)
        
        link = document.createElement("a")
        link.href = url
        link.download = "LocalPDF_Fused.pdf"
        link.click()
        
        js.URL.revokeObjectURL(url)
        
        status_div.innerText = "Operation Successful. File exported securely."
        status_div.className = "status-message text-green"

    except ValueError as ve:
        # Catch our custom password error gracefully
        status_div.innerText = str(ve)
        status_div.className = "status-message text-red"
    except Exception as e:
        status_div.innerText = f"Processing Exception: {str(e)}"
        status_div.className = "status-message text-red"
