def py_encode_basestring_ascii(s):
    """Return an ASCII-only JSON representation of a Python string"""

    def replace(match):
        s = match.group(0)
        try:
            return ESCAPE_DCT[s]
        except KeyError:
            n = ord(s)
            if n < 65536:
                return "\\u{0:04x}".format(n)
            else:
                n -= 65536
                s1 = 55296 | n >> 10 & 1023
                s2 = 56320 | n & 1023
                return "\\u{0:04x}\\u{1:04x}".format(s1, s2)

    return '"' + ESCAPE_ASCII.sub(replace, s) + '"'


def default(self, o):
    """Implement this method in a subclass such that it returns
    a serializable object for ``o``, or calls the base implementation
    (to raise a ``TypeError``).

    For example, to support arbitrary iterators, you could
    implement default like this::

        def default(self, o):
            try:
                iterable = iter(o)
            except TypeError:
                pass
            else:
                return list(iterable)
            # Let the base class default method raise the TypeError
            return super().default(o)

    """
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
