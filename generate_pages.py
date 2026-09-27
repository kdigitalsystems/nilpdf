"""Generate SEO landing pages for each NilPDF tool."""
import json
import os

TOOLS = [
    {
        'slug': 'merge-pdf',
        'tool_id': 'merge',
        'title': 'Merge PDF Files Free Online | NilPDF',
        'h1': 'Merge PDF Files',
        'tagline': 'Combine multiple PDFs into one file, instantly, privately, for free.',
        'description': 'Free online PDF merger. Combine multiple PDF files into one. No uploads, no account, runs entirely in your browser.',
        'keywords': 'merge pdf, combine pdf, join pdf files, merge pdf free online',
        'bullets': [
            'Drag and drop any number of PDFs in any order',
            'Reorder files before merging with a click',
            'Password-protected PDFs supported',
            'Files never leave your device, zero uploads',
        ],
        'body_text': 'NilPDF Merge runs entirely in your browser using WebAssembly, no file ever leaves your device. Whether you\'re combining contracts, reports, or scanned documents, the result is a single, clean PDF downloaded directly to you. Files up to 200MB each are supported, no account required, and no data sent to any server.',
        'how_to_name': 'How to merge PDF files',
        'how_to_steps': [
            ('Open NilPDF Merge', 'Visit nilpdf.com and select the Merge tool.'),
            ('Add your PDFs', 'Drag and drop your PDF files or click Browse to select them.'),
            ('Arrange order', 'Drag files into the order you want.'),
            ('Merge', 'Click "Merge Files", the combined PDF downloads automatically.'),
        ],
        'faq': [
            ('Is merging PDF files really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I merge them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('How many PDFs can I merge at once?', "There's no limit. You can drag in as many files as you need, reorder them, and merge into one."),
        ],
        'related': [
            ('split-pdf', 'Split PDF'),
            ('compress-pdf', 'Compress PDF'),
        ],
    },
    {
        'slug': 'compress-pdf',
        'tool_id': 'compress',
        'title': 'Compress PDF Online Free | NilPDF',
        'h1': 'Compress PDF Online',
        'tagline': 'Optimize PDF structure and embedded resources to reduce file size, free and private.',
        'description': 'Free online PDF compressor. Shrink PDF files for email or upload. No server uploads, runs entirely in your browser.',
        'keywords': 'compress pdf, reduce pdf size, shrink pdf, compress pdf free online',
        'bullets': [
            'Compresses images and removes redundant data',
            'Batch-compress multiple PDFs at once',
            'Shows before/after file size comparison',
            'No uploads, your files stay on your device',
        ],
        'body_text': 'NilPDF Compress shrinks PDFs by optimising image data and removing redundant cross-reference tables, all inside your browser. No account, files up to 200MB supported, no waiting for a server to process your files. Simply drop your PDF, click compress, and the smaller file downloads instantly.',
        'how_to_name': 'How to compress a PDF',
        'how_to_steps': [
            ('Open NilPDF Compress', 'Visit nilpdf.com and select the Compress PDF tool.'),
            ('Select your PDF', 'Drop your PDF file or click Browse.'),
            ('Compress', 'Click "Optimize Size", the smaller PDF downloads automatically.'),
        ],
        'faq': [
            ('Is compressing a PDF really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I compress them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('How much will my PDF shrink?', 'It depends on the content, PDFs with large images typically compress 30-70%. Text-only PDFs compress less.'),
        ],
        'related': [
            ('merge-pdf', 'Merge PDF'),
            ('remove-pdf-metadata', 'Remove Metadata'),
        ],
    },
    {
        'slug': 'split-pdf',
        'tool_id': 'split',
        'title': 'Split PDF Online Free | NilPDF',
        'h1': 'Split PDF Online',
        'tagline': 'Extract pages or split a PDF into multiple files, free and private.',
        'description': 'Free online PDF splitter. Extract specific pages or split into separate files. No uploads, runs in your browser.',
        'keywords': 'split pdf, extract pdf pages, split pdf free online, pdf page extractor',
        'bullets': [
            'Extract any pages by number (e.g. 1-3, 5, 7-9)',
            'Split into separate files, downloads as ZIP',
            'Works with encrypted PDFs',
            'Zero uploads, all processing in your browser',
        ],
        'body_text': 'NilPDF Split lets you extract any combination of pages from a PDF without uploading anything to a server. Type a range like 2-5 or individual page numbers, and your extracted PDF or ZIP of separate files downloads in seconds. No account, files up to 200MB supported, no data shared with anyone.',
        'how_to_name': 'How to split a PDF',
        'how_to_steps': [
            ('Open NilPDF Split', 'Visit nilpdf.com and select the Split tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Enter pages', 'Type the page numbers or ranges you want to extract.'),
            ('Split', 'Click "Extract Pages", your PDF downloads instantly.'),
        ],
        'faq': [
            ('Is splitting a PDF really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I split them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Can I extract just one page?', 'Yes, enter a single page number (e.g. "3") to extract just that page as a separate PDF.'),
        ],
        'related': [
            ('merge-pdf', 'Merge PDF'),
            ('remove-pdf-pages', 'Remove Pages'),
        ],
    },
    {
        'slug': 'pdf-to-images',
        'tool_id': 'topng',
        'title': 'PDF to Images: Convert PDF to JPG/PNG Free | NilPDF',
        'h1': 'PDF to Images',
        'tagline': 'Convert every page of a PDF to JPG or PNG images, free, instant, private.',
        'description': 'Free online PDF to image converter. Export each page as JPG or PNG. No uploads, runs entirely in your browser.',
        'keywords': 'pdf to jpg, pdf to png, pdf to image, convert pdf to jpg free',
        'bullets': [
            'Converts every page to a separate image',
            'Choose JPG (smaller) or PNG (lossless)',
            'Downloads all images in a ZIP file',
            'Runs locally, no server, no uploads',
        ],
        'body_text': 'NilPDF converts each PDF page to a separate JPG or PNG image directly in your browser. Every page is rendered locally using WebAssembly, no cloud service, no upload limits, and your documents stay completely private. All images are bundled into a convenient ZIP file ready to download.',
        'how_to_name': 'How to convert PDF to images',
        'how_to_steps': [
            ('Open NilPDF PDF to Images', 'Visit nilpdf.com and select the PDF to Images tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Choose format', 'Select JPG or PNG from the dropdown.'),
            ('Convert', 'Click "Convert to Images", a ZIP of all pages downloads.'),
        ],
        'faq': [
            ('Is converting PDF to images really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I convert them to images?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('What resolution are the exported images?', 'Pages are exported at 144 DPI by default, suitable for screen use and presentations.'),
        ],
        'related': [
            ('images-to-pdf', 'Images to PDF'),
            ('pdf-to-text', 'PDF to Text'),
        ],
    },
    {
        'slug': 'images-to-pdf',
        'tool_id': 'topdf',
        'title': 'Images to PDF: Convert JPG/PNG to PDF Free | NilPDF',
        'h1': 'Images to PDF',
        'tagline': 'Combine JPG or PNG images into a single PDF, free and private.',
        'description': 'Free online image to PDF converter. Turn JPG and PNG files into a PDF. No uploads, runs entirely in your browser.',
        'keywords': 'jpg to pdf, images to pdf, png to pdf, convert images to pdf free',
        'bullets': [
            'Supports JPG and PNG in any combination',
            'Add multiple images, each becomes a page',
            'Maintains original image quality',
            'No cloud upload, all local processing',
        ],
        'body_text': 'NilPDF bundles your photos and screenshots into a single PDF locally, nothing is sent to a server. Mix JPG and PNG images freely, arrange them in the order you want, and download the result in one click. No account required, files up to 200MB each are supported.',
        'how_to_name': 'How to convert images to PDF',
        'how_to_steps': [
            ('Open NilPDF Images to PDF', 'Visit nilpdf.com and select the Images to PDF tool.'),
            ('Add images', 'Drop your JPG/PNG files or click Browse.'),
            ('Create PDF', 'Click "Create PDF", your PDF downloads immediately.'),
        ],
        'faq': [
            ('Is converting images to PDF really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my image files safe when I convert them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('What image formats are supported?', 'JPG and PNG are supported.'),
        ],
        'related': [
            ('pdf-to-images', 'PDF to Images'),
            ('merge-pdf', 'Merge PDF'),
        ],
    },
    {
        'slug': 'rotate-pdf',
        'tool_id': 'rotate',
        'title': 'Rotate PDF Pages Online Free | NilPDF',
        'h1': 'Rotate PDF Pages',
        'tagline': 'Rotate any pages in a PDF by 90° or 180°, free and private.',
        'description': 'Free online PDF page rotator. Rotate specific pages or the entire document. No uploads, runs in your browser.',
        'keywords': 'rotate pdf, rotate pdf pages, fix pdf orientation, rotate pdf free online',
        'bullets': [
            'Rotate 90° clockwise, counter-clockwise, or 180°',
            'Rotate all pages or select specific ones',
            'Works with password-protected PDFs',
            'No file uploads, your PDF stays on your device',
        ],
        'body_text': 'NilPDF Rotate corrects mis-scanned or sideways pages without re-encoding your entire document. Choose a rotation angle, target specific pages or the whole file, and download the fixed PDF, all processed locally in your browser with no data sent anywhere.',
        'how_to_name': 'How to rotate PDF pages',
        'how_to_steps': [
            ('Open NilPDF Rotate', 'Visit nilpdf.com and select the Rotate tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Set rotation', 'Choose angle and optionally enter specific page numbers.'),
            ('Rotate', 'Click "Rotate Pages", your corrected PDF downloads.'),
        ],
        'faq': [
            ('Is rotating PDF pages really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I rotate them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Can I rotate just some pages, not all?', 'Yes, specify which pages to rotate or choose to rotate all pages at once.'),
        ],
        'related': [
            ('remove-pdf-pages', 'Remove Pages'),
            ('reorder-pdf-pages', 'Reorder Pages'),
        ],
    },
    {
        'slug': 'pdf-to-text',
        'tool_id': 'totext',
        'title': 'Extract Text from PDF Free Online | NilPDF',
        'h1': 'PDF to Text',
        'tagline': 'Extract all text content from any PDF, free, private, no uploads.',
        'description': 'Free online PDF text extractor. Copy all text from a PDF file. No server uploads, runs entirely in your browser.',
        'keywords': 'pdf to text, extract text from pdf, pdf text extractor, copy text from pdf',
        'bullets': [
            'Extracts all text from every page',
            'Preview extracted text directly in the browser',
            'Copy to clipboard or download as .txt file',
            'Zero uploads, processed locally on your device',
        ],
        'body_text': 'NilPDF extracts all embedded text from every page of your PDF locally, with no server required. The result can be previewed instantly in the browser, copied to clipboard, or downloaded as a plain .txt file, useful for searching, editing, or repurposing document content.',
        'how_to_name': 'How to extract text from a PDF',
        'how_to_steps': [
            ('Open NilPDF PDF to Text', 'Visit nilpdf.com and select the PDF to Text tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Extract', 'Click "Extract Text", preview and copy or download the result.'),
        ],
        'faq': [
            ('Is extracting text from a PDF really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I extract text?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Does it work on scanned PDFs?', 'It extracts embedded text only. Scanned PDFs (images of text) require OCR which is not yet supported.'),
        ],
        'related': [
            ('pdf-to-images', 'PDF to Images'),
            ('inspect-pdf', 'Inspect PDF'),
        ],
    },
    {
        'slug': 'watermark-pdf',
        'tool_id': 'watermark',
        'title': 'Add Watermark to PDF Free Online | NilPDF',
        'h1': 'Add Watermark to PDF',
        'tagline': 'Stamp a diagonal text watermark on any PDF, free and private.',
        'description': 'Free online PDF watermark tool. Add CONFIDENTIAL, DRAFT, or any custom text. No uploads, runs in your browser.',
        'keywords': 'watermark pdf, add watermark to pdf, pdf watermark online, stamp pdf',
        'bullets': [
            'Custom watermark text, any word or phrase',
            'Adjustable opacity (10%-80%)',
            'Diagonal placement across every page',
            'No cloud processing, runs in your browser',
        ],
        'body_text': 'NilPDF Watermark stamps your chosen text diagonally across every page of your PDF, entirely in your browser. Adjust the font size and opacity to suit your needs, then download the watermarked file instantly. Common uses include marking drafts as CONFIDENTIAL, DRAFT, or DO NOT COPY before sharing.',
        'how_to_name': 'How to add a watermark to a PDF',
        'how_to_steps': [
            ('Open NilPDF Watermark', 'Visit nilpdf.com and select the Add Watermark tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Enter text', 'Type your watermark text (e.g. CONFIDENTIAL) and set opacity.'),
            ('Apply', 'Click "Apply Watermark", your watermarked PDF downloads.'),
        ],
        'faq': [
            ('Is adding a watermark to a PDF really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I watermark them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Can I control how big the watermark is?', 'Yes, you can adjust the font size and opacity from the tool settings.'),
        ],
        'related': [
            ('add-page-numbers-pdf', 'Add Page Numbers'),
            ('remove-pdf-metadata', 'Remove Metadata'),
        ],
    },
    {
        'slug': 'remove-pdf-pages',
        'tool_id': 'remove',
        'title': 'Remove Pages from PDF Free Online | NilPDF',
        'h1': 'Remove PDF Pages',
        'tagline': 'Delete unwanted pages from any PDF, free, instant, private.',
        'description': 'Free online PDF page remover. Delete specific pages from a PDF file. No uploads, runs entirely in your browser.',
        'keywords': 'remove pages from pdf, delete pdf pages, pdf page remover, remove page pdf free',
        'bullets': [
            'Remove any pages by number (e.g. 1, 3-5)',
            'Live preview shows which pages will be removed',
            'Works with encrypted PDFs',
            'Files never leave your browser, zero uploads',
        ],
        'body_text': 'NilPDF Remove Pages lets you delete any unwanted pages from a PDF without uploading the file anywhere. Enter individual page numbers or ranges, preview which pages will be removed, and download the trimmed PDF. The original file is never sent to a server.',
        'how_to_name': 'How to remove pages from a PDF',
        'how_to_steps': [
            ('Open NilPDF Remove Pages', 'Visit nilpdf.com and select the Remove tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Enter pages', 'Type the page numbers you want to delete.'),
            ('Remove', 'Click "Remove Pages", your trimmed PDF downloads.'),
        ],
        'faq': [
            ('Is removing PDF pages really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I remove pages?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Can I remove multiple pages at once?', 'Yes, enter a comma-separated list (e.g. 1,3,5) or a range (e.g. 2-4) to remove multiple pages.'),
        ],
        'related': [
            ('split-pdf', 'Split PDF'),
            ('reorder-pdf-pages', 'Reorder Pages'),
        ],
    },
    {
        'slug': 'reorder-pdf-pages',
        'tool_id': 'reorder',
        'title': 'Reorder PDF Pages Online Free | NilPDF',
        'h1': 'Reorder PDF Pages',
        'tagline': 'Drag and drop to rearrange pages in any PDF, free and private.',
        'description': 'Free online PDF page reorder tool. Drag thumbnails to change page order. No uploads, runs in your browser.',
        'keywords': 'reorder pdf pages, rearrange pdf pages, change page order pdf, pdf reorder free',
        'bullets': [
            'Visual drag-and-drop thumbnails for every page',
            'Instantly see the new page order before saving',
            'Supports password-protected PDFs',
            'Local processing, no file uploads needed',
        ],
        'body_text': 'NilPDF Reorder shows a visual thumbnail grid of every page and lets you drag them into any order before saving. The entire operation, loading, rearranging, and exporting, happens locally inside your browser with no data sent to any server.',
        'how_to_name': 'How to reorder PDF pages',
        'how_to_steps': [
            ('Open NilPDF Reorder', 'Visit nilpdf.com and select the Reorder Pages tool.'),
            ('Upload your PDF', 'Drop your PDF or click "Load for Reordering".'),
            ('Drag pages', 'Drag the page thumbnails into the order you want.'),
            ('Save', 'Click "Save Reordered PDF", your PDF downloads.'),
        ],
        'faq': [
            ('Is reordering PDF pages really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I reorder them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Is there a page limit for reordering?', 'No, the drag-and-drop reorder tool works with PDFs of any length.'),
        ],
        'related': [
            ('remove-pdf-pages', 'Remove Pages'),
            ('rotate-pdf', 'Rotate PDF'),
        ],
    },
    {
        'slug': 'add-page-numbers-pdf',
        'tool_id': 'pagenums',
        'title': 'Add Page Numbers to PDF Free Online | NilPDF',
        'h1': 'Add Page Numbers to PDF',
        'tagline': 'Stamp page numbers onto any PDF, choose position and starting number.',
        'description': 'Free online tool to add page numbers to PDF files. No uploads, runs entirely in your browser.',
        'keywords': 'add page numbers to pdf, pdf page numbering, number pages in pdf, pdf page numbers free',
        'bullets': [
            'Six placement options (bottom centre, corners, top)',
            'Custom starting number',
            'Works with encrypted PDFs',
            'Zero server uploads, runs locally in your browser',
        ],
        'body_text': 'NilPDF adds clean page numbers to every page of your PDF without uploading anything. Choose from six placement positions, set a custom starting number, and download the numbered PDF in seconds. Ideal for reports, contracts, and any document that needs clear pagination.',
        'how_to_name': 'How to add page numbers to a PDF',
        'how_to_steps': [
            ('Open NilPDF Page Numbers', 'Visit nilpdf.com and select the Add Page Numbers tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Configure', 'Choose position and starting number.'),
            ('Apply', 'Click "Add Page Numbers", your numbered PDF downloads.'),
        ],
        'faq': [
            ('Is adding page numbers to a PDF really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I add page numbers?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Can I choose where the page number appears?', 'Yes, six positions are available: bottom centre, bottom corners, top centre, and top corners.'),
        ],
        'related': [
            ('watermark-pdf', 'Watermark PDF'),
            ('merge-pdf', 'Merge PDF'),
        ],
    },
    {
        'slug': 'remove-pdf-metadata',
        'tool_id': 'anonymize',
        'title': 'Remove PDF Metadata Online Free | NilPDF',
        'h1': 'Remove PDF Metadata',
        'tagline': 'Strip hidden author, title, and tracking data from any PDF, privately.',
        'description': 'Free online PDF metadata remover. Strip author, title, creator, and all hidden data. No uploads, runs in your browser.',
        'keywords': 'remove pdf metadata, strip pdf metadata, pdf anonymizer, clean pdf metadata free',
        'bullets': [
            'Removes author, title, creator, subject, and all custom fields',
            'Batch-process multiple PDFs at once',
            'Protects your privacy before sharing documents',
            'No uploads, metadata never sent to any server',
        ],
        'body_text': "NilPDF erases all hidden identity data from your PDF before you share it, author name, software used, edit timestamps, and XMP fields. Everything is processed locally; your document never touches a server. A clean PDF with no identifying metadata downloads in seconds.",
        'how_to_name': 'How to remove PDF metadata',
        'how_to_steps': [
            ('Open NilPDF Remove Metadata', 'Visit nilpdf.com and select the Remove Metadata tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Remove metadata', 'Click "Strip Identifiers", your clean PDF downloads.'),
        ],
        'faq': [
            ('Is removing PDF metadata really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I remove metadata?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('What metadata gets removed?', 'Author, title, subject, creator, producer, keywords, and all custom XMP metadata fields.'),
        ],
        'related': [
            ('inspect-pdf', 'Inspect PDF'),
            ('compress-pdf', 'Compress PDF'),
        ],
    },
    {
        'slug': 'inspect-pdf',
        'tool_id': 'inspect',
        'title': 'Inspect PDF Metadata Online Free | NilPDF',
        'h1': 'Inspect PDF',
        'tagline': 'View PDF metadata, page count, fonts, and document properties, instantly.',
        'description': 'Free online PDF inspector. See author, title, creator, creation date, page count, and embedded fonts. No uploads.',
        'keywords': 'inspect pdf, pdf metadata viewer, view pdf properties, pdf info online',
        'bullets': [
            'Shows author, title, creator, subject, creation date',
            'Lists page count and PDF version',
            'Displays embedded fonts',
            'Instant results, no uploads, no waiting',
        ],
        'body_text': "NilPDF Inspect reads your PDF's internal structure locally and displays all metadata fields, embedded fonts, and document properties in a clean table. No file leaves your device, results appear in seconds. Use it to verify what information is stored inside a PDF before sharing it.",
        'how_to_name': 'How to inspect a PDF',
        'how_to_steps': [
            ('Open NilPDF Inspect', 'Visit nilpdf.com and select the Inspect tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('View results', 'All metadata and document properties appear immediately.'),
        ],
        'faq': [
            ('Is inspecting a PDF really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I inspect them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Does it show the PDF version?', 'Yes, the tool shows the PDF version, page count, all standard metadata fields, and embedded font names.'),
        ],
        'related': [
            ('remove-pdf-metadata', 'Remove Metadata'),
            ('pdf-to-text', 'PDF to Text'),
        ],
    },
    {
        'slug': 'repair-pdf',
        'tool_id': 'repair',
        'title': 'Repair PDF Online Free | NilPDF',
        'h1': 'Repair PDF',
        'tagline': 'Recover pages from corrupted or damaged PDF files, free and private.',
        'description': 'Free online PDF repair tool. Recover pages from corrupted or truncated PDF files. No uploads, runs entirely in your browser.',
        'keywords': 'repair pdf, fix corrupted pdf, recover pdf, pdf repair tool free',
        'bullets': [
            'Recovers pages from truncated or corrupted PDFs',
            'Skips unreadable pages and saves all recoverable content',
            'Works on cross-reference table errors',
            'No uploads, your file never leaves your device',
        ],
        'body_text': 'NilPDF Repair attempts to recover readable pages from corrupted, truncated, or damaged PDF files, entirely in your browser. Pages that cannot be decoded are skipped; all recoverable pages are packaged into a new, clean PDF ready to download. No account required, no data sent to any server.',
        'how_to_name': 'How to repair a corrupted PDF',
        'how_to_steps': [
            ('Open NilPDF Repair', 'Visit nilpdf.com and select the Repair tool.'),
            ('Upload your PDF', 'Drop your corrupted PDF or click Browse.'),
            ('Recover', 'Click "Recover PDF", readable pages are extracted and saved.'),
            ('Download', 'Your repaired PDF downloads automatically.'),
        ],
        'faq': [
            ('Is repairing a PDF really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I repair them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('What kind of corruption can it fix?', "It recovers from truncated files and cross-reference table errors. Pages that can't be read are skipped; readable pages are saved."),
        ],
        'related': [
            ('inspect-pdf', 'Inspect PDF'),
            ('merge-pdf', 'Merge PDF'),
        ],
    },
    {
        'slug': 'redact-pdf',
        'tool_id': 'redact',
        'title': 'Redact PDF Online Free | NilPDF',
        'h1': 'Redact PDF',
        'tagline': 'Permanently black out sensitive areas of a PDF. Free and private.',
        'description': 'Free online PDF redaction tool. Black out sensitive text or images and add custom notes. The page is rebuilt from a flattened image, so the underlying content is actually removed, not just covered. No uploads, runs entirely in your browser.',
        'keywords': 'redact pdf, black out pdf, censor pdf, permanent pdf redaction, secure pdf redaction free',
        'bullets': [
            'Click and drag to black out any area on a page',
            'Add custom text notes anywhere on a page',
            'Pages with a redaction are rebuilt from a flattened image, so the original text is actually gone',
            'Works across multi-page documents, untouched pages keep their original text',
            'No uploads, your file never leaves your device',
        ],
        'body_text': "NilPDF Redact lets you black out sensitive text, numbers, or images on a PDF page, entirely inside your browser. Any page you mark is re-rendered locally at high resolution with the black boxes (and any notes on that page) permanently baked into the image, then rebuilt as a new page with no text layer, no hidden content, and nothing left over from the original. That means a redacted page can no longer be searched, selected, or copied, the content is genuinely gone, not just covered up. Pages you don't mark are left exactly as they were. Nothing is ever uploaded to a server.",
        'how_to_name': 'How to redact a PDF',
        'how_to_steps': [
            ('Open NilPDF Redact', 'Visit nilpdf.com and select the Redact tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Mark areas', 'Switch to Redact mode and drag boxes over sensitive content, or switch to Text mode to add notes.'),
            ('Apply', 'Click "Apply & Download". Pages with a redaction are flattened and rebuilt, then your PDF downloads automatically.'),
        ],
        'faq': [
            ('Is redacting a PDF really free?', 'Yes. Completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I redact them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Does redaction actually remove the underlying content?', 'Yes. Any page with a black box is re-rendered at high resolution with the box permanently baked in, then rebuilt as a brand new page containing only that image, nothing from the original page carries over. The text under a black box cannot be selected, copied, or extracted afterward.'),
            ('Will my redacted PDF still have selectable text?', "Not on the pages you redact. Redacting a page flattens it into an image, so text on that page is no longer selectable or searchable. Pages you don't redact keep their original, fully selectable text."),
        ],
        'related': [
            ('protect-pdf', 'Protect PDF'),
            ('remove-pdf-metadata', 'Remove Metadata'),
            ('watermark-pdf', 'Watermark PDF'),
        ],
    },
    {
        'slug': 'edit-pdf',
        'tool_id': 'edit',
        'title': 'Edit PDF Online Free: Add Text | NilPDF',
        'h1': 'Edit PDF: Add Text',
        'tagline': 'Click anywhere to write text onto a PDF page, free and private.',
        'description': 'Free online PDF editor. Click anywhere on a page to add text, no uploads, runs entirely in your browser.',
        'keywords': 'edit pdf, add text to pdf, write on pdf, pdf editor free online',
        'bullets': [
            'Click anywhere on a page to add a text note',
            'Works across multi-page documents',
            'Remove or move notes before saving',
            'No uploads, your file never leaves your device',
        ],
        'body_text': "NilPDF Edit lets you write text directly onto any page of a PDF, fill in a blank, add a comment, sign off with a note, all rendered and applied locally in your browser. Click where you want the text, type it, and it's placed on the page. Download the edited PDF when you're done. Nothing is ever uploaded to a server.",
        'how_to_name': 'How to add text to a PDF',
        'how_to_steps': [
            ('Open NilPDF Edit', 'Visit nilpdf.com and select the Edit tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Add text', 'Click anywhere on the page and type the text you want to add.'),
            ('Apply', 'Click "Apply & Download", your edited PDF downloads automatically.'),
        ],
        'faq': [
            ('Is editing a PDF really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I edit them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Can I edit existing text in the PDF?', "Not yet, NilPDF Edit adds new text on top of the page, it doesn't modify existing text in the document. To black out or replace existing content, use the Redact tool instead."),
        ],
        'related': [
            ('redact-pdf', 'Redact PDF'),
            ('fill-pdf-forms', 'Fill PDF Forms'),
        ],
    },
    {
        'slug': 'fill-pdf-forms',
        'tool_id': 'fillform',
        'title': 'Fill PDF Forms Online Free | NilPDF',
        'h1': 'Fill PDF Forms',
        'tagline': 'Fill in PDF form fields directly on the page, free and private.',
        'description': 'Free online PDF form filler. Fill in text fields, checkboxes, and radio buttons directly on the page, then optionally flatten the form. No uploads, runs entirely in your browser.',
        'keywords': 'fill pdf form, pdf form filler, fill in pdf online free, flatten pdf form',
        'bullets': [
            'Detects and highlights every fillable field on the page',
            'Fill text fields, checkboxes, and radio buttons directly on the page',
            'Values carry across every page of a multi-page form',
            'Optional flatten step bakes values in and locks the fields',
            'No uploads, your form data never leaves your device',
        ],
        'body_text': 'NilPDF Fill Forms scans a PDF for its fillable AcroForm fields and lets you complete them directly on the rendered page, entirely inside your browser. Text fields, checkboxes, and radio buttons all work the same way they would in a desktop PDF reader. When you\'re done, download the filled PDF as-is with fields still editable, or turn on Flatten to bake your entries permanently into the page and remove the interactive fields. Nothing is ever uploaded to a server.',
        'how_to_name': 'How to fill in a PDF form',
        'how_to_steps': [
            ('Open NilPDF Fill Forms', 'Visit nilpdf.com and select the Fill PDF Forms tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse. NilPDF detects the form\'s fillable fields automatically.'),
            ('Fill in the fields', 'Type into text fields, and check boxes or select radio buttons directly on the page.'),
            ('Apply', 'Optionally turn on Flatten, then click "Apply & Download", your filled PDF downloads automatically.'),
        ],
        'faq': [
            ('Is filling in a PDF form really free?', 'Yes, completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I fill them in?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('What does "Flatten" do?', 'Flattening bakes your entered values permanently into the page content and removes the interactive form fields, so the result can no longer be edited as a form. Leave it off if you want the filled PDF to stay editable.'),
            ('What if my PDF has no fillable fields?', 'NilPDF will tell you the file has no fillable form fields. Only PDFs with an actual AcroForm (interactive form fields) can be filled this way, a scanned or flat PDF has no fields to detect.'),
        ],
        'related': [
            ('edit-pdf', 'Edit PDF'),
            ('redact-pdf', 'Redact PDF'),
            ('fill-and-sign-pdf', 'Fill & Sign PDF'),
        ],
        'extra_json_ld': '''    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      "name": "NilPDF Fill PDF Forms",
      "url": "https://nilpdf.com/fill-pdf-forms/",
      "applicationCategory": "UtilitiesApplication",
      "operatingSystem": "Any (browser-based)",
      "browserRequirements": "Requires a modern browser with JavaScript enabled",
      "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    }
    </script>
''',
    },
    {
        'slug': 'protect-pdf',
        'tool_id': 'protect',
        'title': 'Protect PDF with a Password Online Free | NilPDF',
        'h1': 'Protect PDF with a Password',
        'tagline': 'Encrypt a PDF with AES-256 so only people who know the password can open it, free and private.',
        'description': 'Free online PDF password protector. Encrypt any PDF with strong, standards-compatible AES-256 encryption. No uploads, runs entirely in your browser.',
        'keywords': 'protect pdf, password protect pdf, encrypt pdf, add password to pdf, pdf encryption online free',
        'bullets': [
            'Strong, standards-compatible AES-256 encryption',
            'Show/hide toggle and a password strength indicator',
            'Replace the password on an already-protected PDF',
            'Preserves the original page quality and content',
            'No uploads, your file and password never leave your device',
        ],
        'body_text': 'NilPDF Protect encrypts a PDF with a password entirely inside your browser, using the same AES-256 standard supported by Adobe Acrobat and every major PDF reader. Type a password, confirm it, and the encrypted file downloads directly to you, nothing is ever sent anywhere to do it. If the PDF is already password-protected, enter the current password first and NilPDF will replace it with your new one. Because the encryption happens on your device and nothing is transmitted, logged, or retained, NilPDF has no way to recover a forgotten password, so keep it somewhere safe.',
        'how_to_name': 'How to password protect a PDF',
        'how_to_steps': [
            ('Open NilPDF Protect', 'Visit nilpdf.com and select the Protect PDF tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse. If it is already encrypted, enter its current password.'),
            ('Set a password', 'Type a new password and confirm it, use the show/hide toggle to check it and the strength indicator as a guide.'),
            ('Encrypt', 'Click "Protect & Download" and the encrypted PDF downloads automatically.'),
        ],
        'faq': [
            ('Is protecting a PDF really free?', 'Yes. Completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I protect them?', 'Yes. Your file and your password never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server, so there is nothing to upload, log, or retain.'),
            ('What encryption does NilPDF use?', 'AES-256, the strongest standard PDF encryption method, compatible with Adobe Acrobat and other major PDF readers.'),
            ('Can NilPDF recover my password if I forget it?', "No, and this isn't a limitation NilPDF can lift. The password is never sent anywhere or stored, so nobody, including NilPDF, can recover it. If you lose it, the file cannot be unlocked."),
            ('Can I change the password on a PDF that is already protected?', 'Yes. Enter the current password to open it, then set a new one. The new password fully replaces the old one.'),
        ],
        'related': [
            ('unlock-pdf', 'Unlock PDF'),
            ('redact-pdf', 'Redact PDF'),
            ('sign-pdf', 'Sign PDF'),
        ],
        'extra_json_ld': '''    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      "name": "NilPDF Protect PDF",
      "url": "https://nilpdf.com/protect-pdf/",
      "applicationCategory": "UtilitiesApplication",
      "operatingSystem": "Any (browser-based)",
      "browserRequirements": "Requires a modern browser with JavaScript enabled",
      "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    }
    </script>
''',
    },
    {
        'slug': 'unlock-pdf',
        'tool_id': 'unlock',
        'title': 'Unlock PDF: Remove Password Online Free | NilPDF',
        'h1': 'Unlock PDF',
        'tagline': 'Permanently remove password encryption from a PDF you have the password for, free and private.',
        'description': 'Free online PDF password remover. Permanently strip encryption from a PDF once you supply the correct password. No uploads, runs entirely in your browser. Cannot crack, guess, or bypass an unknown password.',
        'keywords': 'unlock pdf, remove pdf password, decrypt pdf, remove pdf encryption, pdf password remover free',
        'bullets': [
            'Supports common PDF encryption, including RC4, AES-128, and AES-256',
            'Produces a genuinely unencrypted file, not a temporary unlock',
            'Detects PDFs that were never password protected',
            'Requires the owner password to lift permission restrictions like print/copy locks',
            'No uploads, your file and password never leave your device',
        ],
        'body_text': "NilPDF Unlock permanently removes password encryption from a PDF, entirely inside your browser. Enter the file's password, and NilPDF rebuilds the document without any encryption at all, not a version that just skips the password prompt this one time. It supports the standard PDF encryption formats in use today, including the AES-256 encryption NilPDF's own Protect tool produces. Some protected PDFs use two passwords under the hood: a user password that only opens the file, and a separate owner password that also lifts restrictions on printing or copying. If those differ, NilPDF needs the owner password specifically before it will strip the restrictions, entering only the viewing password isn't enough. What NilPDF cannot do, under any circumstances, is discover, crack, or bypass a password it wasn't given, if you don't know the password, there is no workaround here.",
        'how_to_name': 'How to remove a password from a PDF',
        'how_to_steps': [
            ('Open NilPDF Unlock', 'Visit nilpdf.com and select the Unlock PDF tool.'),
            ('Upload your PDF', 'Drop your password-protected PDF or click Browse.'),
            ('Enter the password', 'Type the PDF\'s password, use the show/hide toggle to check it.'),
            ('Unlock', 'Click "Unlock & Download" and the unencrypted PDF downloads automatically.'),
        ],
        'faq': [
            ('Is unlocking a PDF really free?', 'Yes. Completely free, unlimited use, no account required.'),
            ('Are my PDF file and password safe when I unlock it?', 'Yes. Neither your file nor your password ever leaves your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server, so there is nothing to upload, log, or retain.'),
            ('Can NilPDF remove a password I don\'t know?', "No. NilPDF cannot discover, crack, guess, or bypass a password it wasn't given. This tool only removes encryption from a PDF you already have the correct password for."),
            ('What PDF encryption does this support?', 'The standard PDF Standard Security Handler formats: RC4 (40 and 128-bit) and AES (128 and 256-bit), including the AES-256 encryption produced by NilPDF\'s own Protect PDF tool.'),
            ('Why does it ask for an owner password instead of the one I have?', "Some PDFs have a separate owner password that controls permissions like printing or copying, distinct from the user password that just opens the file. If you only enter the user password, NilPDF can open the file but won't strip protections it isn't confident you're allowed to remove, the owner password is required for that."),
        ],
        'related': [
            ('protect-pdf', 'Protect PDF'),
            ('redact-pdf', 'Redact PDF'),
            ('repair-pdf', 'Repair PDF'),
        ],
        'extra_json_ld': '''    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      "name": "NilPDF Unlock PDF",
      "url": "https://nilpdf.com/unlock-pdf/",
      "applicationCategory": "UtilitiesApplication",
      "operatingSystem": "Any (browser-based)",
      "browserRequirements": "Requires a modern browser with JavaScript enabled",
      "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    }
    </script>
''',
    },
    {
        'slug': 'sign-pdf',
        'tool_id': 'sign',
        'title': 'Sign PDF Online Free | NilPDF',
        'h1': 'Sign PDF',
        'tagline': 'Draw, type, or upload a signature and place it on any page. Free and private.',
        'description': 'Free online PDF signer. Draw a signature, type your name, or upload an image, then place it on any page. No uploads, runs entirely in your browser. This creates a visual signature, not a certificate-based digital signature.',
        'keywords': 'sign pdf, pdf signature, esign pdf online free, add signature to pdf',
        'bullets': [
            'Draw a signature with your mouse or finger',
            'Type your name in several signature styles',
            'Upload a signature image instead',
            'Place, resize, duplicate, or remove signatures on any page',
            'No uploads, your signature never leaves your device',
        ],
        'body_text': 'NilPDF Sign lets you create a signature by drawing it, typing your name in a handwriting-style font, or uploading an image, then place it anywhere on any page of your PDF. Drag to reposition, drag the corner handle to resize, and use the duplicate button to reuse the same signature on other spots or pages. The result is a flattened PDF with the signature image permanently part of the page. This is a visual electronic signature, not a certificate-based digital signature, and NilPDF makes no guarantee that it meets the legal requirements for signing any particular document.',
        'how_to_name': 'How to sign a PDF',
        'how_to_steps': [
            ('Open NilPDF Sign', 'Visit nilpdf.com and select the Sign PDF tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Create a signature', 'Draw it, type your name, or upload an image.'),
            ('Place it on the page', 'Add it to the page, then drag to position and resize as needed.'),
            ('Apply', 'Click "Apply & Download" and your signed PDF downloads automatically.'),
        ],
        'faq': [
            ('Is signing a PDF really free?', 'Yes. Completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I sign them?', 'Yes. Your files never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('Is this a legally binding digital signature?', 'No. This creates a visual signature, a picture of a signature placed on the page. It is not a certificate-based digital signature, and NilPDF makes no guarantee that it meets the legal requirements for your document. Check what your use case requires before relying on it.'),
            ('Does NilPDF store my signature?', "Not unless you choose to. There is an optional \"remember this signature on this device\" setting that saves it in your browser's local storage for reuse. It is off by default and you can remove a saved signature at any time."),
            ('Can I sign a password-protected PDF?', 'Yes. Enter the password when prompted and NilPDF will decrypt the file locally before you sign it.'),
        ],
        'related': [
            ('edit-pdf', 'Edit PDF'),
            ('fill-pdf-forms', 'Fill PDF Forms'),
            ('protect-pdf', 'Protect PDF'),
            ('fill-and-sign-pdf', 'Fill & Sign PDF'),
        ],
        'extra_json_ld': '''    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      "name": "NilPDF Sign PDF",
      "url": "https://nilpdf.com/sign-pdf/",
      "applicationCategory": "UtilitiesApplication",
      "operatingSystem": "Any (browser-based)",
      "browserRequirements": "Requires a modern browser with JavaScript enabled",
      "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    }
    </script>
''',
    },
    {
        'slug': 'fill-and-sign-pdf',
        'tool_id': 'fillsign',
        'title': 'Fill & Sign PDF Online Free | NilPDF',
        'h1': 'Fill & Sign PDF',
        'tagline': 'Fill in form fields, write in blanks or dates, and sign, all in one pass. Free and private.',
        'description': 'Free online tool to fill in a PDF, write text anywhere on the page, and sign it, all in one workspace. No uploads, runs entirely in your browser.',
        'keywords': 'fill and sign pdf, fill in pdf and sign, pdf form fill sign online free, sign and date pdf',
        'bullets': [
            'Detects and fills real AcroForm fields automatically, if the PDF has them',
            'Click anywhere to write in a blank, a date, or a note, works on any PDF',
            'Draw, type, or upload a signature and place it on the page',
            'Optional flatten step locks in filled form fields',
            'No uploads, your file and signature never leave your device',
        ],
        'body_text': 'NilPDF Fill & Sign combines three steps that used to be three separate tools into one pass: if your PDF has real fillable fields, they\'re detected and highlighted automatically so you can type straight into them; anywhere else on the page, switch to Text mode and click to write in a blank, a date, or a note; then switch to Sign mode to draw, type, or upload a signature and drag it into place. One "Apply & Download" bakes everything in and downloads the finished PDF. Nothing is ever uploaded to a server, form detection, filling, writing, and signing all happen locally in your browser.',
        'how_to_name': 'How to fill in and sign a PDF',
        'how_to_steps': [
            ('Open NilPDF Fill & Sign', 'Visit nilpdf.com and select the Fill & Sign tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse. Fillable fields, if any, are detected automatically.'),
            ('Fill and write', 'Type into detected fields, and use Text mode to click anywhere else and add notes or dates.'),
            ('Sign', 'Switch to Sign mode, draw, type, or upload a signature, then drag it into position.'),
            ('Apply', 'Click "Apply & Download" and the finished PDF downloads automatically.'),
        ],
        'faq': [
            ('Is this really free?', 'Yes. Completely free, unlimited use, no account required.'),
            ('Are my PDF files safe when I use this?', 'Yes. Your file and your signature never leave your device. Everything runs in your browser using WebAssembly. NilPDF has no backend server.'),
            ('What if my PDF has no fillable form fields?', "That's fine, the Fields option only appears if NilPDF detects real AcroForm fields. On any other PDF you can still switch to Text mode and click anywhere to write in a blank or a date, then sign it."),
            ('Is the signature a legally binding digital signature?', 'No. It creates a visual signature, a picture of a signature placed on the page. It is not a certificate-based digital signature, and NilPDF makes no guarantee that it meets the legal requirements for your document.'),
            ('Can I use this on a password-protected PDF?', 'Yes. Enter the password when prompted and NilPDF will decrypt the file locally before you fill it in or sign it.'),
        ],
        'related': [
            ('fill-pdf-forms', 'Fill PDF Forms'),
            ('sign-pdf', 'Sign PDF'),
            ('edit-pdf', 'Edit PDF'),
        ],
        'extra_json_ld': '''    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      "name": "NilPDF Fill & Sign PDF",
      "url": "https://nilpdf.com/fill-and-sign-pdf/",
      "applicationCategory": "UtilitiesApplication",
      "operatingSystem": "Any (browser-based)",
      "browserRequirements": "Requires a modern browser with JavaScript enabled",
      "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    }
    </script>
''',
    },
]

DARK_THEME_TOKENS = (
    '--bg: #16181c; --card: #1e2126; --text: #ece9e2; --muted: #a3a9b0; --border: #33373d; '
    '--accent: #d6a355; --on-accent: #15181d; --vault: #6fb3a0; --vault-soft: #1c3530;'
)

GA_SNIPPET = '''    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-GH395FJ43L"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-GH395FJ43L');
    </script>
'''

PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
{ga_snippet}    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <meta name="keywords" content="{keywords}">
    <link rel="canonical" href="https://nilpdf.com/{slug}/">
    <meta property="og:title" content="{h1} | NilPDF">
    <meta property="og:description" content="{description}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://nilpdf.com/{slug}/">
    <meta property="og:image" content="https://nilpdf.com/assets/og-image.png">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{h1} | NilPDF">
    <meta name="twitter:image" content="https://nilpdf.com/assets/og-image.png">
    <link rel="icon" href="https://nilpdf.com/assets/icon.svg" type="image/svg+xml">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Public+Sans:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "HowTo",
      "name": "{how_to_name}",
      "description": "{description}",
      "tool": {{"@type": "HowToTool", "name": "NilPDF"}},
      "step": {how_to_steps_json}
    }}
    </script>
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "FAQPage",
      "mainEntity": {faq_json}
    }}
    </script>
{extra_json_ld}    <script>
        /* Match the theme the visitor already picked on the main app (stored under
           the same localStorage key), instead of always falling back to the OS
           preference. Runs before <body> paints to avoid a flash of the wrong theme. */
        (function() {{
            var saved = localStorage.getItem('theme');
            if (saved === 'dark' || saved === 'light') {{
                document.documentElement.setAttribute('data-theme', saved);
            }}
        }})();
    </script>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        :root {{
            --bg: #f3f2ee; --card: #ffffff; --text: #15181d; --muted: #565c64;
            --accent: #a8681f; --on-accent: #ffffff; --border: #dcdad3; --radius: 4px;
            --vault: #2f6b5c; --vault-soft: #dfeae6;
            --font-display: 'Fraunces', Georgia, 'Times New Roman', serif;
            --font-body: 'Public Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            --font-mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        }}
        @media (prefers-color-scheme: dark) {{
            :root:not([data-theme="light"]) {{ {dark_theme_tokens} }}
        }}
        :root[data-theme="dark"] {{ {dark_theme_tokens} }}
        body {{ font-family: var(--font-body);
                background: var(--bg); color: var(--text); line-height: 1.6; }}
        .container {{ max-width: 680px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
        .back {{ font-size: 0.85rem; color: var(--accent); text-decoration: none; display: inline-block; margin-bottom: 2rem; }}
        .back:hover {{ text-decoration: underline; }}
        .brand {{ font-family: var(--font-mono); font-size: 0.78rem; font-weight: 600; color: var(--accent);
                  letter-spacing: 0.06em; text-transform: uppercase;
                  text-decoration: none; display: block; margin-bottom: 0.5rem; }}
        h1 {{ font-family: var(--font-display); font-size: clamp(1.75rem, 5vw, 2.5rem); font-weight: 600;
              line-height: 1.2; margin-bottom: 0.75rem; }}
        .tagline {{ font-size: 1.1rem; color: var(--muted); margin-bottom: 2rem; }}
        .cta {{ display: inline-block; background: var(--accent); color: var(--on-accent); font-weight: 700;
                font-size: 1rem; padding: 0.85rem 2rem; border-radius: var(--radius);
                text-decoration: none; margin-bottom: 2.5rem; transition: opacity 0.15s; }}
        .cta:hover {{ opacity: 0.88; }}
        .bullets {{ list-style: none; display: grid; gap: 0.6rem; margin-bottom: 2.5rem; }}
        .bullets li {{ display: flex; align-items: flex-start; gap: 0.6rem; font-size: 0.95rem; }}
        .bullets li::before {{ content: "✓"; color: var(--accent); font-weight: 700; flex-shrink: 0; margin-top: 0.05em; }}
        .privacy-strip {{ background: var(--vault-soft); border: 1px solid var(--vault); border-radius: var(--radius);
                          padding: 1rem 1.25rem; font-size: 0.85rem; color: var(--text); margin-bottom: 2.5rem; }}
        .privacy-strip strong {{ color: var(--vault); }}
        footer {{ font-size: 0.8rem; color: var(--muted); border-top: 1px solid var(--border); padding-top: 1.5rem; }}
        footer a {{ color: var(--accent); text-decoration: none; }}
        .body-text {{ font-size: 0.95rem; color: var(--text); margin-bottom: 2rem; line-height: 1.7; }}
        .faq {{ margin-bottom: 2.5rem; }}
        .faq h2 {{ font-size: 1.1rem; font-weight: 700; margin-bottom: 1rem; }}
        .faq-item {{ margin-bottom: 1.25rem; }}
        .faq-item h3 {{ font-size: 0.95rem; font-weight: 600; margin-bottom: 0.3rem; }}
        .faq-item p {{ font-size: 0.9rem; color: var(--muted); line-height: 1.6; }}
        .related-tools {{ margin-bottom: 2rem; font-size: 0.85rem; }}
        .related-tools p {{ color: var(--muted); margin-bottom: 0.5rem; }}
        .related-tools a {{ color: var(--accent); text-decoration: none; margin-right: 1rem; }}
        .related-tools a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <a class="back" href="https://nilpdf.com/">← All PDF tools</a>
        <a class="brand" href="https://nilpdf.com/">NilPDF</a>
        <h1>{h1}</h1>
        <p class="tagline">{tagline}</p>
        <a class="cta" href="https://nilpdf.com/#{tool_id}">Use this tool free →</a>
        <ul class="bullets">
{bullet_items}
        </ul>
        <p class="body-text">{body_text}</p>
        <div class="privacy-strip">
            <strong>Your files stay on your device.</strong> They are processed entirely inside your browser using WebAssembly.
            Nothing is uploaded to any server. NilPDF has no backend, there is no server to send your files to.
        </div>
        <section class="faq">
            <h2>Frequently Asked Questions</h2>
{faq_items}
        </section>
        <nav class="related-tools">
            <p>Other free PDF tools:</p>
{related_items}
        </nav>
        <footer>
            <p>Part of <a href="https://nilpdf.com/">NilPDF</a>: 21 free PDF tools, zero uploads.</p>
        </footer>
    </div>
</body>
</html>
'''


# The second FAQ entry on every tool page is always "Are my files safe...?".
# Its visible answer is worded more conversationally than the terser one used
# in the FAQPage JSON-LD, so the two need to be tracked separately.
SAFE_ANSWER_HTML_INDEX = 1
SAFE_ANSWER_HTML = ('Your files never leave your device. All processing happens in your browser '
                     'using WebAssembly (Pyodide). NilPDF has no server, there is nothing to upload to.')


def build_how_to_json(steps):
    result = []
    for i, (name, text) in enumerate(steps, 1):
        result.append({
            "@type": "HowToStep",
            "position": i,
            "name": name,
            "text": text,
        })
    return json.dumps(result, indent=6, ensure_ascii=False)


def build_faq_json(faq):
    """Render FAQ entries with acceptedAnswer inlined on one line, matching the hand-authored pages."""
    entries = []
    for question, answer in faq:
        entries.append(
            '        {\n'
            '          "@type": "Question",\n'
            f'          "name": {json.dumps(question, ensure_ascii=False)},\n'
            f'          "acceptedAnswer": {{"@type": "Answer", "text": {json.dumps(answer, ensure_ascii=False)}}}\n'
            '        }'
        )
    return '[\n' + ',\n'.join(entries) + '\n      ]'


def build_faq_html(faq):
    items = []
    for i, (question, answer) in enumerate(faq):
        if i == SAFE_ANSWER_HTML_INDEX:
            answer = SAFE_ANSWER_HTML
        items.append(
            '            <div class="faq-item">\n'
            f'                <h3>{question}</h3>\n'
            f'                <p>{answer}</p>\n'
            '            </div>'
        )
    return '\n'.join(items)


def build_related_html(related):
    return '\n'.join(
        f'            <a href="https://nilpdf.com/{slug}/">{label}</a>'
        for slug, label in related
    )


def generate():
    base = os.path.dirname(os.path.abspath(__file__))
    for tool in TOOLS:
        slug = tool['slug']
        dir_path = os.path.join(base, slug)
        os.makedirs(dir_path, exist_ok=True)

        bullet_items = '\n'.join(
            f'            <li>{b}</li>' for b in tool['bullets']
        )
        how_to_steps_json = build_how_to_json(tool['how_to_steps'])

        html = PAGE_TEMPLATE.format(
            ga_snippet=GA_SNIPPET,
            dark_theme_tokens=DARK_THEME_TOKENS,
            title=tool['title'],
            h1=tool['h1'],
            tagline=tool['tagline'],
            description=tool['description'],
            keywords=tool['keywords'],
            slug=slug,
            tool_id=tool['tool_id'],
            bullet_items=bullet_items,
            body_text=tool['body_text'],
            how_to_name=tool['how_to_name'],
            how_to_steps_json=how_to_steps_json,
            faq_json=build_faq_json(tool['faq']),
            faq_items=build_faq_html(tool['faq']),
            related_items=build_related_html(tool['related']),
            extra_json_ld=tool.get('extra_json_ld', ''),
        )

        out = os.path.join(dir_path, 'index.html')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'  {slug}/index.html')

    print(f'\nGenerated {len(TOOLS)} landing pages.')


if __name__ == '__main__':
    generate()
