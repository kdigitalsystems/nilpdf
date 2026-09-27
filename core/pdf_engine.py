import io
import zipfile
from pypdf import PdfWriter, PdfReader

def _ensure_py(data):
    """Handles both Browser (Pyodide) and Native Python (CI) inputs."""
    return data.to_py() if hasattr(data, 'to_py') else data

def _open_pdf(buf):
    """Open a PdfReader without decrypting it. Falls back to strict=False on parse error."""
    try:
        return PdfReader(io.BytesIO(buf), strict=True)
    except Exception:
        return PdfReader(io.BytesIO(buf), strict=False)

def _open_reader(buf, password=""):
    """Open a PdfReader, decrypting with password if needed."""
    reader = _open_pdf(buf)
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


# ── Shared page-overlay helper (used by Edit, Sign, and Fill & Sign) ───────

def _draw_overlay(w, h, redacts=(), texts=(), signatures=()):
    """Draw redaction boxes, text notes, and/or signature images onto a blank
    page-sized reportlab canvas. Returns the resulting overlay page (from a
    fresh PdfReader) if anything was actually drawn, or None if every item
    was empty or failed to decode — callers should skip merging in that case
    rather than reading pages[0] of a reportlab canvas with zero pages, which
    is what save() produces when nothing was drawn on it.

    Each item is drawn independently and a malformed one (non-numeric
    coordinates, for example) is skipped rather than raised, the same way an
    undecodable signature image already was — one bad item from a large batch
    shouldn't take down the whole page.
    """
    import base64
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.colors import black
    from reportlab.lib.utils import ImageReader

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(w, h))
    drawn_any = False

    for edit in redacts:
        try:
            c.setFillColor(black)
            c.rect(float(edit.get("x", 0)), float(edit.get("y", 0)),
                   float(edit.get("width", 0)), float(edit.get("height", 0)),
                   stroke=0, fill=1)
            drawn_any = True
        except Exception:
            continue

    for edit in texts:
        try:
            size = float(edit.get("size") or 12)
            c.setFillColor(black)
            c.setFont("Helvetica", size)
            c.drawString(float(edit.get("x", 0)), float(edit.get("y", 0)), str(edit.get("text", "")))
            drawn_any = True
        except Exception:
            continue

    for sig in signatures:
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

    if not drawn_any:
        return None
    c.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def _merge_overlay(page, overlay_page):
    try:
        page.merge_page(overlay_page, over=True)
    except TypeError:
        page.merge_page(overlay_page)  # older pypdf without `over` param


def _clean_field_values(values):
    """Coerce a None field value to an empty string before handing it to
    pypdf, which otherwise stringifies it to the literal text "None" and
    bakes that into the field's appearance instead of leaving it blank.
    """
    return {k: ("" if v is None else v) for k, v in values.items()}


