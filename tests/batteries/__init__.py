"""Data-driven snippet batteries.

Each sibling module exports ``SNIPPETS``.  For the Python batteries an item is either a Python
source string or ``(source, (3, 12))`` when the snippet needs a newer interpreter.  ``lenient``
exports ``(dpy_text, python_reference)`` pairs and ``rejected`` exports ``(dpy_text, error_code)``.
"""

V311 = (3, 11)
V312 = (3, 12)
V313 = (3, 13)
