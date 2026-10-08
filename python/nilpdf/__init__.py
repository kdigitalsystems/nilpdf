"""NilPDF: PDF tools that keep your files on your machine.

The command line tool's main job is ``nilpdf check-redaction``, which reports
text still hiding in a "redacted" PDF. The same engine that powers
https://nilpdf.com is available as ``nilpdf.engine``.

Nothing here makes network requests. Files are read, checked and left as they
were, on the machine running the code.
"""
import json as _json
import os as _os

__version__ = "0.1.0"

__all__ = ["check_redaction", "__version__"]


def check_redaction(source, password=""):
    """Report text that is still in a PDF but hidden from view.

    ``source`` is a path (``str`` or path-like) or the PDF's bytes. The PDF
    itself is not modified. Returns a dict with:

    - ``hidden_text_found``: True if anything was found
    - ``findings``: a list of dicts with ``kind`` (``covered_text``,
      ``unapplied_redaction`` or ``earlier_revision``), ``page``, ``text``
      and ``detail``
    - ``metadata``: document properties, which can also reveal information
    - ``invisible_text_pages``: pages with an invisible (typically OCR) text layer
    - ``pages`` and ``limitations``

    Raises ``ValueError`` for a wrong or missing password, and pypdf's errors
    for files that are not readable PDFs.
    """
    from . import engine

    if isinstance(source, (bytes, bytearray, memoryview)):
        data = bytes(source)
    else:
        with open(_os.fspath(source), "rb") as f:
            data = f.read()
    return _json.loads(engine.process_check_redaction(data, password=password))