def _flatten_form_fields(writer):
    """Remove the interactive AcroForm and widget annotations after their
    filled appearances have already been baked in by
    update_page_form_field_values(flatten=True), leaving a non-interactive PDF.
    """
    from pypdf.generic import NameObject, ArrayObject

    for page in writer.pages:
        if "/Annots" in page:
            kept = [a for a in page["/Annots"] if a.get_object().get("/Subtype") != "/Widget"]
            if kept:
                page[NameObject("/Annots")] = ArrayObject(kept)
            else:
                del page["/Annots"]
    writer._root_object.pop("/AcroForm", None)


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
        raise ValueError(f"Page(s) {out_of_range} don't exist: this PDF has {total_pages} page(s).")

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
                    f"Range {i + 1}: page(s) {out_of_range} don't exist, this PDF has {total_pages} page(s)."
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
    total_pages = len(reader.pages)
    order = list(_ensure_py(new_order))

    if not order:
        raise ValueError("No page order was provided.")
    out_of_range = [idx + 1 for idx in order if not (0 <= idx < total_pages)]
    if out_of_range:
        raise ValueError(f"Page(s) {out_of_range} don't exist, this PDF has {total_pages} page(s).")

    writer = PdfWriter()
    for idx in order:
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
    succeeded = 0
    used_names = {}
    def _unique(zip_name):
        # Two uploaded files can share a name (e.g. from different folders), which
        # would otherwise silently overwrite one output with the other in the zip.
        count = used_names.get(zip_name, 0)
        used_names[zip_name] = count + 1
        return zip_name if count == 0 else f"{zip_name.rsplit('.', 1)[0]}_{count}.{zip_name.rsplit('.', 1)[1]}"

    with zipfile.ZipFile(out_zip_stream, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, (name, buf) in enumerate(zip(names, buffers)):
            _post_progress(status_id, int(i / total * 90), f"Processing {name} ({i + 1}/{total})...")
            base_name = name.rsplit('.', 1)[0] if '.' in name else name
            try:
                if action == 'COMPRESS':
                    processed_bytes = process_compress(buf, status_id=status_id, password=password)
                    suffix = "_compressed.pdf"
                elif action == 'ANONYMIZE':
                    processed_bytes = process_anonymize(buf, status_id=status_id, password=password)
                    suffix = "_metadata_removed.pdf"
                else:
                    processed_bytes = buf
                    suffix = "_processed.pdf"
                zf.writestr(_unique(f"{base_name}{suffix}"), processed_bytes)
                succeeded += 1
            except Exception as exc:
                # One bad file (wrong password, corrupt PDF) shouldn't lose every
                # already-processed file in the batch — note the failure inside
                # the zip and keep going instead of letting the exception escape
                # and discard the whole in-progress archive.
                zf.writestr(_unique(f"{base_name}_FAILED.txt"), f"Could not process \"{name}\": {exc}")

    if succeeded == 0:
        raise ValueError(
            "None of the selected files could be processed. "
            "If any are password-protected, check that the password entered is correct."
        )

    return out_zip_stream.getvalue()


# ── New tools (Part 3) ─────────────────────────────────────────────────────

def process_rotate(js_buf, degrees, page_indices, status_id="", password=""):
    """Rotate specific pages (or all pages if page_indices is empty)."""
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    total = len(reader.pages)
    indices_set = set(_ensure_py(page_indices))
    rotate_all = len(indices_set) == 0

    if not rotate_all:
        out_of_range = sorted(idx + 1 for idx in indices_set if not (0 <= idx < total))
        if out_of_range:
            raise ValueError(f"Page(s) {out_of_range} don't exist, this PDF has {total} page(s).")

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
        raise ValueError(f"Page(s) {out_of_range} don't exist: this PDF has {total} page(s).")

    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i not in indices_to_remove:
            writer.add_page(page)

    if len(writer.pages) == 0:
        raise ValueError("Cannot remove all pages, at least one page must remain.")

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
    reader = _open_reader(buf, password)
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
    _post_progress(status_id, 95, f"Finalising: {recovered} pages recovered, {skipped} skipped…")
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
        import reportlab  # noqa: F401 — presence check only; _draw_overlay imports what it needs
    except ImportError:
        raise ImportError("Edit requires reportlab. Please reload the page.")

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    total = len(writer.pages)

    edits_by_page = {}
    for edit in _ensure_py(edits) or []:
        edit = dict(edit)
        page_idx = int(edit.get("page", 0))
        edits_by_page.setdefault(page_idx, []).append(edit)

    for i in range(total):
        page_edits = edits_by_page.get(i)
        if page_edits:
            page = writer.pages[i]
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            redacts = [e for e in page_edits if e.get("type") == "redact"]
            texts = [e for e in page_edits if e.get("type") == "text"]
            overlay_page = _draw_overlay(w, h, redacts=redacts, texts=texts)
            if overlay_page is not None:
                _merge_overlay(page, overlay_page)

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

    images = {int(k): v for k, v in dict(_ensure_py(page_images) or {}).items()}

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
    try:
        import reportlab  # noqa: F401 — presence check only; _draw_overlay imports what it needs
    except ImportError:
        raise ImportError("Sign requires reportlab. Please reload the page.")

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    total = len(writer.pages)

    sigs_by_page = {}
    for sig in _ensure_py(signatures) or []:
        sig = dict(sig)
        page_idx = int(sig.get("page", 0))
        sigs_by_page.setdefault(page_idx, []).append(sig)

    for i in range(total):
        page_sigs = sigs_by_page.get(i)
        if page_sigs:
            page = writer.pages[i]
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            overlay_page = _draw_overlay(w, h, signatures=page_sigs)
            if overlay_page is not None:
                _merge_overlay(page, overlay_page)

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
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append(reader)

    if "/AcroForm" not in writer._root_object:
        raise ValueError("This PDF has no fillable form fields.")

    _post_progress(status_id, 20, "Filling form fields...")
    values = _clean_field_values(dict(_ensure_py(field_values) or {}))
    try:
        writer.update_page_form_field_values(None, values, auto_regenerate=not flatten, flatten=bool(flatten))
    except Exception as exc:
        raise ValueError(f"Could not fill form fields: {exc}")

    if flatten:
        _post_progress(status_id, 70, "Flattening form...")
        _flatten_form_fields(writer)

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
    _post_progress(status_id, 20, "Reading PDF...")
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    _stamp_producer(writer)
    _post_progress(status_id, 60, "Encrypting with AES-256...")
    writer.encrypt(user_password=new_password, owner_password=new_password, algorithm="AES-256")

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_unlock(js_buf, status_id="", password=""):
    """Permanently remove password encryption from a PDF, producing a
    genuinely unencrypted file — not a file that merely opens without a
    prompt for this one session.

    This only works with the correct password already in hand: NilPDF has
    no way to discover, crack, or otherwise bypass a password it wasn't
    given. Standard PDF encryption (RC4, AES-128, AES-256, including
    NilPDF's own Protect output) uses two passwords under the hood, a user
    password that just opens the file, and an owner password that also
    lifts permission restrictions like printing or copying. Supplying only
    the user password proves you can view the file, not that you're allowed
    to strip its restrictions, so if the two differ, the owner password is
    required before this will remove anything.
    """
    from pypdf import PasswordType

    reader = _open_pdf(_ensure_py(js_buf))

    if not reader.is_encrypted:
        raise ValueError("This PDF isn't password protected, there's nothing to unlock.")

    _post_progress(status_id, 15, "Checking password...")
    result = reader.decrypt(password or "")
    if result == PasswordType.NOT_DECRYPTED:
        raise ValueError("Incorrect password. Please enter the correct PDF password.")
    if result == PasswordType.USER_PASSWORD:
        raise ValueError(
            "That password only opens this PDF for viewing. It has a separate owner "
            "password restricting permissions like printing or copying, enter that "
            "owner password to remove the restrictions."
        )

    _post_progress(status_id, 40, "Removing encryption...")
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    total = max(len(writer.pages), 1)
    _post_progress(status_id, 80, f"Rebuilding {total} page(s)...")

    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def process_fill_and_sign(js_buf, field_values, edits, signatures, flatten=False, status_id="", password=""):
    """Combine form-filling, free text notes, and signature images in one pass.

    `field_values` maps AcroForm field name to value, same as process_fill_form
    — pass an empty dict if the PDF has no fields to fill, in which case the
    form-filling step (and its "no fillable fields" check) is skipped entirely
    rather than treated as an error, since this tool also serves flat PDFs with
    no form fields at all. `edits` is a list of
    {"page","type":"text","x","y","text","size"} dicts, the same shape
    process_edit takes. `signatures` is a list of
    {"page","x","y","width","height","image"} dicts, the same shape
    process_sign takes. `flatten` bakes filled field values into the page and
    removes the interactive AcroForm, same as process_fill_form; it only
    applies when `field_values` is non-empty. Text notes and signatures are
    always flattened into the page content — there's no non-flattened mode
    for those, matching process_edit and process_sign.
    """
    try:
        import reportlab  # noqa: F401 — presence check only; _draw_overlay imports what it needs
    except ImportError:
        raise ImportError("Fill & Sign requires reportlab. Please reload the page.")

    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append(reader)

    values = _clean_field_values(dict(_ensure_py(field_values) or {}))
    if values:
        if "/AcroForm" not in writer._root_object:
            raise ValueError("This PDF has no fillable form fields.")
        _post_progress(status_id, 15, "Filling form fields...")
        try:
            writer.update_page_form_field_values(None, values, auto_regenerate=not flatten, flatten=bool(flatten))
        except Exception as exc:
            raise ValueError(f"Could not fill form fields: {exc}")

        if flatten:
            _flatten_form_fields(writer)

    edits_by_page = {}
    for edit in _ensure_py(edits) or []:
        edit = dict(edit)
        edits_by_page.setdefault(int(edit.get("page", 0)), []).append(edit)

    sigs_by_page = {}
    for sig in _ensure_py(signatures) or []:
        sig = dict(sig)
        sigs_by_page.setdefault(int(sig.get("page", 0)), []).append(sig)

    total = len(writer.pages)
    for i in range(total):
        page_edits = edits_by_page.get(i) or []
        page_texts = [e for e in page_edits if e.get("type") == "text"]
        page_sigs = sigs_by_page.get(i) or []
        if page_texts or page_sigs:
            page = writer.pages[i]
            w = float(page.mediabox.width)
            h = float(page.mediabox.height)
            overlay_page = _draw_overlay(w, h, texts=page_texts, signatures=page_sigs)
            if overlay_page is not None:
                _merge_overlay(page, overlay_page)

        _post_progress(status_id, int((i + 1) / total * 90), f"Applying page {i + 1} of {total}...")

    _stamp_producer(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ── Redaction checker ──────────────────────────────────────────────────────
#
# Answers "is this PDF really redacted?" without needing the original. The
# common failure is a box drawn on top of text that is still in the file:
# invisible on screen, but copy, search and extraction all still find it. It
# looks for three ways text can survive:
#
#   covered_text          text painted first, then an opaque shape or image
#                         painted over it (black box, white-out, image patch)
#   unapplied_redaction   a /Redact annotation marked but never applied, or a
#                         dark annotation box sitting over live text
#   earlier_revision      text present in an earlier saved version of the file
#                         (incremental updates) but not in the final one
#
# Paint order is what separates a redaction box from a table background: a
# shape only hides text drawn *before* it. Semi-transparent shapes (highlighter
# style, fill alpha < 1) are ignored since the text shows through.

_FILL_OPS = {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
_CHAR_WIDTH_EM = 0.5          # average glyph advance, as a fraction of font size
_COVER_RATIO = 0.6            # a character counts as hidden if its sample point is inside


def _matmul(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return [a1 * a2 + b1 * c2, a1 * b2 + b1 * d2, c1 * a2 + d1 * c2,
            c1 * b2 + d1 * d2, e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2]


def _apply(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _inside(box, x, y, pad=0.5):
    return box[0] - pad <= x <= box[2] + pad and box[1] - pad <= y <= box[3] + pad


def _color_name(rgb):
    if rgb is None:
        return "unknown"
    lum = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return "black" if lum < 0.2 else "white" if lum > 0.9 else "coloured"


def _to_rgb(args):
    vals = [float(a) for a in args if hasattr(a, "__float__")]
    if len(vals) == 1:
        return (vals[0],) * 3
    if len(vals) == 3:
        return tuple(vals)
    if len(vals) == 4:
        c, m, y, k = vals
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return None


def _page_paint_events(page):
    """Walk a page's content in paint order and return (texts, covers).

    texts:  [(order, text, [(x, y) sample point per character], font_size)]
    covers: [(order, bbox, kind, colour)] for opaque filled shapes and images
    """
    texts, covers = [], []
    order = [0]
    state = {"fill": (0.0, 0.0, 0.0), "alpha": 1.0}
    stack = []
    path = []

    ext_gstates = {}
    xobjects = {}
    try:
        res = page.get("/Resources")
        res = res.get_object() if res is not None else {}
        gs = res.get("/ExtGState")
        ext_gstates = gs.get_object() if gs is not None else {}
        xo = res.get("/XObject")
        xobjects = xo.get_object() if xo is not None else {}
    except Exception:
        pass

    def before(op, args, cm, tm):
        order[0] += 1
        if op == b"q":
            stack.append(dict(state))
        elif op == b"Q":
            if stack:
                state.update(stack.pop())
        elif op in (b"rg", b"g", b"k", b"sc", b"scn"):
            rgb = _to_rgb(args)
            if rgb is not None:
                state["fill"] = rgb
        elif op == b"gs" and args:
            try:
                g = ext_gstates[args[0]].get_object()
                if "/ca" in g:
                    state["alpha"] = float(g["/ca"])
            except Exception:
                pass
        elif op == b"re" and len(args) == 4:
            x, y, w, h = (float(a) for a in args)
            path.append(_bbox([_apply(cm, x, y), _apply(cm, x + w, y), _apply(cm, x, y + h), _apply(cm, x + w, y + h)]))
        elif op in _FILL_OPS:
            if state["alpha"] >= 0.99:
                for box in path:
                    covers.append((order[0], box, "shape", _color_name(state["fill"])))
            path.clear()
        elif op in (b"n", b"S", b"s", b"W", b"W*"):
            if op != b"W" and op != b"W*":
                path.clear()
        elif op == b"Do" and args:
            try:
                xobj = xobjects[args[0]].get_object()
                if str(xobj.get("/Subtype")) == "/Image" and "/SMask" not in xobj and state["alpha"] >= 0.99:
                    box = _bbox([_apply(cm, 0, 0), _apply(cm, 1, 0), _apply(cm, 0, 1), _apply(cm, 1, 1)])
                    covers.append((order[0], box, "image", "image"))
            except Exception:
                pass

    def on_text(text, cm, tm, font_dict, font_size):
        text = text.rstrip("\n")
        if not text.strip():
            return
        order[0] += 1
        m = _matmul(tm, cm)
        scale_x = (m[0] ** 2 + m[1] ** 2) ** 0.5 or 1.0
        scale_y = (m[2] ** 2 + m[3] ** 2) ** 0.5 or 1.0
        size = float(font_size or 12)
        adv = size * _CHAR_WIDTH_EM
        mid = size * 0.35              # sample at roughly mid x-height
        points = [_apply(m, (i + 0.5) * adv / 1.0, mid) for i in range(len(text))]
        texts.append((order[0], text, points, size * scale_y))

    page.extract_text(visitor_operand_before=before, visitor_text=on_text)
    return texts, covers


def _hidden_spans(text, points, boxes):
    """Return the runs of characters whose sample points fall inside any box,
    widened to whole words so a report reads 'SECRET-123' not 'CRET-12'."""
    hidden = [any(_inside(b, x, y) for b in boxes) for (x, y) in points]
    if sum(hidden) < max(2, int(len(text) * 0.1)):
        return []
    spans, i = [], 0
    while i < len(text):
        if hidden[i]:
            j = i
            while j < len(text) and hidden[j]:
                j += 1
            while i > 0 and not text[i - 1].isspace():
                i -= 1
            while j < len(text) and not text[j].isspace():
                j += 1
            span = text[i:j].strip()
            if span and (not spans or spans[-1] != span):
                spans.append(span)
            i = j
        else:
            i += 1
    return spans


def _annotation_findings(page, texts, page_no):
    findings = []
    annots = page.get("/Annots")
    if annots is None:
        return findings
    for ref in annots.get_object():
        try:
            a = ref.get_object()
            sub = str(a.get("/Subtype"))
            rect = [float(v) for v in a.get("/Rect", [0, 0, 0, 0])]
            box = (min(rect[0], rect[2]), min(rect[1], rect[3]), max(rect[0], rect[2]), max(rect[1], rect[3]))
            colour = _to_rgb(a.get("/IC") or a.get("/C") or [])
            opaque = float(a.get("/CA", 1)) >= 0.99
        except Exception:
            continue
        if sub == "/Redact":
            kind, detail = "unapplied_redaction", "A redaction was marked here but never applied, so the text underneath is still in the file."
        elif sub in ("/Square", "/Highlight", "/Polygon", "/FreeText") and opaque and _color_name(colour) == "black":
            kind, detail = "unapplied_redaction", f"A black {sub[1:].lower()} annotation is drawn over this text; the text underneath is still in the file."
        else:
            continue
        spans = []
        for _order, text, points, _size in texts:
            spans += _hidden_spans(text, points, [box])
        findings.append({"kind": kind, "page": page_no, "text": " ... ".join(spans) if spans else "",
                         "detail": detail})
    return findings


def _earlier_revision_findings(buf, final_words):
    """Incremental saves append to a file rather than rewriting it, so every
    earlier version stays inside. Re-read each one and report words that were
    removed in a later version."""
    ends, start = [], 0
    while True:
        i = buf.find(b"%%EOF", start)
        if i < 0:
            break
        ends.append(i + 5)
        start = i + 5
    findings = []
    for rev, end in enumerate(ends[:-1], start=1):
        try:
            old = PdfReader(io.BytesIO(buf[:end]), strict=False)
            for page_no, pg in enumerate(old.pages, start=1):
                words = {w for w in (pg.extract_text() or "").split() if len(w) >= 3}
                gone = sorted(words - final_words)
                if gone:
                    findings.append({"kind": "earlier_revision", "page": page_no, "text": " ".join(gone[:40]),
                                     "detail": f"Present in saved version {rev} of {len(ends)}, removed later, but still in the file."})
        except Exception:
            continue
    return findings


def process_check_redaction(js_buf, status_id="", password=""):
    """Report text that is still in a PDF but hidden from view. Returns a JSON
    report as UTF-8 bytes. Nothing about the file is modified."""
    import json
    buf = bytes(_ensure_py(js_buf))
    reader = _open_reader(buf, password)
    total = max(len(reader.pages), 1)
    findings, final_words, invisible_pages = [], set(), []

    for page_no, page in enumerate(reader.pages, start=1):
        _post_progress(status_id, int(page_no / total * 80), f"Checking page {page_no} of {total}...")
        try:
            texts, covers = _page_paint_events(page)
        except Exception:
            continue
        for order, text, points, _size in texts:
            final_words |= {w for w in text.split() if len(w) >= 3}
            later = [(box, kind, colour) for (c_order, box, kind, colour) in covers if c_order > order]
            if not later:
                continue
            spans = _hidden_spans(text, points, [b for b, _k, _c in later])
            if spans:
                kinds = sorted({f"{c} {k}" if k == "shape" else "image" for _b, k, c in later})
                findings.append({"kind": "covered_text", "page": page_no, "text": " ... ".join(spans),
                                 "detail": f"Drawn over by a {', '.join(kinds)} but still in the file: it can be selected, copied and searched."})
        findings += _annotation_findings(page, texts, page_no)
        try:
            content = page.get_contents()
            if content is not None and b"3 Tr" in content.get_data():
                invisible_pages.append(page_no)
        except Exception:
            pass

    _post_progress(status_id, 90, "Checking earlier saved versions...")
    findings += _earlier_revision_findings(buf, final_words)

    meta = {}
    try:
        for key in ("/Title", "/Author", "/Subject", "/Keywords", "/Creator"):
            val = (reader.metadata or {}).get(key)
            if val and str(val).strip():
                meta[key[1:].lower()] = str(val)[:200]
    except Exception:
        pass

    report = {
        "pages": len(reader.pages),
        "hidden_text_found": bool(findings),
        "findings": findings[:200],
        "metadata": meta,
        "invisible_text_pages": invisible_pages,
        "limitations": [
            "Text that was never in the file as text, such as a scanned image with a black bar burned into it, "
            "can't be checked this way; its pixels are simply gone or simply there.",
            "Positions are estimated from average character widths, so a reported phrase can include a neighbouring "
            "word or miss one at the very edge of a box.",
        ],
    }
    _post_progress(status_id, 99, "Done.")
    return json.dumps(report, ensure_ascii=False).encode("utf-8")
