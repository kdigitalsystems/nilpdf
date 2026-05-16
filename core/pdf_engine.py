import io
import zipfile
from pypdf import PdfWriter, PdfReader

def _ensure_py(data):
    """Handles both Browser (Pyodide) and Native Python (CI) inputs."""
    return data.to_py() if hasattr(data, 'to_py') else data

def _open_reader(buf, password=""):
    """Open a PdfReader, decrypting with password if needed. Falls back to strict=False on parse error."""
    try:
        reader = PdfReader(io.BytesIO(buf), strict=True)
    except Exception:
        reader = PdfReader(io.BytesIO(buf), strict=False)
    if reader.is_encrypted:
        result = reader.decrypt(password or "")
        if result == 0:
            raise ValueError("Incorrect password. Please enter the correct PDF password.")
    return reader

def _post_progress(status_id, pct, msg):
    """Send progress update to JS main thread when running in Pyodide."""
    try:
        from js import reportProgress
        reportProgress(status_id, pct, msg)
    except Exception:
        pass

def _compress_images(writer, quality=75):
    """Best-effort re-compression of raw image XObjects to JPEG. Silent on failure."""
    try:
        from PIL import Image
        from pypdf.generic import NameObject, NumberObject
    except ImportError:
        return

    for page in writer.pages:
        try:
            resources = page.get("/Resources")
            if resources is None:
                continue
            if hasattr(resources, 'get_object'):
                resources = resources.get_object()
            xobjects = resources.get("/XObject")
            if xobjects is None:
                continue
            if hasattr(xobjects, 'get_object'):
                xobjects = xobjects.get_object()

            for key in list(xobjects.keys()):
                try:
                    xobj_ref = xobjects[key]
                    xobj = xobj_ref.get_object() if hasattr(xobj_ref, 'get_object') else xobj_ref

                    if str(xobj.get("/Subtype")) != "/Image":
                        continue

                    current_filter = xobj.get("/Filter")
                    if current_filter is not None:
                        if any(f in str(current_filter) for f in ("DCTDecode", "JPXDecode")):
                            continue

                    bpc = int(xobj.get("/BitsPerComponent", 8))
                    if bpc != 8:
                        continue

                    width = int(xobj["/Width"])
                    height = int(xobj["/Height"])
                    cs_str = str(xobj.get("/ColorSpace", "/DeviceRGB"))
                    if cs_str == "/DeviceRGB":
                        mode, bpp = "RGB", 3
                    elif cs_str == "/DeviceGray":
                        mode, bpp = "L", 1
                    else:
                        continue

                    raw = xobj.get_data()
                    if len(raw) != width * height * bpp:
                        continue

                    img = Image.frombytes(mode, (width, height), raw)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=quality, optimize=True)
                    jpeg_bytes = buf.getvalue()

                    if len(jpeg_bytes) >= len(raw):
                        continue

                    xobj._raw_data = jpeg_bytes
                    xobj._data = None
                    xobj[NameObject("/Filter")] = NameObject("/DCTDecode")
                    xobj[NameObject("/Length")] = NumberObject(len(jpeg_bytes))
                    xobj.pop(NameObject("/DecodeParms"), None)
                except Exception:
                    continue
        except Exception:
            continue


# ── Producer stamp (V8) ────────────────────────────────────────────────────

def _stamp_producer(writer):
    """Append NilPDF producer credit to output PDF metadata (except Anonymize)."""
    writer.add_metadata({'/Producer': 'NilPDF (nilpdf.com)'})


# ── Existing tools ─────────────────────────────────────────────────────────

def process_compress(js_buf, status_id="", password=""):
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    import gc
    total = len(writer.pages)
    for i, page in enumerate(writer.pages):
        try:
            page.compress_content_streams()
        except Exception:
            pass
        _post_progress(status_id, int((i + 1) / total * 70), f"Compressing page {i + 1} of {total}...")
        if i % 20 == 19:
            gc.collect()

    _post_progress(status_id, 75, "Re-compressing images...")
    _compress_images(writer)
    _stamp_producer(writer)

    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()


def process_anonymize(js_buf, status_id="", password=""):
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({
        "/Author": "", "/Creator": "", "/Producer": "NilPDF (Private)",
        "/Subject": "", "/Title": "", "/Keywords": "",
        "/CreationDate": "D:19700101000000Z", "/ModDate": "D:19700101000000Z"
    })
    try:
        writer._root_object.pop("/Metadata", None)
    except Exception:
        pass
    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()


def process_merge(js_buffers, status_id="", password=""):
    buffers = _ensure_py(js_buffers)
    merger = PdfWriter()
    total = len(buffers)
    for i, buf in enumerate(buffers):
        reader = _open_reader(buf, password)
        merger.append(reader)
        _post_progress(status_id, int((i + 1) / total * 90), f"Merged file {i + 1} of {total}...")
    _stamp_producer(merger)
    out_stream = io.BytesIO()
    merger.write(out_stream)
    return out_stream.getvalue()


