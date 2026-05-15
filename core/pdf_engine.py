import io
import zipfile
from pypdf import PdfWriter, PdfReader

def _ensure_py(data):
    """Handles both Browser (Pyodide) and Native Python (CI) inputs."""
    return data.to_py() if hasattr(data, 'to_py') else data

def _open_reader(buf, password=""):
    """Open a PdfReader, decrypting with password if needed."""
    reader = PdfReader(io.BytesIO(buf))
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
        pass  # Not running in Pyodide (e.g. unit tests)

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

                    # Skip already JPEG/JPEG2000 images — can't improve further
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
                        continue  # CMYK, indexed etc. — skip

                    raw = xobj.get_data()
                    if len(raw) != width * height * bpp:
                        continue  # Not plain decoded pixels

                    img = Image.frombytes(mode, (width, height), raw)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=quality, optimize=True)
                    jpeg_bytes = buf.getvalue()

                    if len(jpeg_bytes) >= len(raw):
                        continue  # No improvement, skip

                    xobj._raw_data = jpeg_bytes
                    xobj._data = None
                    xobj[NameObject("/Filter")] = NameObject("/DCTDecode")
                    xobj[NameObject("/Length")] = NumberObject(len(jpeg_bytes))
                    xobj.pop(NameObject("/DecodeParms"), None)
                except Exception:
                    continue
        except Exception:
            continue


def process_compress(js_buf, status_id="", password=""):
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    total = len(writer.pages)
    for i, page in enumerate(writer.pages):
        try:
            page.compress_content_streams()
        except Exception:
            pass  # Stream already optimised or unsupported — skip silently
        _post_progress(status_id, int((i + 1) / total * 70), f"Compressing page {i + 1} of {total}...")

    _post_progress(status_id, 75, "Re-compressing images...")
    _compress_images(writer)

    out_stream = io.BytesIO()
    writer.write(out_stream)
    return out_stream.getvalue()


def process_anonymize(js_buf, status_id="", password=""):
    reader = _open_reader(_ensure_py(js_buf), password)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_metadata({
        "/Author": "", "/Creator": "", "/Producer": "LocalPDF (Private)",
        "/Subject": "", "/Title": "", "/Keywords": "",
        "/CreationDate": "D:19700101000000Z", "/ModDate": "D:19700101000000Z"
    })
    # Remove XMP metadata via document catalog (avoids private _xmp_metadata attribute)
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
        raise ValueError(
            f"Page(s) {out_of_range} don't exist — this PDF has {total_pages} page(s)."
        )

    for idx in indices:
        writer.add_page(reader.pages[idx])
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
                processed_bytes = process_compress(buf, password=password)
                suffix = "_squeezed.pdf"
            elif action == 'ANONYMIZE':
                processed_bytes = process_anonymize(buf, password=password)
                suffix = "_scrubbed.pdf"
            else:
                processed_bytes = buf
                suffix = "_processed.pdf"

            base_name = name.rsplit('.', 1)[0] if '.' in name else name
            zf.writestr(f"{base_name}{suffix}", processed_bytes)

    return out_zip_stream.getvalue()
