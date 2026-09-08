"""Dependency-free, conservative JavaScript minification for static serving.

The minifier only ever deletes characters: comments, indentation, blank lines
and redundant intra-line whitespace. It never rewrites or reorders code.

Safety rules:
- Newlines between tokens are preserved, so automatic semicolon insertion
  (ASI) semantics are untouched.
- Contents of string literals, regex literals and template literals are
  preserved verbatim, so runtime string values never change.
- A regex-vs-division ambiguity check (based on the preceding token, with a
  keyword allowlist) decides whether `/` starts a regex literal.
- Any anomaly (newline inside a string/regex, unbalanced braces/templates,
  unexpected EOF) raises MinifyError and the original file is served instead.
- Every result is verified before use: the stream of significant characters
  (everything except whitespace and comments) must be identical in the
  original and the minified output, otherwise MinifyError is raised.
"""

import logging
import threading

log = logging.getLogger("launcher.minify")

_WS = " \t\r\n\f\v"

# Keywords after which a `/` starts a regex literal rather than division.
_REGEX_KEYWORDS = frozenset({
    "return", "typeof", "instanceof", "in", "of", "new", "delete",
    "void", "do", "else", "case", "throw", "yield", "await",
})


class MinifyError(Exception):
    pass


def _is_word_char(ch):
    return ch.isalnum() or ch in "_$"


def _regex_allowed(out):
    """Decide whether a `/` at this point starts a regex literal, based on the
    last significant character already emitted."""
    k = len(out) - 1
    while k >= 0 and out[k] in _WS:
        k -= 1
    if k < 0:
        return True
    c = out[k]
    if c in ")]\"`":
        return False
    if c == "}":
        return True
    if _is_word_char(c):
        j = k
        while j >= 0 and _is_word_char(out[j]):
            j -= 1
        word = "".join(out[j + 1:k + 1])
        if word[:1].isdigit():
            return False
        return word in _REGEX_KEYWORDS
    return True


def _run(source, canonical_only=False):
    """Tokenize `source` and emit it. In normal mode whitespace and comments
    are stripped conservatively; in canonical_only mode ALL whitespace and
    comments are dropped (used for the integrity self-check)."""
    out = []
    n = len(source)
    i = 0
    mode = "code"  # "code" | "template"
    braces = [0]   # brace depth per open template expression (bottom = file)
    string_q = None
    in_regex = False
    regex_class = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = source[i]

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                continue  # let the newline flow through whitespace handling
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and i + 1 < n and source[i + 1] == "/":
                in_block_comment = False
                if not canonical_only and out and out[-1] != "\n":
                    out.append(" ")
                i += 2
                continue
            i += 1
            continue

        if string_q is not None:
            out.append(ch)
            if ch == "\\":
                if i + 1 >= n:
                    raise MinifyError("escape at EOF")
                out.append(source[i + 1])
                i += 2
                continue
            if ch == "\n":
                raise MinifyError("newline in string literal")
            if ch == string_q:
                string_q = None
            i += 1
            continue

        if in_regex:
            if ch == "\\":
                if i + 1 >= n:
                    raise MinifyError("escape at EOF")
                out.append(ch)
                out.append(source[i + 1])
                i += 2
                continue
            if ch == "\n":
                raise MinifyError("newline in regex literal")
            if ch == "[":
                regex_class = True
            elif ch == "]":
                regex_class = False
            elif ch == "/" and not regex_class:
                in_regex = False
            out.append(ch)
            i += 1
            continue

        if mode == "template":
            if ch == "\\":
                if i + 1 >= n:
                    raise MinifyError("escape at EOF")
                out.append(ch)
                out.append(source[i + 1])
                i += 2
                continue
            if ch == "`":
                out.append(ch)
                mode = "code"
                i += 1
                continue
            if ch == "$" and i + 1 < n and source[i + 1] == "{":
                out.append("${")
                braces.append(0)
                mode = "code"
                i += 2
                continue
            out.append(ch)
            i += 1
            continue

        # --- code mode ---

        if ch in _WS:
            j = i
            while j < n and source[j] in _WS:
                j += 1
            if not canonical_only:
                if "\n" in source[i:j]:
                    while out and out[-1] in " \t":
                        out.pop()
                    if out and out[-1] != "\n":
                        out.append("\n")
                elif out and out[-1] not in _WS:
                    out.append(" ")
            i = j
            continue

        if ch == "/" and i + 1 < n:
            nxt = source[i + 1]
            if nxt == "/":
                in_line_comment = True
                i += 2
                continue
            if nxt == "*":
                in_block_comment = True
                i += 2
                continue
            if _regex_allowed(out):
                in_regex = True
                regex_class = False
            out.append(ch)
            i += 1
            continue

        if ch in "'\"":
            string_q = ch
            out.append(ch)
            i += 1
            continue

        if ch == "`":
            mode = "template"
            out.append(ch)
            i += 1
            continue

        if ch == "{":
            braces[-1] += 1
        elif ch == "}":
            if braces[-1] == 0:
                if len(braces) == 1:
                    raise MinifyError("unbalanced brace")
                braces.pop()
                mode = "template"
            else:
                braces[-1] -= 1

        out.append(ch)
        i += 1

    if string_q is not None or in_regex or in_block_comment or in_line_comment:
        raise MinifyError("unexpected EOF inside token")
    if mode == "template" or len(braces) > 1 or braces[0] != 0:
        raise MinifyError("unbalanced template or braces")

    return "".join(out)


def minify_js(source):
    result = _run(source, canonical_only=False)
    canonical = _run(source, canonical_only=True)
    if _run(result, canonical_only=True) != canonical:
        raise MinifyError("integrity check failed")
    return result


def _looks_minified(source):
    """Heuristic: files whose first lines are not indented are assumed to be
    build artifacts that are already minified, and are passed through."""
    for line in source[:65536].splitlines()[:100]:
        if line[:1] in (" ", "\t"):
            return False
    return True


_cache = {}
_cache_lock = threading.Lock()


def minified_js_bytes(path):
    """Return minified bytes for a JS file, or None to serve it as-is."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = str(path)
    stamp = (st.st_mtime_ns, st.st_size)
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
    try:
        source = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    if _looks_minified(source):
        result = None
    else:
        try:
            result = minify_js(source).encode("utf-8")
        except MinifyError as exc:
            log.warning("Minification skipped for %s: %s", path, exc)
            result = None
    with _cache_lock:
        _cache[key] = (stamp, result)
    return result
