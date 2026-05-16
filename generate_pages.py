"""Generate SEO landing pages for each NilPDF tool."""
import os

TOOLS = [
    {
        'slug': 'merge-pdf',
        'tool_id': 'merge',
        'title': 'Merge PDF Files Free Online — NilPDF',
        'h1': 'Merge PDF Files',
        'tagline': 'Combine multiple PDFs into one file — instantly, privately, for free.',
        'description': 'Free online PDF merger. Combine multiple PDF files into one. No uploads, no account — runs entirely in your browser.',
        'keywords': 'merge pdf, combine pdf, join pdf files, merge pdf free online',
        'bullets': [
            'Drag and drop any number of PDFs in any order',
            'Reorder files before merging with a click',
            'Password-protected PDFs supported',
            'Files never leave your device — zero uploads',
        ],
        'how_to_name': 'How to merge PDF files',
        'how_to_steps': [
            ('Open NilPDF Merge', 'Visit nilpdf.com and select the Merge tool.'),
            ('Add your PDFs', 'Drag and drop your PDF files or click Browse to select them.'),
            ('Arrange order', 'Drag files into the order you want.'),
            ('Merge', 'Click "Merge Files" — the combined PDF downloads automatically.'),
        ],
    },
    {
        'slug': 'compress-pdf',
        'tool_id': 'compress',
        'title': 'Compress PDF Online Free — NilPDF',
        'h1': 'Compress PDF Online',
        'tagline': 'Reduce PDF file size without losing quality — free and private.',
        'description': 'Free online PDF compressor. Shrink PDF files for email or upload. No server uploads — runs entirely in your browser.',
        'keywords': 'compress pdf, reduce pdf size, shrink pdf, compress pdf free online',
        'bullets': [
            'Compresses images and removes redundant data',
            'Batch-compress multiple PDFs at once',
            'Shows before/after file size comparison',
            'No uploads — your files stay on your device',
        ],
        'how_to_name': 'How to compress a PDF',
        'how_to_steps': [
            ('Open NilPDF Compress', 'Visit nilpdf.com and select the Squeeze (Compress) tool.'),
            ('Select your PDF', 'Drop your PDF file or click Browse.'),
            ('Compress', 'Click "Optimize Size" — the smaller PDF downloads automatically.'),
        ],
    },
    {
        'slug': 'split-pdf',
        'tool_id': 'split',
        'title': 'Split PDF Online Free — NilPDF',
        'h1': 'Split PDF Online',
        'tagline': 'Extract pages or split a PDF into multiple files — free and private.',
        'description': 'Free online PDF splitter. Extract specific pages or split into separate files. No uploads — runs in your browser.',
        'keywords': 'split pdf, extract pdf pages, split pdf free online, pdf page extractor',
        'bullets': [
            'Extract any pages by number (e.g. 1-3, 5, 7-9)',
            'Split into separate files — downloads as ZIP',
            'Works with encrypted PDFs',
            'Zero uploads — all processing in your browser',
        ],
        'how_to_name': 'How to split a PDF',
        'how_to_steps': [
            ('Open NilPDF Split', 'Visit nilpdf.com and select the Split tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Enter pages', 'Type the page numbers or ranges you want to extract.'),
            ('Split', 'Click "Extract Pages" — your PDF downloads instantly.'),
        ],
    },
    {
        'slug': 'pdf-to-images',
        'tool_id': 'topng',
        'title': 'PDF to Images — Convert PDF to JPG/PNG Free — NilPDF',
        'h1': 'PDF to Images',
        'tagline': 'Convert every page of a PDF to JPG or PNG images — free, instant, private.',
        'description': 'Free online PDF to image converter. Export each page as JPG or PNG. No uploads — runs entirely in your browser.',
        'keywords': 'pdf to jpg, pdf to png, pdf to image, convert pdf to jpg free',
        'bullets': [
            'Converts every page to a separate image',
            'Choose JPG (smaller) or PNG (lossless)',
            'Downloads all images in a ZIP file',
            'Runs locally — no server, no uploads',
        ],
        'how_to_name': 'How to convert PDF to images',
        'how_to_steps': [
            ('Open NilPDF To Images', 'Visit nilpdf.com and select the "To Images" tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Choose format', 'Select JPG or PNG from the dropdown.'),
            ('Convert', 'Click "Convert to Images" — a ZIP of all pages downloads.'),
        ],
    },
    {
        'slug': 'images-to-pdf',
        'tool_id': 'topdf',
        'title': 'Images to PDF — Convert JPG/PNG to PDF Free — NilPDF',
        'h1': 'Images to PDF',
        'tagline': 'Combine JPG or PNG images into a single PDF — free and private.',
        'description': 'Free online image to PDF converter. Turn JPG and PNG files into a PDF. No uploads — runs entirely in your browser.',
        'keywords': 'jpg to pdf, images to pdf, png to pdf, convert images to pdf free',
        'bullets': [
            'Supports JPG and PNG in any combination',
            'Add multiple images — each becomes a page',
            'Maintains original image quality',
            'No cloud upload — all local processing',
        ],
        'how_to_name': 'How to convert images to PDF',
        'how_to_steps': [
            ('Open NilPDF From Images', 'Visit nilpdf.com and select the "From Images" tool.'),
            ('Add images', 'Drop your JPG/PNG files or click Browse.'),
            ('Create PDF', 'Click "Create PDF" — your PDF downloads immediately.'),
        ],
    },
    {
        'slug': 'rotate-pdf',
        'tool_id': 'rotate',
        'title': 'Rotate PDF Pages Online Free — NilPDF',
        'h1': 'Rotate PDF Pages',
        'tagline': 'Rotate any pages in a PDF by 90° or 180° — free and private.',
        'description': 'Free online PDF page rotator. Rotate specific pages or the entire document. No uploads — runs in your browser.',
        'keywords': 'rotate pdf, rotate pdf pages, fix pdf orientation, rotate pdf free online',
        'bullets': [
            'Rotate 90° clockwise, counter-clockwise, or 180°',
            'Rotate all pages or select specific ones',
            'Works with password-protected PDFs',
            'No file uploads — your PDF stays on your device',
        ],
        'how_to_name': 'How to rotate PDF pages',
        'how_to_steps': [
            ('Open NilPDF Rotate', 'Visit nilpdf.com and select the Rotate tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Set rotation', 'Choose angle and optionally enter specific page numbers.'),
            ('Rotate', 'Click "Rotate Pages" — your corrected PDF downloads.'),
        ],
    },
    {
        'slug': 'pdf-to-text',
        'tool_id': 'totext',
        'title': 'Extract Text from PDF Free Online — NilPDF',
        'h1': 'PDF to Text',
        'tagline': 'Extract all text content from any PDF — free, private, no uploads.',
        'description': 'Free online PDF text extractor. Copy all text from a PDF file. No server uploads — runs entirely in your browser.',
        'keywords': 'pdf to text, extract text from pdf, pdf text extractor, copy text from pdf',
        'bullets': [
            'Extracts all text from every page',
            'Preview extracted text directly in the browser',
            'Copy to clipboard or download as .txt file',
            'Zero uploads — processed locally on your device',
        ],
        'how_to_name': 'How to extract text from a PDF',
        'how_to_steps': [
            ('Open NilPDF To Text', 'Visit nilpdf.com and select the "To Text" tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Extract', 'Click "Extract Text" — preview and copy or download the result.'),
        ],
    },
    {
        'slug': 'watermark-pdf',
        'tool_id': 'watermark',
        'title': 'Add Watermark to PDF Free Online — NilPDF',
        'h1': 'Add Watermark to PDF',
        'tagline': 'Stamp a diagonal text watermark on any PDF — free and private.',
        'description': 'Free online PDF watermark tool. Add CONFIDENTIAL, DRAFT, or any custom text. No uploads — runs in your browser.',
        'keywords': 'watermark pdf, add watermark to pdf, pdf watermark online, stamp pdf',
        'bullets': [
            'Custom watermark text — any word or phrase',
            'Adjustable opacity (10%–80%)',
            'Diagonal placement across every page',
            'No cloud processing — runs in your browser',
        ],
        'how_to_name': 'How to add a watermark to a PDF',
        'how_to_steps': [
            ('Open NilPDF Watermark', 'Visit nilpdf.com and select the Watermark tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Enter text', 'Type your watermark text (e.g. CONFIDENTIAL) and set opacity.'),
            ('Apply', 'Click "Apply Watermark" — your watermarked PDF downloads.'),
        ],
    },
    {
        'slug': 'remove-pdf-pages',
        'tool_id': 'remove',
        'title': 'Remove Pages from PDF Free Online — NilPDF',
        'h1': 'Remove PDF Pages',
        'tagline': 'Delete unwanted pages from any PDF — free, instant, private.',
        'description': 'Free online PDF page remover. Delete specific pages from a PDF file. No uploads — runs entirely in your browser.',
        'keywords': 'remove pages from pdf, delete pdf pages, pdf page remover, remove page pdf free',
        'bullets': [
            'Remove any pages by number (e.g. 1, 3-5)',
            'Live preview shows which pages will be removed',
            'Works with encrypted PDFs',
            'Files never leave your browser — zero uploads',
        ],
        'how_to_name': 'How to remove pages from a PDF',
        'how_to_steps': [
            ('Open NilPDF Remove Pages', 'Visit nilpdf.com and select the Remove tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Enter pages', 'Type the page numbers you want to delete.'),
            ('Remove', 'Click "Remove Pages" — your trimmed PDF downloads.'),
        ],
    },
    {
        'slug': 'reorder-pdf-pages',
        'tool_id': 'reorder',
        'title': 'Reorder PDF Pages Online Free — NilPDF',
        'h1': 'Reorder PDF Pages',
        'tagline': 'Drag and drop to rearrange pages in any PDF — free and private.',
        'description': 'Free online PDF page reorder tool. Drag thumbnails to change page order. No uploads — runs in your browser.',
        'keywords': 'reorder pdf pages, rearrange pdf pages, change page order pdf, pdf reorder free',
        'bullets': [
            'Visual drag-and-drop thumbnails for every page',
            'Instantly see the new page order before saving',
            'Supports password-protected PDFs',
            'Local processing — no file uploads needed',
        ],
        'how_to_name': 'How to reorder PDF pages',
        'how_to_steps': [
            ('Open NilPDF Reorder', 'Visit nilpdf.com and select the Order tool.'),
            ('Upload your PDF', 'Drop your PDF or click "Load for Reordering".'),
            ('Drag pages', 'Drag the page thumbnails into the order you want.'),
            ('Save', 'Click "Save Reordered PDF" — your PDF downloads.'),
        ],
    },
    {
        'slug': 'add-page-numbers-pdf',
        'tool_id': 'pagenums',
        'title': 'Add Page Numbers to PDF Free Online — NilPDF',
        'h1': 'Add Page Numbers to PDF',
        'tagline': 'Stamp page numbers onto any PDF — choose position and starting number.',
        'description': 'Free online tool to add page numbers to PDF files. No uploads — runs entirely in your browser.',
        'keywords': 'add page numbers to pdf, pdf page numbering, number pages in pdf, pdf page numbers free',
        'bullets': [
            'Six placement options (bottom centre, corners, top)',
            'Custom starting number',
            'Works with encrypted PDFs',
            'Zero server uploads — runs locally in your browser',
        ],
        'how_to_name': 'How to add page numbers to a PDF',
        'how_to_steps': [
            ('Open NilPDF Page Numbers', 'Visit nilpdf.com and select the "Page #s" tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Configure', 'Choose position and starting number.'),
            ('Apply', 'Click "Add Page Numbers" — your numbered PDF downloads.'),
        ],
    },
    {
        'slug': 'remove-pdf-metadata',
        'tool_id': 'anonymize',
        'title': 'Remove PDF Metadata Online Free — NilPDF',
        'h1': 'Remove PDF Metadata',
        'tagline': 'Strip hidden author, title, and tracking data from any PDF — privately.',
        'description': 'Free online PDF metadata remover. Scrub author, title, creator, and all hidden data. No uploads — runs in your browser.',
        'keywords': 'remove pdf metadata, strip pdf metadata, pdf anonymizer, clean pdf metadata free',
        'bullets': [
            'Removes author, title, creator, subject, and all custom fields',
            'Batch-process multiple PDFs at once',
            'Protects your privacy before sharing documents',
            'No uploads — metadata never sent to any server',
        ],
        'how_to_name': 'How to remove PDF metadata',
        'how_to_steps': [
            ('Open NilPDF Scrub', 'Visit nilpdf.com and select the Scrub tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('Scrub', 'Click "Strip Identifiers" — your clean PDF downloads.'),
        ],
    },
    {
        'slug': 'inspect-pdf',
        'tool_id': 'inspect',
        'title': 'Inspect PDF Metadata Online Free — NilPDF',
        'h1': 'Inspect PDF',
        'tagline': 'View PDF metadata, page count, fonts, and document properties — instantly.',
        'description': 'Free online PDF inspector. See author, title, creator, creation date, page count, and embedded fonts. No uploads.',
        'keywords': 'inspect pdf, pdf metadata viewer, view pdf properties, pdf info online',
        'bullets': [
            'Shows author, title, creator, subject, creation date',
            'Lists page count and PDF version',
            'Displays embedded fonts',
            'Instant results — no uploads, no waiting',
        ],
        'how_to_name': 'How to inspect a PDF',
        'how_to_steps': [
            ('Open NilPDF Inspect', 'Visit nilpdf.com and select the Inspect tool.'),
            ('Upload your PDF', 'Drop your PDF or click Browse.'),
            ('View results', 'All metadata and document properties appear immediately.'),
        ],
    },
]

PAGE_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <meta name="keywords" content="{keywords}">
    <link rel="canonical" href="https://nilpdf.com/{slug}/">
    <meta property="og:title" content="{h1} — NilPDF">
    <meta property="og:description" content="{description}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://nilpdf.com/{slug}/">
    <meta property="og:image" content="https://nilpdf.com/assets/og-image.png">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{h1} — NilPDF">
    <meta name="twitter:image" content="https://nilpdf.com/assets/og-image.png">
    <link rel="icon" href="https://nilpdf.com/assets/icon.svg" type="image/svg+xml">
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
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        :root {{
            --bg: #f8fafc; --card: #ffffff; --text: #0f172a; --muted: #64748b;
            --accent: #3b82f6; --border: #e2e8f0; --radius: 10px;
        }}
        @media (prefers-color-scheme: dark) {{
            :root {{ --bg: #0f172a; --card: #1e293b; --text: #f8fafc; --muted: #94a3b8; --border: #334155; }}
        }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                background: var(--bg); color: var(--text); line-height: 1.6; }}
        .container {{ max-width: 680px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
        .back {{ font-size: 0.85rem; color: var(--accent); text-decoration: none; display: inline-block; margin-bottom: 2rem; }}
        .back:hover {{ text-decoration: underline; }}
        .brand {{ font-size: 0.9rem; font-weight: 700; color: var(--accent); letter-spacing: 0.05em;
                  text-decoration: none; display: block; margin-bottom: 0.5rem; }}
        h1 {{ font-size: clamp(1.75rem, 5vw, 2.5rem); font-weight: 800; line-height: 1.2; margin-bottom: 0.75rem; }}
        .tagline {{ font-size: 1.1rem; color: var(--muted); margin-bottom: 2rem; }}
        .cta {{ display: inline-block; background: var(--accent); color: #fff; font-weight: 700;
                font-size: 1rem; padding: 0.85rem 2rem; border-radius: var(--radius);
                text-decoration: none; margin-bottom: 2.5rem; transition: opacity 0.15s; }}
        .cta:hover {{ opacity: 0.88; }}
        .bullets {{ list-style: none; display: grid; gap: 0.6rem; margin-bottom: 2.5rem; }}
        .bullets li {{ display: flex; align-items: flex-start; gap: 0.6rem; font-size: 0.95rem; }}
        .bullets li::before {{ content: "✓"; color: var(--accent); font-weight: 700; flex-shrink: 0; margin-top: 0.05em; }}
        .privacy-strip {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
                          padding: 1rem 1.25rem; font-size: 0.85rem; color: var(--muted); margin-bottom: 2.5rem; }}
        .privacy-strip strong {{ color: var(--text); }}
        footer {{ font-size: 0.8rem; color: var(--muted); border-top: 1px solid var(--border); padding-top: 1.5rem; }}
        footer a {{ color: var(--accent); text-decoration: none; }}
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
        <div class="privacy-strip">
            <strong>100% private.</strong> Your files are processed entirely inside your browser using WebAssembly.
            Nothing is uploaded to any server. NilPDF has no backend — there is no server to send your files to.
        </div>
        <footer>
            <p>Part of <a href="https://nilpdf.com/">NilPDF</a> — 13 free PDF tools, zero uploads.</p>
        </footer>
    </div>
</body>
</html>
'''


def build_how_to_json(steps):
    import json
    result = []
    for i, (name, text) in enumerate(steps, 1):
        result.append({
            "@type": "HowToStep",
            "position": i,
            "name": name,
            "text": text,
        })
    return json.dumps(result, indent=6)


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
            title=tool['title'],
            h1=tool['h1'],
            tagline=tool['tagline'],
            description=tool['description'],
            keywords=tool['keywords'],
            slug=slug,
            tool_id=tool['tool_id'],
            bullet_items=bullet_items,
            how_to_name=tool['how_to_name'],
            how_to_steps_json=how_to_steps_json,
        )

        out = os.path.join(dir_path, 'index.html')
        with open(out, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'  {slug}/index.html')

    print(f'\nGenerated {len(TOOLS)} landing pages.')


if __name__ == '__main__':
    generate()
