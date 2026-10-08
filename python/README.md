# nilpdf

**Find text still hiding in a "redacted" PDF.**

A black box drawn over text only covers it. The text stays in the file, and
anyone can select it, copy it, or search for it. That is how sealed material
leaked from a Paul Manafort court filing in 2019, and it keeps happening.

`nilpdf check-redaction` reads a PDF the way a script would and reports text
that is still there:

- **under a box**: text drawn first and then covered by an opaque shape or
  image drawn over it (black boxes, white-out, pasted image patches)
- **under a redaction that was never applied**: `/Redact` marks, and black
  box annotations sitting over live text
- **in an earlier saved version**: editors that save by appending changes
  keep the old version inside the same file

It needs only the redacted file, not the original. **Everything runs on your
machine.** The tool makes no network requests and sends nothing anywhere,
which matters most for exactly the documents you'd want to check.

```console
$ pip install nilpdf
$ nilpdf check-redaction filing.pdf
HIDDEN  filing.pdf: hidden text in 1 place
  page 1, hidden under a box: Page 1. SSN SECRET-123-45-6789
    Drawn over by a black shape but still in the file: it can be selected, copied and searched.
```

Prefer a browser? The same check runs at
[nilpdf.com/check-pdf-redaction](https://nilpdf.com/check-pdf-redaction/), also
without uploading the file.

## Usage

```console
nilpdf check-redaction filing.pdf                # one file
nilpdf check-redaction docs/                     # every PDF under docs/, recursively
nilpdf check-redaction a.pdf b.pdf --password pw # encrypted PDFs
nilpdf check-redaction --json out/*.pdf          # machine-readable report
curl -s https://example.com/doc.pdf | nilpdf check-redaction -   # standard input
nilpdf check-redaction -v filing.pdf             # also show title, author and other properties
```

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Every file was checked and none has hidden text |
| `1` | At least one file has hidden text |
| `2` | No hidden text found, but a file couldn't be checked (unreadable, not a PDF, wrong password), or the arguments were wrong |

### In CI

Fail a build when a PDF in the repository still has hidden text:

```yaml
- run: pip install nilpdf
- run: nilpdf check-redaction published/
```

### As a pre-commit hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/kdigitalsystems/nilpdf
    rev: v0.1.0
    hooks:
      - id: check-redaction
```

### From Python

```python
import nilpdf

report = nilpdf.check_redaction("filing.pdf")       # a path, or the PDF's bytes
if report["hidden_text_found"]:
    for f in report["findings"]:
        print(f["page"], f["kind"], f["text"])
```

Each finding has a `kind` (`covered_text`, `unapplied_redaction` or
`earlier_revision`), a `page`, the hidden `text`, and a `detail` explaining why
it is still readable. The report also lists document `metadata` (title, author
and so on, which can reveal information too) and any pages with an invisible
OCR text layer.

The engine behind the website's other tools (merge, split, compress, redact,
sign and more) is available as `nilpdf.engine`. Those tools need Pillow and
reportlab: `pip install "nilpdf[full]"`.

## How it works, and what it can't see

The checker walks each page's drawing instructions in the order they are
painted. Text that is painted first and then covered by an opaque shape or
image painted later is hidden text. Paint order is what keeps it from crying
wolf: a table background or a dark header bar is painted *before* its text, so
it is left alone, and a translucent highlighter is ignored because the text
shows through.

It can't see inside images. If a scanned page was blacked out in the scan
itself, those pixels are simply gone or simply there, and there's no text to
find. Positions are estimated from average character widths, so a reported
phrase can include a neighbouring word or miss one at the very edge of a box.

## Related

[x-ray](https://github.com/freelawproject/x-ray) from Free Law Project is an
excellent Python library for finding text under drawn rectangles, and verifies
candidates by rendering them. `nilpdf` also checks unapplied redaction marks
and earlier saved versions, and its check runs in the browser too, for people
who won't install anything.

## License

MIT. Source: [github.com/kdigitalsystems/nilpdf](https://github.com/kdigitalsystems/nilpdf)