def process_split(js_buf, page_indices, status_id="", password=""):
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    indices = _ensure_py(page_indices)
    total_pages = len(reader.pages)

    out_of_range = [idx + 1 for idx in indices if not (0 <= idx < total_pages)]
    if out_of_range:
        raise ValueError(f"Page(s) {out_of_range} don't exist — this PDF has {total_pages} page(s).")

    for idx in indices:
        writer.add_page(reader.pages[idx])
    _stamp_producer(writer)
    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()


def process_split_ranges(js_buf, ranges_list, status_id="", password=""):
    """Split PDF into multiple files — one per comma-separated range. Returns a ZIP."""
    reader = _open_reader(_ensure_py(js_buf), password)
    ranges = _ensure_py(ranges_list)
    total_pages = len(reader.pages)
    total_ranges = len(ranges)

    out_zip = io.BytesIO()
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, indices in enumerate(ranges):
            indices = list(indices)
            out_of_range = [idx + 1 for idx in indices if not (0 <= idx < total_pages)]
            if out_of_range:
                raise ValueError(
                    f"Range {i + 1}: page(s) {out_of_range} don't exist — this PDF has {total_pages} page(s)."
                )
            part_writer = PdfWriter()
            for idx in indices:
                part_writer.add_page(reader.pages[idx])
            _stamp_producer(part_writer)
            part_stream = io.BytesIO()
            part_writer.write(part_stream)
            zf.writestr(f"split_part_{i + 1}.pdf", part_stream.getvalue())
            _post_progress(status_id, int((i + 1) / total_ranges * 90), f"Split range {i + 1} of {total_ranges}...")

    return out_zip.getvalue()


def process_reorder(js_buf, new_order, status_id="", password=""):
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    for idx in _ensure_py(new_order):
        if 0 <= idx < len(reader.pages):
            writer.add_page(reader.pages[idx])
    _stamp_producer(writer)
    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()


def process_bulk(action, file_names, js_buffers, status_id="", password=""):
    names = _ensure_py(file_names)
    buffers = _ensure_py(js_buffers)
    total = len(names)

    out_zip_stream = io.BytesIO()
    with zipfile.ZipFile(out_zip_stream, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, (name, buf) in enumerate(zip(names, buffers)):
            _post_progress(status_id, int(i / total * 90), f"Processing {name} ({i + 1}/{total})...")
            if action == 'COMPRESS':
                processed_bytes = process_compress(buf, status_id=status_id, password=password)
                suffix = "_squeezed.pdf"
            elif action == 'ANONYMIZE':
                processed_bytes = process_anonymize(buf, status_id=status_id, password=password)
                suffix = "_scrubbed.pdf"
            else:
                processed_bytes = buf
                suffix = "_processed.pdf"

            base_name = name.rsplit('.', 1)[0] if '.' in name else name
            zf.writestr(f"{base_name}{suffix}", processed_bytes)

    return out_zip_stream.getvalue()


# ── New tools (Part 3) ─────────────────────────────────────────────────────

def process_rotate(js_buf, degrees, page_indices, status_id="", password=""):
    """Rotate specific pages (or all pages if page_indices is empty)."""
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    indices_set = set(_ensure_py(page_indices))
    rotate_all = len(indices_set) == 0
    total = len(reader.pages)

    for i, page in enumerate(reader.pages):
        if rotate_all or i in indices_set:
            page.rotate(int(degrees))
        writer.add_page(page)
        _post_progress(status_id, int((i + 1) / total * 90), f"Rotating page {i + 1} of {total}...")

    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_remove_pages(js_buf, page_indices, status_id="", password=""):
    """Remove the specified pages; keep everything else."""
    reader = _open_reader(_ensure_py(js_buf), password)
    indices_to_remove = set(_ensure_py(page_indices))
    total = len(reader.pages)

    out_of_range = [idx + 1 for idx in indices_to_remove if not (0 <= idx < total)]
    if out_of_range:
        raise ValueError(f"Page(s) {out_of_range} don't exist — this PDF has {total} page(s).")

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i not in indices_to_remove:
            writer.add_page(page)

    if len(writer.pages) == 0:
        raise ValueError("Cannot remove all pages — at least one page must remain.")

    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_extract_text(js_buf, status_id="", password=""):
    """Extract all text content from the PDF. Returns UTF-8 encoded bytes."""
    reader = _open_reader(_ensure_py(js_buf), password)
    total = len(reader.pages)
    parts = []

    for i, page in enumerate(reader.pages):
        _post_progress(status_id, int((i + 1) / total * 90), f"Extracting page {i + 1} of {total}...")
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"--- Page {i + 1} ---\n{text.strip()}")

    result = "\n\n".join(parts) if parts else "(No extractable text found in this PDF.)"
    return result.encode("utf-8")


