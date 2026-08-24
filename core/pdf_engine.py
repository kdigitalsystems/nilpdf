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

def _compress_images(writer, quality=75, status_id="", start_pct=62, end_pct=92):
    """Best-effort re-compression of raw image XObjects to JPEG. Silent on failure."""
    try:
        from PIL import Image
        from pypdf.generic import NameObject, NumberObject
    except ImportError:
        return

    pages = writer.pages
    total_pages = max(len(pages), 1)
    for page_num, page in enumerate(pages):
        try:
            resources = page.get("/Resources")
            if resources is not None:
                if hasattr(resources, 'get_object'):
                    resources = resources.get_object()
                xobjects = resources.get("/XObject")
                if xobjects is not None:
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
            pass
        _post_progress(status_id,
                       int(start_pct + (page_num + 1) / total_pages * (end_pct - start_pct)),
                       f"Optimising images on page {page_num + 1} of {total_pages}...")


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
        _post_progress(status_id, int((i + 1) / total * 60), f"Compressing page {i + 1} of {total}...")
        if i % 20 == 19:
            gc.collect()

    _compress_images(writer, status_id=status_id, start_pct=62, end_pct=92)
    _post_progress(status_id, 95, "Writing output...")
    _stamp_producer(writer)

    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()


_ANONYMIZE_FIELD_LABELS = {
    "/Title": "Title", "/Author": "Author", "/Subject": "Subject",
    "/Keywords": "Keywords", "/Creator": "Creator", "/Producer": "Producer",
    "/CreationDate": "Creation date", "/ModDate": "Modification date",
}


def process_anonymize(js_buf, status_id="", password=""):
    import json
    _post_progress(status_id, 5, "Reading PDF...")
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    total = max(len(reader.pages), 1)

    existing = dict(reader.metadata) if reader.metadata else {}
    removed_fields = [
        label for field, label in _ANONYMIZE_FIELD_LABELS.items()
        if str(existing.get(field, "") or "").strip()
    ]
    had_xmp = "/Metadata" in reader.trailer.get("/Root", {})

    for i, page in enumerate(reader.pages):
        writer.add_page(page)
        _post_progress(status_id, int(5 + (i + 1) / total * 80), f"Copying page {i + 1} of {total}...")
    _post_progress(status_id, 90, "Clearing metadata...")
    writer.add_metadata({
        "/Author": "", "/Creator": "", "/Producer": "NilPDF (Private)",
        "/Subject": "", "/Title": "", "/Keywords": "",
        "/CreationDate": "D:19700101000000Z", "/ModDate": "D:19700101000000Z"
    })
    try:
        writer._root_object.pop("/Metadata", None)
        if had_xmp:
            removed_fields.append("Embedded XMP metadata")
    except Exception:
        pass
    _post_progress(status_id, 96, "Writing output...")
    out_stream = io.BytesIO()
    writer.write(out_stream)
    _post_progress(status_id, 99, "__STATS__:" + json.dumps({
        "removedCount": len(removed_fields),
        "removedFields": removed_fields,
    }))
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
                suffix = "_compressed.pdf"
            elif action == 'ANONYMIZE':
                processed_bytes = process_anonymize(buf, status_id=status_id, password=password)
                suffix = "_metadata_removed.pdf"
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
    _post_progress(status_id, 2, "Reading file data…")
    buf = _ensure_py(js_buf)
    _post_progress(status_id, 5, "Parsing PDF structure (may take a moment for large files)…")
    try:
        reader = PdfReader(io.BytesIO(buf), strict=True)
    except Exception:
        _post_progress(status_id, 15, "Strict parse failed — retrying with lenient recovery…")
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
    import json
    _post_progress(status_id, 99, "__STATS__:" + json.dumps({"recovered": recovered, "skipped": skipped, "total": total}))
    return out.getvalue()


