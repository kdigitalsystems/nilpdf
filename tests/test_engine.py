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


def read_pdf(data):
    return PdfReader(io.BytesIO(data))


def producer_of(data):
    return read_pdf(data).metadata.get("/Producer", "")


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

    def test_ignores_out_of_bounds_indices(self):
        result = process_reorder(make_pdf(3), [0, 1, 99])
        self.assertEqual(len(read_pdf(result).pages), 2)

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
            self.assertIn("report_squeezed.pdf", zf.namelist())


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


if __name__ == "__main__":
    unittest.main()
