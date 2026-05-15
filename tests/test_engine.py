import unittest
import io
from pypdf import PdfWriter, PdfReader
from core.pdf_engine import (
    process_merge, process_split, process_reorder,
    process_anonymize, process_compress, process_split_ranges
)

def create_dummy_pdf(num_pages=1):
    """Utility to create a small valid PDF in memory for testing."""
    writer = PdfWriter()
    for i in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()

class TestPDFEngine(unittest.TestCase):
    def test_merge(self):
        pdf1 = create_dummy_pdf(1)
        pdf2 = create_dummy_pdf(1)
        result = process_merge([pdf1, pdf2])
        self.assertTrue(len(result) > 100)
        reader = PdfReader(io.BytesIO(result))
        self.assertEqual(len(reader.pages), 2)

    def test_split(self):
        pdf = create_dummy_pdf(5)
        result = process_split(pdf, [0, 2])
        self.assertTrue(len(result) > 100)
        reader = PdfReader(io.BytesIO(result))
        self.assertEqual(len(reader.pages), 2)

    def test_split_out_of_range(self):
        pdf = create_dummy_pdf(3)
        with self.assertRaises(ValueError) as ctx:
            process_split(pdf, [0, 99])
        self.assertIn("don't exist", str(ctx.exception))

    def test_reorder(self):
        pdf = create_dummy_pdf(3)
        result = process_reorder(pdf, [2, 1, 0])
        self.assertTrue(len(result) > 100)
        reader = PdfReader(io.BytesIO(result))
        self.assertEqual(len(reader.pages), 3)

    def test_anonymize(self):
        pdf = create_dummy_pdf(1)
        result = process_anonymize(pdf)
        reader = PdfReader(io.BytesIO(result))
        meta = reader.metadata
        self.assertEqual(meta.get("/Producer"), "NilPDF (Private)")
        self.assertEqual(meta.get("/Author"), "")
        self.assertEqual(meta.get("/CreationDate"), "D:19700101000000Z")

    def test_compress(self):
        pdf = create_dummy_pdf(2)
        result = process_compress(pdf)
        self.assertTrue(len(result) > 100)
        reader = PdfReader(io.BytesIO(result))
        self.assertEqual(len(reader.pages), 2)

    def test_split_ranges(self):
        pdf = create_dummy_pdf(6)
        result = process_split_ranges(pdf, [[0, 1, 2], [3, 4, 5]])
        self.assertTrue(len(result) > 100)  # Returns a ZIP

    def test_split_ranges_out_of_range(self):
        pdf = create_dummy_pdf(3)
        with self.assertRaises(ValueError):
            process_split_ranges(pdf, [[0, 1], [5, 6]])

if __name__ == '__main__':
    unittest.main()
