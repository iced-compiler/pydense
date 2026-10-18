def _wrap_chunks(self, chunks):
    """_wrap_chunks(chunks : [string]) -> [string]

    Wrap a sequence of text chunks and return a list of lines of
    length 'self.width' or less.  (If 'break_long_words' is false,
    some lines may be longer than this.)  Chunks correspond roughly
    to words and the whitespace between them: each chunk is
    indivisible (modulo 'break_long_words'), but a line break can
    come between any two chunks.  Chunks should not have internal
    whitespace; ie. a chunk is either all whitespace or a "word".
    Whitespace chunks will be removed from the beginning and end of
    lines, but apart from that whitespace is preserved.
    """
    lines = []
    if self.width <= 0:
        raise ValueError("invalid width %r (must be > 0)" % self.width)
    if self.max_lines is not None:
        if self.max_lines > 1:
            indent = self.subsequent_indent
        else:
            indent = self.initial_indent
        if len(indent) + len(self.placeholder.lstrip()) > self.width:
            raise ValueError("placeholder too large for max width")
    chunks.reverse()
    while chunks:
        cur_line = []
        cur_len = 0
        if lines:
            indent = self.subsequent_indent
        else:
            indent = self.initial_indent
        width = self.width - len(indent)
        if self.drop_whitespace and chunks[-1].strip() == "" and lines:
            del chunks[-1]
        while chunks:
            l = len(chunks[-1])
            if cur_len + l <= width:
                cur_line.append(chunks.pop())
                cur_len += l
            else:
                break
        if chunks and len(chunks[-1]) > width:
            self._handle_long_word(chunks, cur_line, cur_len, width)
            cur_len = sum(map(len, cur_line))
        if self.drop_whitespace and cur_line and (cur_line[-1].strip() == ""):
            cur_len -= len(cur_line[-1])
            del cur_line[-1]
        if cur_line:
            if (
                self.max_lines is None
                or len(lines) + 1 < self.max_lines
                or (
                    (
                        not chunks
                        or (self.drop_whitespace and len(chunks) == 1 and (not chunks[0].strip()))
                    )
                    and cur_len <= width
                )
            ):
                lines.append(indent + "".join(cur_line))
            else:
                while cur_line:
                    if cur_line[-1].strip() and cur_len + len(self.placeholder) <= width:
                        cur_line.append(self.placeholder)
                        lines.append(indent + "".join(cur_line))
                        break
                    cur_len -= len(cur_line[-1])
                    del cur_line[-1]
                else:
                    if lines:
                        prev_line = lines[-1].rstrip()
                        if len(prev_line) + len(self.placeholder) <= self.width:
                            lines[-1] = prev_line + self.placeholder
                            break
                    lines.append(indent + self.placeholder.lstrip())
                break
    return lines
