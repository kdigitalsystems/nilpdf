import unittest
import io
from pypdf import PdfWriter
from core.pdf_engine import process_merge, process_split, process_reorder

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
        # Verify the result is a non-empty PDF
        self.assertTrue(len(result) > 100)

    def test_split(self):
        pdf = create_dummy_pdf(5) # 5 pages
        # Extract page 1 and 3 (index 0 and 2)
        result = process_split(pdf, [0, 2])
        self.assertTrue(len(result) > 100)

    def test_reorder(self):
        pdf = create_dummy_pdf(3)
        result = process_reorder(pdf, [2, 1, 0])
        self.assertTrue(len(result) > 100)

if __name__ == '__main__':
    unittest.main()