def process_edit(js_buf, edits, status_id="", password=""):
    """Apply redaction boxes and free-form text annotations to specific pages.

    `edits` is a list of dicts, each shaped like one of:
      {"page": int, "type": "redact", "x": float, "y": float, "width": float, "height": float}
      {"page": int, "type": "text", "x": float, "y": float, "text": str, "size": float}
    Coordinates are PDF points with the origin at the bottom-left of the page
    (reportlab's coordinate system) — the caller is responsible for converting
    from canvas/screen pixel coordinates before sending.
    """
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.colors import black
    except ImportError:
        raise ImportError("Edit requires reportlab. Please reload the page.")

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    total = len(writer.pages)

    edits_by_page = {}
    for edit in _ensure_py(edits):
        edit = dict(edit)
        page_idx = int(edit.get("page", 0))
        edits_by_page.setdefault(page_idx, []).append(edit)

    for i in range(total):
        page_edits = edits_by_page.get(i)
        if page_edits:
            page = writer.pages[i]
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)

            overlay_buf = io.BytesIO()
            c = rl_canvas.Canvas(overlay_buf, pagesize=(w, h))
            for edit in page_edits:
                if edit.get("type") == "redact":
                    c.setFillColor(black)
                    c.rect(float(edit.get("x", 0)), float(edit.get("y", 0)),
                           float(edit.get("width", 0)), float(edit.get("height", 0)),
                           stroke=0, fill=1)
                elif edit.get("type") == "text":
                    size = float(edit.get("size") or 12)
                    c.setFillColor(black)
                    c.setFont("Helvetica", size)
                    c.drawString(float(edit.get("x", 0)), float(edit.get("y", 0)), str(edit.get("text", "")))
            c.save()
            overlay_buf.seek(0)

            overlay_page = PdfReader(overlay_buf).pages[0]
            try:
                page.merge_page(overlay_page, over=True)
            except TypeError:
                page.merge_page(overlay_page)  # older pypdf without `over` param

        _post_progress(status_id, int((i + 1) / total * 90), f"Editing page {i + 1} of {total}...")

    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_redact(js_buf, page_images, status_id="", password=""):
    """Securely rebuild the pages that were redacted, discarding everything the
    original page carried.

    `page_images` maps a page index (int, or a numeric string since it may
    arrive as JSON) to a base64-encoded PNG: that page rendered at high
    resolution in the browser with the redaction boxes and any notes already
    composited into the pixels. For each page with an entry, this function
    creates a brand new page containing only that image and nothing else. It
    never copies the original page's text, annotations, form fields, images,
    or any other content into the output, so nothing that was under a black
    box can be recovered by extracting text or inspecting the file. Pages
    without an entry are copied through unchanged.

    If an image fails to decode, this raises rather than silently keeping the
    original (unredacted) page. Falling back would defeat the purpose of a
    redaction tool: better to fail loudly than to ship a file the user
    believes is redacted when it is not.
    """
    import base64
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.utils import ImageReader
    except ImportError:
        raise ImportError("Redact requires reportlab. Please reload the page.")

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    total = len(reader.pages)

    images = {int(k): v for k, v in dict(_ensure_py(page_images)).items()}

    for i in range(total):
        raw = images.get(i)
        if raw is not None:
            page = reader.pages[i]
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            raw_str = str(raw)
            if raw_str.startswith("data:") and "," in raw_str:
                raw_str = raw_str.split(",", 1)[1]
            try:
                img = ImageReader(io.BytesIO(base64.b64decode(raw_str)))
                flat_buf = io.BytesIO()
                c = rl_canvas.Canvas(flat_buf, pagesize=(w, h))
                c.drawImage(img, 0, 0, width=w, height=h, preserveAspectRatio=False)
                c.save()
                flat_buf.seek(0)
                writer.add_page(PdfReader(flat_buf).pages[0])
            except Exception as e:
                raise ValueError(f"Could not rebuild redacted page {i + 1}: {e}")
        else:
            writer.add_page(reader.pages[i])
        _post_progress(status_id, int((i + 1) / total * 90), f"Rebuilding page {i + 1} of {total}...")

    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_sign(js_buf, signatures, status_id="", password=""):
    """Stamp one or more signature/initial images onto specific pages, flattened
    permanently into the page content (a visual mark, not a certificate-based
    digital signature).

    `signatures` is a list of dicts:
      {"page": int, "x": float, "y": float, "width": float, "height": float, "image": str}
    `image` is a base64-encoded PNG (with or without a "data:image/png;base64,"
    prefix); transparency is preserved. Coordinates are PDF points with the
    origin at the bottom-left of the page. The caller converts from
    canvas/screen pixel coordinates before sending. A signature with
    unreadable image data is skipped rather than failing the whole document.
    """
    import base64
    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.utils import ImageReader
    except ImportError:
        raise ImportError("Sign requires reportlab. Please reload the page.")

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    total = len(writer.pages)

    sigs_by_page = {}
    for sig in _ensure_py(signatures):
        sig = dict(sig)
        page_idx = int(sig.get("page", 0))
        sigs_by_page.setdefault(page_idx, []).append(sig)

    for i in range(total):
        page_sigs = sigs_by_page.get(i)
        if page_sigs:
            page = writer.pages[i]
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)

            overlay_buf = io.BytesIO()
            c = rl_canvas.Canvas(overlay_buf, pagesize=(w, h))
            drawn_any = False
            for sig in page_sigs:
                raw = str(sig.get("image", ""))
                if raw.startswith("data:") and "," in raw:
                    raw = raw.split(",", 1)[1]
                try:
                    img = ImageReader(io.BytesIO(base64.b64decode(raw)))
                    c.drawImage(
                        img,
                        float(sig.get("x", 0)), float(sig.get("y", 0)),
                        width=float(sig.get("width", 100)), height=float(sig.get("height", 40)),
                        mask="auto", preserveAspectRatio=False,
                    )
                    drawn_any = True
                except Exception:
                    continue
            # A reportlab canvas with no successful drawing calls emits zero
            # pages on save() (a failed drawImage doesn't necessarily leave a
            # blank page behind). Skip the merge entirely rather than reading
            # pages[0] of an empty PDF.
            if drawn_any:
                c.save()
                overlay_buf.seek(0)
                overlay_page = PdfReader(overlay_buf).pages[0]
                try:
                    page.merge_page(overlay_page, over=True)
                except TypeError:
                    page.merge_page(overlay_page)  # older pypdf without `over` param

        _post_progress(status_id, int((i + 1) / total * 90), f"Signing page {i + 1} of {total}...")

    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_fill_form(js_buf, field_values, flatten=False, status_id="", password=""):
    """Fill AcroForm field values and optionally flatten to a non-interactive PDF.

    `field_values` maps field name (/T) to the value to set: a plain string for
    text/choice fields, or the "on" export value (e.g. "/Yes") for checkboxes
    and radio buttons. When `flatten` is True the filled appearance is baked
    into each page's content stream and the interactive widgets/AcroForm are
    removed entirely, so the result is no longer editable as a form.
    """
    from pypdf.generic import NameObject, ArrayObject

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append(reader)

    if "/AcroForm" not in writer._root_object:
        raise ValueError("This PDF has no fillable form fields.")

    _post_progress(status_id, 20, "Filling form fields...")
    values = dict(_ensure_py(field_values) or {})
    try:
        writer.update_page_form_field_values(None, values, auto_regenerate=not flatten, flatten=bool(flatten))
    except Exception as exc:
        raise ValueError(f"Could not fill form fields: {exc}")

    if flatten:
        _post_progress(status_id, 70, "Flattening form...")
        for page in writer.pages:
            if "/Annots" in page:
                kept = [a for a in page["/Annots"] if a.get_object().get("/Subtype") != "/Widget"]
                if kept:
                    page[NameObject("/Annots")] = ArrayObject(kept)
                else:
                    del page["/Annots"]
        writer._root_object.pop("/AcroForm", None)

    _post_progress(status_id, 95, "Writing output...")
    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_protect(js_buf, new_password, status_id="", password=""):
    """Encrypt a PDF with AES-256, or replace an existing password with a new one.

    `password` (if the source PDF is already encrypted) is used only to open
    it; `new_password` becomes both the user and owner password on the output,
    so anyone who can open the result can also do anything with it — NilPDF
    isn't in the business of enforcing print/copy restrictions.
    """
    new_password = str(new_password or "")
    if not new_password:
        raise ValueError("Enter a password to protect this PDF.")

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    total = max(len(writer.pages), 1)
    for i in range(total):
        _post_progress(status_id, int((i + 1) / total * 60), f"Copying page {i + 1} of {total}...")

    _stamp_producer(writer)
    _post_progress(status_id, 85, "Encrypting with AES-256...")
    writer.encrypt(user_password=new_password, owner_password=new_password, algorithm="AES-256")

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
