import io
import unittest
import zipfile
from pypdf import PdfWriter, PdfReader

from core.pdf_engine import (
    process_merge,
    process_split,
    process_split_ranges,
    process_reorder,
    process_anonymize,
    process_compress,
    process_rotate,
    process_remove_pages,
    process_extract_text,
    process_watermark,
    process_add_page_numbers,
    process_bulk,
    process_repair,
    process_add_footer,
    process_edit,
    process_redact,
    process_sign,
    process_fill_form,
    process_protect,
    process_unlock,
    process_fill_and_sign,
    process_check_redaction,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def make_pdf(num_pages=1):
    """Return bytes of a minimal valid PDF with the given number of blank pages."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_pdf_with_text(text="Hello NilPDF"):
    """Return bytes of a PDF containing extractable text (via reportlab)."""
    from reportlab.pdfgen import canvas as rl_canvas
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf)
    c.drawString(72, 72, text)
    c.save()
    buf.seek(0)
    return buf.getvalue()


def make_encrypted_pdf(num_pages=1, password="secret"):
    """Return bytes of a password-protected PDF."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    writer.encrypt(password)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_encrypted_pdf_with_owner(num_pages=1, user_password="userpw", owner_password="ownerpw", algorithm=None):
    """Return bytes of a PDF with distinct user and owner passwords —
    opening it only proves the user password, not permission to strip
    restrictions, which requires the owner password."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    kwargs = {"algorithm": algorithm} if algorithm else {}
    writer.encrypt(user_password=user_password, owner_password=owner_password, **kwargs)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def make_form_pdf(password=None):
    """Return bytes of a PDF with a text field and a checkbox AcroForm field."""
    from reportlab.pdfgen import canvas as rl_canvas
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf)
    form = c.acroForm
    form.textfield(name="name_field", x=150, y=690, width=200, height=20, value="")
    form.checkbox(name="subscribe_cb", x=200, y=645, size=15, checked=False)
    c.showPage()
    c.save()
    buf.seek(0)

    if not password:
        return buf.getvalue()

    writer = PdfWriter()
    writer.append(PdfReader(buf))
    writer.encrypt(password)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def make_pdf_with_raw_image(width=300, height=200):
    """A page carrying an uncompressed (Flate, not JPEG) RGB image: the case
    Compress exists for, and the only one that reaches the Pillow path.
    Noise keeps JPEG from being larger than the raw pixels, which Compress
    would otherwise correctly skip."""
    import random
    from PIL import Image
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    rnd = random.Random(1)
    img = Image.new("RGB", (width, height))
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(width * height)])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(width + 100, height + 100))
    c.drawImage(ImageReader(img), 50, 50, width=width, height=height)
    c.save()
    return buf.getvalue()


def image_filters(data):
    xobjects = read_pdf(data).pages[0]["/Resources"]["/XObject"]
    return [str(xobjects[k].get_object().get("/Filter")) for k in xobjects]


def read_pdf(data):
    return PdfReader(io.BytesIO(data))


def producer_of(data):
    return read_pdf(data).metadata.get("/Producer", "")


def make_signature_png_base64():
    """Return a small transparent PNG (a signature stand-in) as a base64 string,
    with the same 'data:image/png;base64,' prefix the browser would send."""
    import base64
    from PIL import Image
    img = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def make_flat_page_png_base64(width=200, height=200):
    """Return an opaque PNG standing in for a browser-rendered, already-redacted
    page image (what renderFlattenedPage() would produce), as a base64 string."""
    import base64
    from PIL import Image
    img = Image.new("RGB", (width, height), (255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ── Merge ──────────────────────────────────────────────────────────────────

class TestMerge(unittest.TestCase):
    def test_merges_two_pdfs(self):
        result = process_merge([make_pdf(1), make_pdf(1)])
        self.assertEqual(len(read_pdf(result).pages), 2)

    def test_merges_three_pdfs(self):
        result = process_merge([make_pdf(2), make_pdf(3), make_pdf(1)])
        self.assertEqual(len(read_pdf(result).pages), 6)

    def test_stamps_producer(self):
        result = process_merge([make_pdf(1), make_pdf(1)])
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        enc = make_encrypted_pdf(password="correct")
        with self.assertRaises(ValueError):
            process_merge([enc], password="wrong")

    def test_correct_password_works(self):
        enc = make_encrypted_pdf(password="secret")
        result = process_merge([enc, make_pdf(1)], password="secret")
        self.assertEqual(len(read_pdf(result).pages), 2)


# ── Compress ───────────────────────────────────────────────────────────────

class TestCompress(unittest.TestCase):
    def test_recompresses_raw_image_to_jpeg(self):
        """Every other Compress test uses blank pages, which never reach the
        image path, so a crash on any real image went unnoticed."""
        original = make_pdf_with_raw_image()
        self.assertNotIn("DCTDecode", " ".join(image_filters(original)), "fixture must start uncompressed")
        result = process_compress(original)
        self.assertEqual(image_filters(result), ["/DCTDecode"])
        self.assertLess(len(result), len(original))

    def test_recompressed_image_still_decodes(self):
        """The JPEG must be a real, readable image of the original size, not
        just bytes with a JPEG label on them."""
        result = process_compress(make_pdf_with_raw_image(width=300, height=200))
        images = read_pdf(result).pages[0].images
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].image.size, (300, 200))

    def test_produces_valid_pdf(self):
        result = process_compress(make_pdf(3))
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_stamps_producer(self):
        result = process_compress(make_pdf(1))
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_compress(make_encrypted_pdf(password="x"), password="wrong")


# ── Split ──────────────────────────────────────────────────────────────────

class TestSplit(unittest.TestCase):
    def test_extracts_correct_pages(self):
        result = process_split(make_pdf(5), [0, 2, 4])
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_single_page(self):
        result = process_split(make_pdf(5), [3])
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError) as ctx:
            process_split(make_pdf(3), [0, 99])
        self.assertIn("don't exist", str(ctx.exception))

    def test_stamps_producer(self):
        result = process_split(make_pdf(3), [0, 1])
        self.assertIn("NilPDF", producer_of(result))


# ── Split into multiple files ──────────────────────────────────────────────

class TestSplitRanges(unittest.TestCase):
    def test_returns_zip(self):
        result = process_split_ranges(make_pdf(6), [[0, 1, 2], [3, 4, 5]])
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(result)))

    def test_zip_contains_correct_file_count(self):
        result = process_split_ranges(make_pdf(6), [[0, 1], [2, 3], [4, 5]])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            self.assertEqual(len(zf.namelist()), 3)

    def test_each_part_has_correct_page_count(self):
        result = process_split_ranges(make_pdf(4), [[0, 1], [2], [3]])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            page_counts = []
            for name in sorted(zf.namelist()):
                part = read_pdf(zf.read(name))
                page_counts.append(len(part.pages))
        self.assertEqual(page_counts, [2, 1, 1])

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            process_split_ranges(make_pdf(3), [[0, 1], [5, 6]])

    def test_parts_stamp_producer(self):
        result = process_split_ranges(make_pdf(2), [[0], [1]])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            for name in zf.namelist():
                meta = read_pdf(zf.read(name)).metadata
                self.assertIn("NilPDF", meta.get("/Producer", ""))


# ── Reorder ────────────────────────────────────────────────────────────────

class TestReorder(unittest.TestCase):
    def test_preserves_page_count(self):
        result = process_reorder(make_pdf(3), [2, 1, 0])
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_out_of_bounds_index_raises(self):
        with self.assertRaises(ValueError):
            process_reorder(make_pdf(3), [0, 1, 99])

    def test_empty_order_raises(self):
        with self.assertRaises(ValueError):
            process_reorder(make_pdf(3), [])

    def test_stamps_producer(self):
        result = process_reorder(make_pdf(3), [0, 1, 2])
        self.assertIn("NilPDF", producer_of(result))


# ── Anonymize ──────────────────────────────────────────────────────────────

class TestAnonymize(unittest.TestCase):
    def test_clears_author(self):
        result = process_anonymize(make_pdf(1))
        self.assertEqual(read_pdf(result).metadata.get("/Author"), "")

    def test_resets_creation_date(self):
        result = process_anonymize(make_pdf(1))
        self.assertEqual(read_pdf(result).metadata.get("/CreationDate"), "D:19700101000000Z")

    def test_producer_is_private_marker(self):
        result = process_anonymize(make_pdf(1))
        self.assertEqual(read_pdf(result).metadata.get("/Producer"), "NilPDF (Private)")

    def test_does_not_stamp_nilpdf_url(self):
        result = process_anonymize(make_pdf(1))
        self.assertNotIn("nilpdf.com", read_pdf(result).metadata.get("/Producer", ""))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_anonymize(make_encrypted_pdf(password="x"), password="wrong")

    def test_reports_removed_fields(self):
        import core.pdf_engine as engine
        import json
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.add_metadata({"/Title": "Secret Report", "/Author": "Jane Doe"})
        buf = io.BytesIO()
        writer.write(buf)

        captured = []
        original = engine._post_progress
        engine._post_progress = lambda status_id, pct, msg: captured.append(msg)
        try:
            process_anonymize(buf.getvalue(), status_id="test")
        finally:
            engine._post_progress = original

        stats_msgs = [m for m in captured if m.startswith("__STATS__:")]
        self.assertEqual(len(stats_msgs), 1)
        stats = json.loads(stats_msgs[0][len("__STATS__:"):])
        self.assertIn("Title", stats["removedFields"])
        self.assertIn("Author", stats["removedFields"])
        self.assertEqual(stats["removedCount"], len(stats["removedFields"]))

    def test_reports_only_fields_actually_present(self):
        import core.pdf_engine as engine
        import json
        captured = []
        original = engine._post_progress
        engine._post_progress = lambda status_id, pct, msg: captured.append(msg)
        try:
            process_anonymize(make_pdf(1), status_id="test")
        finally:
            engine._post_progress = original
        stats_msg = next(m for m in captured if m.startswith("__STATS__:"))
        stats = json.loads(stats_msg[len("__STATS__:"):])
        # A freshly-written blank PDF has no Title/Author/etc, only a default Producer.
        self.assertNotIn("Title", stats["removedFields"])
        self.assertNotIn("Author", stats["removedFields"])


# ── Rotate ─────────────────────────────────────────────────────────────────

class TestRotate(unittest.TestCase):
    def test_all_pages_rotated(self):
        result = process_rotate(make_pdf(3), degrees=90, page_indices=[])
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_specific_pages_rotated(self):
        result = process_rotate(make_pdf(4), degrees=180, page_indices=[0, 2])
        self.assertEqual(len(read_pdf(result).pages), 4)

    def test_valid_rotation_values(self):
        for deg in [90, 180, 270]:
            result = process_rotate(make_pdf(1), degrees=deg, page_indices=[])
            self.assertIsNotNone(result)

    def test_stamps_producer(self):
        result = process_rotate(make_pdf(1), degrees=90, page_indices=[])
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_rotate(make_encrypted_pdf(password="x"), degrees=90, page_indices=[], password="wrong")

    def test_out_of_range_index_raises_rather_than_silently_doing_nothing(self):
        with self.assertRaises(ValueError):
            process_rotate(make_pdf(3), degrees=90, page_indices=[99])


# ── Remove pages ───────────────────────────────────────────────────────────

class TestRemovePages(unittest.TestCase):
    def test_removes_specified_pages(self):
        result = process_remove_pages(make_pdf(5), [0, 4])
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_removes_single_page(self):
        result = process_remove_pages(make_pdf(3), [1])
        self.assertEqual(len(read_pdf(result).pages), 2)

    def test_cannot_remove_all_pages(self):
        with self.assertRaises(ValueError) as ctx:
            process_remove_pages(make_pdf(2), [0, 1])
        self.assertIn("Cannot remove all", str(ctx.exception))

    def test_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            process_remove_pages(make_pdf(3), [0, 99])

    def test_stamps_producer(self):
        result = process_remove_pages(make_pdf(3), [0])
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_remove_pages(make_encrypted_pdf(2, "x"), [0], password="wrong")


# ── Extract text ───────────────────────────────────────────────────────────

class TestExtractText(unittest.TestCase):
    def test_returns_bytes(self):
        result = process_extract_text(make_pdf(1))
        self.assertIsInstance(result, bytes)

    def test_blank_pdf_returns_no_text_message(self):
        result = process_extract_text(make_pdf(1))
        self.assertIn("No extractable text", result.decode("utf-8"))

    def test_extracts_actual_text(self):
        pdf = make_pdf_with_text("Hello NilPDF")
        result = process_extract_text(pdf)
        self.assertIn("Hello NilPDF", result.decode("utf-8"))

    def test_page_markers_present(self):
        pdf = make_pdf_with_text("test")
        result = process_extract_text(pdf)
        self.assertIn("Page 1", result.decode("utf-8"))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_extract_text(make_encrypted_pdf(password="x"), password="wrong")


# ── Watermark ──────────────────────────────────────────────────────────────

class TestWatermark(unittest.TestCase):
    def test_produces_valid_pdf(self):
        result = process_watermark(make_pdf(2), text="DRAFT", opacity=0.3)
        self.assertEqual(len(read_pdf(result).pages), 2)

    def test_stamps_producer(self):
        result = process_watermark(make_pdf(1), text="CONFIDENTIAL", opacity=0.3)
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_watermark(make_encrypted_pdf(password="x"), text="W", opacity=0.3, password="wrong")


# ── Add page numbers ───────────────────────────────────────────────────────

class TestAddPageNumbers(unittest.TestCase):
    def test_produces_valid_pdf(self):
        result = process_add_page_numbers(make_pdf(3), position="bottom-center", start_num=1)
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_all_positions(self):
        positions = ["bottom-center", "bottom-right", "bottom-left",
                     "top-center", "top-right", "top-left"]
        for pos in positions:
            result = process_add_page_numbers(make_pdf(1), position=pos, start_num=1)
            self.assertIsNotNone(result, msg=f"Failed for position: {pos}")

    def test_custom_start_number(self):
        result = process_add_page_numbers(make_pdf(2), position="bottom-center", start_num=5)
        self.assertEqual(len(read_pdf(result).pages), 2)

    def test_stamps_producer(self):
        result = process_add_page_numbers(make_pdf(1), position="bottom-center", start_num=1)
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_add_page_numbers(make_encrypted_pdf(password="x"), position="bottom-center", start_num=1, password="wrong")


# ── Bulk processing ────────────────────────────────────────────────────────

class TestBulk(unittest.TestCase):
    def test_bulk_compress_returns_zip(self):
        names = ["a.pdf", "b.pdf"]
        buffers = [make_pdf(1), make_pdf(2)]
        result = process_bulk("COMPRESS", names, buffers)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(result)))

    def test_bulk_compress_file_count(self):
        names = ["a.pdf", "b.pdf", "c.pdf"]
        buffers = [make_pdf(1)] * 3
        result = process_bulk("COMPRESS", names, buffers)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            self.assertEqual(len(zf.namelist()), 3)

    def test_bulk_anonymize_returns_zip(self):
        names = ["x.pdf", "y.pdf"]
        buffers = [make_pdf(1), make_pdf(1)]
        result = process_bulk("ANONYMIZE", names, buffers)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(result)))

    def test_bulk_anonymize_clears_metadata(self):
        names = ["x.pdf"]
        buffers = [make_pdf(1)]
        result = process_bulk("ANONYMIZE", names, buffers)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            part = read_pdf(zf.read(zf.namelist()[0]))
            self.assertEqual(part.metadata.get("/Author"), "")

    def test_bulk_output_filenames_use_suffix(self):
        names = ["report.pdf"]
        buffers = [make_pdf(1)]
        result = process_bulk("COMPRESS", names, buffers)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            self.assertIn("report_compressed.pdf", zf.namelist())

    def test_one_bad_file_does_not_lose_the_rest_of_the_batch(self):
        # A wrong-password file in the middle of the batch used to raise and
        # discard the entire in-progress zip, including files already
        # successfully processed before it.
        names = ["good1.pdf", "wrong-password.pdf", "good2.pdf"]
        buffers = [make_pdf(1), make_encrypted_pdf(password="secret"), make_pdf(1)]
        result = process_bulk("COMPRESS", names, buffers, password="not-the-password")
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names_in_zip = zf.namelist()
            self.assertIn("good1_compressed.pdf", names_in_zip)
            self.assertIn("good2_compressed.pdf", names_in_zip)
            self.assertIn("wrong-password_FAILED.txt", names_in_zip)

    def test_all_files_failing_raises(self):
        names = ["bad1.pdf", "bad2.pdf"]
        buffers = [make_encrypted_pdf(password="secret")] * 2
        with self.assertRaises(ValueError):
            process_bulk("COMPRESS", names, buffers, password="wrong")


# ── Repair ─────────────────────────────────────────────────────────────────

class TestRepair(unittest.TestCase):
    def test_repair_valid_pdf_preserves_page_count(self):
        result = process_repair(make_pdf(3))
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_repair_stamps_producer(self):
        result = process_repair(make_pdf(1))
        self.assertIn("NilPDF", producer_of(result))

    def test_repair_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_repair(make_encrypted_pdf(password="x"), password="wrong")

    def test_repair_correct_password_works(self):
        enc = make_encrypted_pdf(num_pages=2, password="abc")
        result = process_repair(enc, password="abc")
        self.assertEqual(len(read_pdf(result).pages), 2)

    def test_reports_recovered_and_skipped_counts(self):
        import core.pdf_engine as engine
        import json
        captured = []
        original = engine._post_progress
        engine._post_progress = lambda status_id, pct, msg: captured.append(msg)
        try:
            process_repair(make_pdf(3), status_id="test")
        finally:
            engine._post_progress = original
        stats_msgs = [m for m in captured if m.startswith("__STATS__:")]
        self.assertEqual(len(stats_msgs), 1)
        stats = json.loads(stats_msgs[0][len("__STATS__:"):])
        self.assertEqual(stats, {"recovered": 3, "skipped": 0, "total": 3})


# ── Add footer ─────────────────────────────────────────────────────────────

class TestAddFooter(unittest.TestCase):
    def test_footer_preserves_page_count(self):
        result = process_add_footer(make_pdf(2))
        self.assertEqual(len(read_pdf(result).pages), 2)

    def test_footer_stamps_producer(self):
        result = process_add_footer(make_pdf(1))
        self.assertIn("NilPDF", producer_of(result))

    def test_footer_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_add_footer(make_encrypted_pdf(password="x"), password="wrong")


# ── Edit (redaction + text overlay) ──────────────────────────────────────────

class TestEdit(unittest.TestCase):
    def test_redact_produces_valid_pdf(self):
        edits = [{"page": 0, "type": "redact", "x": 0, "y": 0, "width": 20, "height": 20}]
        result = process_edit(make_pdf(2), edits)
        self.assertEqual(len(read_pdf(result).pages), 2)

    def test_text_edit_produces_valid_pdf(self):
        edits = [{"page": 0, "type": "text", "x": 10, "y": 10, "text": "Hello", "size": 14}]
        result = process_edit(make_pdf(1), edits)
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_empty_edits_preserves_page_count(self):
        result = process_edit(make_pdf(3), [])
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_targets_only_specified_page(self):
        edits = [{"page": 2, "type": "redact", "x": 0, "y": 0, "width": 10, "height": 10}]
        result = process_edit(make_pdf(3), edits)
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_multiple_edits_same_page(self):
        edits = [
            {"page": 0, "type": "redact", "x": 0, "y": 0, "width": 10, "height": 10},
            {"page": 0, "type": "text", "x": 20, "y": 20, "text": "Note", "size": 10},
        ]
        result = process_edit(make_pdf(1), edits)
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_stamps_producer(self):
        result = process_edit(make_pdf(1), [])
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_edit(make_encrypted_pdf(password="x"), [], password="wrong")

    def test_correct_password_works(self):
        enc = make_encrypted_pdf(num_pages=2, password="secret")
        edits = [{"page": 1, "type": "text", "x": 5, "y": 5, "text": "X"}]
        result = process_edit(enc, edits, password="secret")
        self.assertEqual(len(read_pdf(result).pages), 2)


# ── Redact (secure: full-page rebuild, not a visual-only overlay) ────────────

class TestRedact(unittest.TestCase):
    def test_secret_string_not_extractable_after_redaction(self):
        secret = "SECRET-XK47-DO-NOT-SHARE"
        original = make_pdf_with_text(secret)
        self.assertIn(secret, read_pdf(original).pages[0].extract_text())  # sanity: it's really there first

        result = process_redact(original, {0: make_flat_page_png_base64()})

        self.assertNotIn(secret, read_pdf(result).pages[0].extract_text())
        self.assertNotIn(secret.encode(), result)  # not recoverable from the raw file bytes either

    def test_redacted_page_has_no_text_layer_at_all(self):
        original = make_pdf_with_text("Anything on this page should be gone")
        result = process_redact(original, {0: make_flat_page_png_base64()})
        self.assertEqual(read_pdf(result).pages[0].extract_text().strip(), "")

    def test_preserves_unaffected_pages(self):
        secret_page_0 = "KEEP-ME-VISIBLE-PAGE-0"
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(make_pdf_with_text(secret_page_0))))
        writer.append(PdfReader(io.BytesIO(make_pdf_with_text("redact this page instead"))))
        buf = io.BytesIO()
        writer.write(buf)
        original = buf.getvalue()

        result = process_redact(original, {1: make_flat_page_png_base64()})
        pages = read_pdf(result).pages
        self.assertEqual(len(pages), 2)
        self.assertIn(secret_page_0, pages[0].extract_text())  # untouched page keeps its real text
        self.assertNotIn("redact this page instead", pages[1].extract_text())

    def test_empty_page_images_preserves_everything(self):
        secret = "NOTHING-SHOULD-CHANGE-HERE"
        original = make_pdf_with_text(secret)
        result = process_redact(original, {})
        self.assertIn(secret, read_pdf(result).pages[0].extract_text())

    def test_output_page_count_matches_input(self):
        result = process_redact(make_pdf(3), {1: make_flat_page_png_base64()})
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_string_keys_are_accepted(self):
        # JSON round-tripping (JS -> worker -> Python) turns numeric dict keys into strings.
        result = process_redact(make_pdf(1), {"0": make_flat_page_png_base64()})
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_invalid_image_raises_instead_of_silently_keeping_original(self):
        # A redaction tool must fail loudly, not fall back to shipping the unredacted
        # page while the user believes it was removed.
        secret = "MUST-NOT-LEAK-ON-DECODE-FAILURE"
        original = make_pdf_with_text(secret)
        with self.assertRaises(ValueError):
            process_redact(original, {0: "not valid base64 image data!!"})

    def test_stamps_producer(self):
        result = process_redact(make_pdf(1), {})
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_redact(make_encrypted_pdf(password="x"), {}, password="wrong")

    def test_correct_password_works(self):
        enc = make_encrypted_pdf(num_pages=2, password="secret")
        result = process_redact(enc, {0: make_flat_page_png_base64()}, password="secret")
        self.assertEqual(len(read_pdf(result).pages), 2)


# ── Sign ─────────────────────────────────────────────────────────────────────

class TestSign(unittest.TestCase):
    def test_stamps_signature_produces_valid_pdf(self):
        sigs = [{"page": 0, "x": 5, "y": 5, "width": 40, "height": 20, "image": make_signature_png_base64()}]
        result = process_sign(make_pdf(1), sigs)
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_targets_only_specified_page(self):
        sigs = [{"page": 2, "x": 5, "y": 5, "width": 40, "height": 20, "image": make_signature_png_base64()}]
        result = process_sign(make_pdf(3), sigs)
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_multiple_signatures_same_page(self):
        img = make_signature_png_base64()
        sigs = [
            {"page": 0, "x": 5, "y": 5, "width": 40, "height": 20, "image": img},
            {"page": 0, "x": 50, "y": 5, "width": 40, "height": 20, "image": img},
        ]
        result = process_sign(make_pdf(1), sigs)
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_empty_signatures_preserves_page_count(self):
        result = process_sign(make_pdf(3), [])
        self.assertEqual(len(read_pdf(result).pages), 3)

    def test_raw_base64_without_data_uri_prefix_works(self):
        raw = make_signature_png_base64().split(",", 1)[1]
        sigs = [{"page": 0, "x": 0, "y": 0, "width": 40, "height": 20, "image": raw}]
        result = process_sign(make_pdf(1), sigs)
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_invalid_image_data_is_skipped_not_fatal(self):
        sigs = [{"page": 0, "x": 0, "y": 0, "width": 40, "height": 20, "image": "not-valid-base64!!"}]
        result = process_sign(make_pdf(1), sigs)
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_stamps_producer(self):
        result = process_sign(make_pdf(1), [])
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_sign(make_encrypted_pdf(password="x"), [], password="wrong")

    def test_correct_password_works(self):
        enc = make_encrypted_pdf(num_pages=2, password="secret")
        sigs = [{"page": 1, "x": 5, "y": 5, "width": 40, "height": 20, "image": make_signature_png_base64()}]
        result = process_sign(enc, sigs, password="secret")
        self.assertEqual(len(read_pdf(result).pages), 2)


# ── Fill Form ────────────────────────────────────────────────────────────────

class TestFillForm(unittest.TestCase):
    def test_fills_text_field_without_flatten(self):
        result = process_fill_form(make_form_pdf(), {"name_field": "Saqib Khan"}, flatten=False)
        fields = read_pdf(result).get_fields()
        self.assertEqual(fields["name_field"]["/V"], "Saqib Khan")

    def test_non_flatten_keeps_fields_editable(self):
        result = process_fill_form(make_form_pdf(), {"name_field": "Saqib Khan"}, flatten=False)
        reader = read_pdf(result)
        self.assertIsNotNone(reader.get_fields())
        self.assertIn("/Annots", reader.pages[0])

    def test_flatten_bakes_value_into_page_text(self):
        result = process_fill_form(make_form_pdf(), {"name_field": "Saqib Khan"}, flatten=True)
        self.assertIn("Saqib Khan", read_pdf(result).pages[0].extract_text())

    def test_flatten_removes_form_fields(self):
        result = process_fill_form(make_form_pdf(), {"name_field": "Saqib Khan"}, flatten=True)
        reader = read_pdf(result)
        self.assertIsNone(reader.get_fields())
        self.assertNotIn("/Annots", reader.pages[0])

    def test_fills_checkbox(self):
        result = process_fill_form(make_form_pdf(), {"subscribe_cb": "/Yes"}, flatten=False)
        fields = read_pdf(result).get_fields()
        self.assertEqual(fields["subscribe_cb"]["/V"], "/Yes")

    def test_empty_field_values_preserves_page_count(self):
        result = process_fill_form(make_form_pdf(), {}, flatten=False)
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_no_acroform_raises(self):
        with self.assertRaises(ValueError):
            process_fill_form(make_pdf(1), {"anything": "value"})

    def test_none_field_value_is_left_blank_not_stringified(self):
        result = process_fill_form(make_form_pdf(), {"name_field": None}, flatten=False)
        value = read_pdf(result).get_fields()["name_field"]["/V"]
        self.assertNotEqual(value, "None")

    def test_stamps_producer(self):
        result = process_fill_form(make_form_pdf(), {"name_field": "X"}, flatten=False)
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_fill_form(make_form_pdf(password="secret"), {}, password="wrong")

    def test_correct_password_works(self):
        enc = make_form_pdf(password="secret")
        result = process_fill_form(enc, {"name_field": "Saqib"}, password="secret")
        self.assertEqual(read_pdf(result).get_fields()["name_field"]["/V"], "Saqib")


# ── Protect ──────────────────────────────────────────────────────────────────

class TestProtect(unittest.TestCase):
    def test_output_is_encrypted(self):
        result = process_protect(make_pdf(1), "correct-horse")
        self.assertTrue(read_pdf(result).is_encrypted)

    def test_opens_with_correct_password(self):
        result = process_protect(make_pdf(2), "correct-horse")
        reader = read_pdf(result)
        self.assertNotEqual(reader.decrypt("correct-horse"), 0)
        self.assertEqual(len(reader.pages), 2)

    def test_fails_with_incorrect_password(self):
        result = process_protect(make_pdf(1), "correct-horse")
        reader = read_pdf(result)
        self.assertEqual(reader.decrypt("wrong-guess"), 0)

    def test_uses_aes_256(self):
        result = process_protect(make_pdf(1), "correct-horse")
        reader = read_pdf(result)
        encrypt_dict = reader.trailer["/Encrypt"].get_object()
        cfm = encrypt_dict["/CF"]["/StdCF"]["/CFM"]
        self.assertEqual(cfm, "/AESV3")
        self.assertEqual(encrypt_dict["/V"], 5)

    def test_preserves_page_content(self):
        pdf = make_pdf_with_text("Sensitive contract terms")
        result = process_protect(pdf, "correct-horse")
        reader = read_pdf(result)
        reader.decrypt("correct-horse")
        self.assertIn("Sensitive contract terms", reader.pages[0].extract_text())

    def test_stamps_producer(self):
        result = process_protect(make_pdf(1), "correct-horse")
        reader = read_pdf(result)
        reader.decrypt("correct-horse")
        self.assertIn("NilPDF", reader.metadata.get("/Producer", ""))

    def test_blank_new_password_raises(self):
        with self.assertRaises(ValueError):
            process_protect(make_pdf(1), "")

    def test_whitespace_only_new_password_is_accepted_literally(self):
        # A password of spaces is unusual but not blank — NilPDF doesn't second-guess it.
        result = process_protect(make_pdf(1), "   ")
        reader = read_pdf(result)
        self.assertNotEqual(reader.decrypt("   "), 0)

    def test_wrong_current_password_raises(self):
        enc = make_encrypted_pdf(password="old-pw")
        with self.assertRaises(ValueError):
            process_protect(enc, "new-pw", password="wrong")

    def test_replaces_protection_on_already_encrypted_pdf(self):
        enc = make_encrypted_pdf(num_pages=2, password="old-pw")
        result = process_protect(enc, "new-pw", password="old-pw")
        reader = read_pdf(result)
        # The old password no longer works, only the new one does.
        self.assertEqual(reader.decrypt("old-pw"), 0)
        reader2 = read_pdf(result)
        self.assertNotEqual(reader2.decrypt("new-pw"), 0)
        self.assertEqual(len(reader2.pages), 2)


# ── Unlock ───────────────────────────────────────────────────────────────────

class TestUnlock(unittest.TestCase):
    def test_output_opens_without_a_password(self):
        enc = make_encrypted_pdf(password="secret")
        result = process_unlock(enc, password="secret")
        reader = read_pdf(result)
        self.assertFalse(reader.is_encrypted)
        self.assertEqual(len(reader.pages), 1)

    def test_output_reports_no_remaining_encryption(self):
        enc = make_encrypted_pdf(num_pages=2, password="secret")
        result = process_unlock(enc, password="secret")
        self.assertNotIn(b"/Encrypt", result)
        self.assertFalse(read_pdf(result).is_encrypted)

    def test_preserves_page_content(self):
        plain = make_pdf_with_text("Confidential clause 7")
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(plain)))
        writer.encrypt(user_password="secret", owner_password="secret")
        buf = io.BytesIO()
        writer.write(buf)
        result = process_unlock(buf.getvalue(), password="secret")
        self.assertIn("Confidential clause 7", read_pdf(result).pages[0].extract_text())

    def test_wrong_password_raises(self):
        enc = make_encrypted_pdf(password="secret")
        with self.assertRaises(ValueError):
            process_unlock(enc, password="wrong-guess")

    def test_blank_password_raises(self):
        enc = make_encrypted_pdf(password="secret")
        with self.assertRaises(ValueError):
            process_unlock(enc, password="")

    def test_unprotected_pdf_raises_a_clear_error(self):
        with self.assertRaises(ValueError):
            process_unlock(make_pdf(1))

    def test_stamps_producer(self):
        enc = make_encrypted_pdf(password="secret")
        result = process_unlock(enc, password="secret")
        self.assertIn("NilPDF", producer_of(result))

    def test_user_password_alone_is_rejected_when_owner_password_differs(self):
        enc = make_encrypted_pdf_with_owner(user_password="viewonly", owner_password="fullaccess")
        with self.assertRaises(ValueError):
            process_unlock(enc, password="viewonly")

    def test_owner_password_removes_restrictions(self):
        enc = make_encrypted_pdf_with_owner(num_pages=2, user_password="viewonly", owner_password="fullaccess")
        result = process_unlock(enc, password="fullaccess")
        reader = read_pdf(result)
        self.assertFalse(reader.is_encrypted)
        self.assertEqual(len(reader.pages), 2)

    def test_single_password_used_for_both_roles_unlocks_directly(self):
        # NilPDF's own Protect PDF sets the same password as both user and
        # owner, so the common case never hits the owner-password gate.
        enc = make_encrypted_pdf_with_owner(user_password="samepw", owner_password="samepw")
        result = process_unlock(enc, password="samepw")
        self.assertFalse(read_pdf(result).is_encrypted)

    def test_unlocks_nilpdf_protect_output(self):
        protected = process_protect(make_pdf_with_text("Round trip"), "roundtrip-pw")
        result = process_unlock(protected, password="roundtrip-pw")
        reader = read_pdf(result)
        self.assertFalse(reader.is_encrypted)
        self.assertIn("Round trip", reader.pages[0].extract_text())

    def test_supports_common_encryption_algorithms(self):
        for algorithm in ["RC4-40", "RC4-128", "AES-128", "AES-256-R5", "AES-256"]:
            with self.subTest(algorithm=algorithm):
                enc = make_encrypted_pdf_with_owner(user_password="pw", owner_password="pw", algorithm=algorithm)
                result = process_unlock(enc, password="pw")
                self.assertFalse(read_pdf(result).is_encrypted)


# ── Fill & Sign ──────────────────────────────────────────────────────────────

class TestFillAndSign(unittest.TestCase):
    def test_fills_field_only(self):
        result = process_fill_and_sign(make_form_pdf(), {"name_field": "Saqib Khan"}, [], [])
        self.assertEqual(read_pdf(result).get_fields()["name_field"]["/V"], "Saqib Khan")

    def test_adds_text_only_on_plain_pdf(self):
        edits = [{"page": 0, "type": "text", "x": 5, "y": 5, "text": "2026-08-24", "size": 12}]
        result = process_fill_and_sign(make_pdf(1), {}, edits, [])
        self.assertIn("2026-08-24", read_pdf(result).pages[0].extract_text())

    def test_adds_signature_only_on_plain_pdf(self):
        sigs = [{"page": 0, "x": 5, "y": 5, "width": 40, "height": 20, "image": make_signature_png_base64()}]
        result = process_fill_and_sign(make_pdf(1), {}, [], sigs)
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_malformed_text_edit_is_skipped_not_fatal(self):
        edits = [
            {"page": 0, "type": "text", "x": "not-a-number", "y": 5, "text": "bad", "size": 12},
            {"page": 0, "type": "text", "x": 5, "y": 5, "text": "good", "size": 12},
        ]
        result = process_fill_and_sign(make_pdf(1), {}, edits, [])
        self.assertIn("good", read_pdf(result).pages[0].extract_text())

    def test_none_field_value_is_left_blank_not_stringified(self):
        result = process_fill_and_sign(make_form_pdf(), {"name_field": None}, [], [])
        value = read_pdf(result).get_fields()["name_field"]["/V"]
        self.assertNotEqual(value, "None")

    def test_combines_fields_text_and_signature(self):
        edits = [{"page": 0, "type": "text", "x": 5, "y": 5, "text": "Signed on 2026-08-24", "size": 12}]
        sigs = [{"page": 0, "x": 50, "y": 50, "width": 40, "height": 20, "image": make_signature_png_base64()}]
        result = process_fill_and_sign(make_form_pdf(), {"name_field": "Saqib Khan"}, edits, sigs)
        reader = read_pdf(result)
        self.assertEqual(reader.get_fields()["name_field"]["/V"], "Saqib Khan")
        self.assertIn("Signed on 2026-08-24", reader.pages[0].extract_text())

    def test_flatten_removes_form_fields(self):
        result = process_fill_and_sign(make_form_pdf(), {"name_field": "Saqib"}, [], [], flatten=True)
        reader = read_pdf(result)
        self.assertIsNone(reader.get_fields())
        self.assertNotIn("/Annots", reader.pages[0])

    def test_no_flatten_keeps_fields_editable(self):
        result = process_fill_and_sign(make_form_pdf(), {"name_field": "Saqib"}, [], [], flatten=False)
        reader = read_pdf(result)
        self.assertIsNotNone(reader.get_fields())

    def test_field_values_on_pdf_without_acroform_raises(self):
        with self.assertRaises(ValueError):
            process_fill_and_sign(make_pdf(1), {"anything": "value"}, [], [])

    def test_empty_field_values_on_plain_pdf_does_not_raise(self):
        result = process_fill_and_sign(make_pdf(2), {}, [], [])
        self.assertEqual(len(read_pdf(result).pages), 2)

    def test_targets_only_specified_page(self):
        edits = [{"page": 2, "type": "text", "x": 5, "y": 5, "text": "note", "size": 12}]
        result = process_fill_and_sign(make_pdf(3), {}, edits, [])
        reader = read_pdf(result)
        self.assertEqual(len(reader.pages), 3)
        self.assertIn("note", reader.pages[2].extract_text())
        self.assertNotIn("note", reader.pages[0].extract_text())

    def test_invalid_signature_image_is_skipped_not_fatal(self):
        sigs = [{"page": 0, "x": 0, "y": 0, "width": 40, "height": 20, "image": "not-valid-base64!!"}]
        result = process_fill_and_sign(make_pdf(1), {}, [], sigs)
        self.assertEqual(len(read_pdf(result).pages), 1)

    def test_stamps_producer(self):
        result = process_fill_and_sign(make_pdf(1), {}, [], [])
        self.assertIn("NilPDF", producer_of(result))

    def test_wrong_password_raises(self):
        with self.assertRaises(ValueError):
            process_fill_and_sign(make_form_pdf(password="secret"), {}, [], [], password="wrong")

    def test_correct_password_works(self):
        enc = make_form_pdf(password="secret")
        result = process_fill_and_sign(enc, {"name_field": "Saqib"}, [], [], password="secret")
        self.assertEqual(read_pdf(result).get_fields()["name_field"]["/V"], "Saqib")


if __name__ == "__main__":
    unittest.main()


# ── Redaction checker ──────────────────────────────────────────────────────

SECRET = "SECRET-123-45-6789"


def make_line_pdf(draw=None, before=None, text=f"Page 1. SSN {SECRET}"):
    """A 400x300 page with one line of text at (40, 200). `before` paints
    things under the text; `draw` paints things on top of it."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(400, 300))
    if before:
        before(c)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(40, 200, text)
    if draw:
        draw(c)
    c.showPage()
    c.drawString(40, 200, "Page 2. nothing sensitive here")
    c.save()
    return buf.getvalue()


def box(r, g, b, x=30, y=190, w=250, h=30, alpha=None):
    def paint(c):
        c.setFillColorRGB(r, g, b)
        if alpha is not None:
            c.setFillAlpha(alpha)
        c.rect(x, y, w, h, fill=1, stroke=0)
    return paint


def check(data, password=""):
    import json
    return json.loads(process_check_redaction(data, password=password))


def with_annotation(data, subtype, **extra):
    from pypdf.generic import ArrayObject, DictionaryObject, FloatObject, NameObject
    writer = PdfWriter(clone_from=io.BytesIO(data))
    annot = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject(subtype),
        NameObject("/Rect"): ArrayObject([FloatObject(v) for v in (30, 190, 280, 220)]),
    })
    for k, v in extra.items():
        annot[NameObject("/" + k)] = ArrayObject([FloatObject(x) for x in v])
    writer.add_annotation(page_number=0, annotation=annot)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class TestCheckRedaction(unittest.TestCase):
    """The checker must catch every way text survives under a "redaction", and
    must not cry wolf at ordinary layouts. A false all-clear is the worst
    outcome, so the leak cases are asserted as strictly as the clean ones."""

    # ---- the leaks it exists to catch ----

    def test_black_box_over_text_is_found(self):
        r = check(make_line_pdf(draw=box(0, 0, 0)))
        self.assertTrue(r["hidden_text_found"])
        f = r["findings"][0]
        self.assertEqual((f["kind"], f["page"]), ("covered_text", 1))
        self.assertIn(SECRET, f["text"])
        self.assertIn("black", f["detail"])

    def test_white_out_over_text_is_found(self):
        r = check(make_line_pdf(draw=box(1, 1, 1)))
        self.assertTrue(r["hidden_text_found"])
        self.assertIn(SECRET, r["findings"][0]["text"])
        self.assertIn("white", r["findings"][0]["detail"])

    def test_box_over_only_the_secret_reports_the_secret_not_the_whole_line(self):
        # Covers roughly x 112..236, where the secret sits; "Page 1." is left of it.
        r = check(make_line_pdf(draw=box(0, 0, 0, x=112, w=124)))
        self.assertTrue(r["hidden_text_found"])
        self.assertIn(SECRET, r["findings"][0]["text"])
        self.assertNotIn("Page", r["findings"][0]["text"])

    def test_image_pasted_over_text_is_found(self):
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        patch = ImageReader(Image.new("RGB", (50, 10), "black"))
        r = check(make_line_pdf(draw=lambda c: c.drawImage(patch, 30, 190, width=250, height=30)))
        self.assertTrue(r["hidden_text_found"])
        self.assertIn("image", r["findings"][0]["detail"])

    def test_unapplied_redact_annotation_is_found(self):
        r = check(with_annotation(make_line_pdf(), "/Redact"))
        kinds = {f["kind"] for f in r["findings"]}
        self.assertIn("unapplied_redaction", kinds)
        self.assertIn(SECRET, next(f for f in r["findings"] if f["kind"] == "unapplied_redaction")["text"])

    def test_black_square_annotation_over_text_is_found(self):
        r = check(with_annotation(make_line_pdf(), "/Square", IC=(0, 0, 0), C=(0, 0, 0)))
        self.assertIn("unapplied_redaction", {f["kind"] for f in r["findings"]})

    def test_text_kept_in_an_earlier_saved_version_is_found(self):
        """Incremental saves append, so a secret deleted in a later save stays
        in the file. Here the second save replaces page 1 with harmless text."""
        from pypdf.generic import DecodedStreamObject, NameObject
        original = make_line_pdf()
        writer = PdfWriter(io.BytesIO(original), incremental=True)
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 40 200 Td (Page 1. nothing here now) Tj ET")
        writer.pages[0][NameObject("/Contents")] = writer._add_object(stream)
        out = io.BytesIO()
        writer.write(out)
        data = out.getvalue()
        self.assertGreater(data.count(b"%%EOF"), 1, "fixture must really be an incremental update")
        self.assertNotIn(SECRET, read_pdf(data).pages[0].extract_text())
        r = check(data)
        f = [f for f in r["findings"] if f["kind"] == "earlier_revision"]
        self.assertTrue(f, f"expected an earlier_revision finding, got {r['findings']}")
        self.assertIn(SECRET, f[0]["text"])

    # ---- ordinary layouts it must not flag ----

    def test_plain_text_is_clean(self):
        self.assertFalse(check(make_line_pdf())["hidden_text_found"])

    def test_background_painted_under_text_is_clean(self):
        """Table cells and highlighted rows paint the fill first, text second."""
        self.assertFalse(check(make_line_pdf(before=box(0.9, 0.9, 0.2)))["hidden_text_found"])

    def test_white_text_on_a_dark_bar_is_clean(self):
        """A dark header bar with light text on top is design, not redaction:
        the text is painted after the bar, so it is visible."""
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(400, 300))
        c.setFillColorRGB(0, 0, 0)
        c.rect(30, 190, 250, 30, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.drawString(40, 200, "Quarterly report")
        c.save()
        self.assertFalse(check(buf.getvalue())["hidden_text_found"])

    def test_translucent_highlight_is_clean(self):
        """A highlighter lets the text show through, so nothing is hidden."""
        self.assertFalse(check(make_line_pdf(draw=box(1, 1, 0, alpha=0.35)))["hidden_text_found"])

    def test_box_in_empty_space_is_clean(self):
        self.assertFalse(check(make_line_pdf(draw=box(0, 0, 0, x=40, y=40, w=100, h=30)))["hidden_text_found"])

    def test_nilpdf_redaction_output_is_clean(self):
        """End to end: a file redacted by NilPDF passes NilPDF's own checker."""
        redacted = process_redact(make_line_pdf(), {0: make_flat_page_png_base64(800, 600)})
        self.assertFalse(check(redacted)["hidden_text_found"])

    # ---- plumbing ----

    def test_report_shape(self):
        r = check(make_line_pdf())
        self.assertEqual(r["pages"], 2)
        for key in ("hidden_text_found", "findings", "metadata", "invisible_text_pages", "limitations"):
            self.assertIn(key, r)

    def test_encrypted_pdf_needs_the_password(self):
        enc = make_encrypted_pdf(password="pw")
        with self.assertRaises(ValueError):
            process_check_redaction(enc, password="wrong")
        self.assertEqual(check(enc, password="pw")["pages"], 1)

    def test_file_is_not_modified_or_returned(self):
        """The checker only reads; its output is a JSON report, not a PDF."""
        out = process_check_redaction(make_line_pdf(draw=box(0, 0, 0)))
        self.assertFalse(out.startswith(b"%PDF"))