def process_watermark(js_buf, text, opacity, status_id="", password=""):
    """Overlay a diagonal text watermark on every page."""
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.colors import Color
    except ImportError:
        raise ImportError("Watermark requires reportlab. Please reload the page.")

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    total = len(writer.pages)

    for i in range(total):
        page = writer.pages[i]
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)

        overlay_buf = io.BytesIO()
        c = rl_canvas.Canvas(overlay_buf, pagesize=(w, h))
        c.saveState()
        c.setFillColor(Color(0.45, 0.45, 0.45, alpha=float(opacity)))
        font_size = max(10.0, min(w, h) * 0.11)
        c.setFont("Helvetica-Bold", font_size)
        c.translate(w / 2, h / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, str(text))
        c.restoreState()
        c.save()
        overlay_buf.seek(0)

        overlay_page = PdfReader(overlay_buf).pages[0]
        try:
            page.merge_page(overlay_page, over=True)
        except TypeError:
            page.merge_page(overlay_page)  # older pypdf without `over` param
        _post_progress(status_id, int((i + 1) / total * 90), f"Watermarking page {i + 1} of {total}...")

    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_add_page_numbers(js_buf, position, start_num, status_id="", password=""):
    """Stamp a page number on every page."""
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.colors import black
    except ImportError:
        raise ImportError("Page numbers require reportlab. Please reload the page.")

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    total = len(writer.pages)
    start = int(start_num) if start_num else 1
    pos = str(position) if position else "bottom-center"
    MARGIN = 28
    FONT_SIZE = 11

    for i in range(total):
        page = writer.pages[i]
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)

        overlay_buf = io.BytesIO()
        c = rl_canvas.Canvas(overlay_buf, pagesize=(w, h))
        c.setFont("Helvetica", FONT_SIZE)
        c.setFillColor(black)

        label = str(start + i)
        y = MARGIN if "bottom" in pos else (h - MARGIN)

        if "center" in pos:
            c.drawCentredString(w / 2, y, label)
        elif "right" in pos:
            c.drawRightString(w - MARGIN, y, label)
        else:
            c.drawString(MARGIN, y, label)

        c.save()
        overlay_buf.seek(0)

        overlay_page = PdfReader(overlay_buf).pages[0]
        try:
            page.merge_page(overlay_page, over=True)
        except TypeError:
            page.merge_page(overlay_page)
        _post_progress(status_id, int((i + 1) / total * 90), f"Numbering page {i + 1} of {total}...")

    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _add_footer(writer, credit_text="Processed with NilPDF.com"):
    """Overlay a small grey credit line at the bottom-centre of every page."""
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.colors import Color
    except ImportError:
        return
    for page in writer.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(w, h))
        c.setFont("Helvetica", 8)
        c.setFillColor(Color(0.5, 0.5, 0.5, alpha=0.55))
        c.drawCentredString(w / 2, 10, str(credit_text))
        c.save()
        buf.seek(0)
        overlay = PdfReader(buf).pages[0]
        try:
            page.merge_page(overlay, over=True)
        except TypeError:
            page.merge_page(overlay)


def process_add_footer(js_buf, status_id="", password=""):
    """Add a small 'Processed with NilPDF.com' credit line to every page."""
    buf = _ensure_py(js_buf)
    reader = _open_reader(buf, password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    _post_progress(status_id, 50, "Adding footer credit…")
    _add_footer(writer)
    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_repair(js_buf, status_id="", password=""):
    """Attempt to recover pages from a corrupted or truncated PDF."""
    buf = _ensure_py(js_buf)
    _post_progress(status_id, 5, "Attempting to open PDF…")
    try:
        reader = PdfReader(io.BytesIO(buf), strict=True)
    except Exception:
        _post_progress(status_id, 15, "Strict parse failed — retrying with error recovery…")
        reader = PdfReader(io.BytesIO(buf), strict=False)
    if reader.is_encrypted:
        result = reader.decrypt(password or "")
        if result == 0:
            raise ValueError("Incorrect or missing password.")
    total = len(reader.pages)
    if total == 0:
        raise ValueError("PDF contains no pages.")
    writer = PdfWriter()
    recovered, skipped = 0, 0
    for i, page in enumerate(reader.pages):
        try:
            writer.add_page(page)
            recovered += 1
        except Exception:
            skipped += 1
        _post_progress(status_id, int(20 + (i + 1) / total * 70),
                       f"Recovered {recovered} of {total} pages…")
    if recovered == 0:
        raise ValueError("No readable pages could be recovered.")
    _post_progress(status_id, 95, f"Finalising — {recovered} pages recovered, {skipped} skipped…")
    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
