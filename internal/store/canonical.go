package store

import (
	"bytes"
	"fmt"
	"sort"
	"strconv"
	"unicode/utf8"

	"launchcontrol/internal/ordjson"
)

// canonicalJSON serializes v exactly the way Python's
//
//	json.dumps(v, sort_keys=True, ensure_ascii=False)
//
// does: object keys sorted, ", " / ": " separators, strings escaped
// Python-style (no HTML escaping, non-ASCII kept raw, \u00xx with
// lowercase hex for control characters). The audit trail's tamper-evident
// hashes were produced by that serializer, so the Go server must byte-match
// it when verifying entries written by the Python app.
//
// Numbers must be json.Number (ordjson.Parse / Normalize guarantee that)
// so the original literal from the database is preserved byte-for-byte.
func canonicalJSON(v any) string {
	var buf bytes.Buffer
	writeCanonical(&buf, v)
	return buf.String()
}

func writeCanonical(buf *bytes.Buffer, v any) {
	switch x := v.(type) {
	case nil:
		buf.WriteString("null")
	case bool:
		if x {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case string:
		writePythonString(buf, x)
	case []any:
		buf.WriteByte('[')
		for i, item := range x {
			if i > 0 {
				buf.WriteString(", ")
			}
			writeCanonical(buf, item)
		}
		buf.WriteByte(']')
	case *ordjson.OMap:
		keys := append([]string(nil), x.Keys()...)
		sort.Strings(keys)
		buf.WriteByte('{')
		for i, k := range keys {
			if i > 0 {
				buf.WriteString(", ")
			}
			writePythonString(buf, k)
			buf.WriteString(": ")
			writeCanonical(buf, x.Get(k))
		}
		buf.WriteByte('}')
	default:
		// Fallback for Go-native numbers created in-process. The audit
		// path always normalizes first (see Normalize), so this should
		// not fire for stored data.
		buf.WriteString(pythonNumber(v))
	}
}

// writePythonString escapes a string with Python's json.dumps rules for
// ensure_ascii=False: only the two mandatory escapes, the five short
// control escapes, and \u00xx (lowercase hex) for the remaining control
// characters. Everything else, including non-ASCII, is written raw.
func writePythonString(buf *bytes.Buffer, s string) {
	buf.WriteByte('"')
	for i := 0; i < len(s); {
		r, size := utf8.DecodeRuneInString(s[i:])
		switch r {
		case '"':
			buf.WriteString(`\"`)
		case '\\':
			buf.WriteString(`\\`)
		case '\n':
			buf.WriteString(`\n`)
		case '\r':
			buf.WriteString(`\r`)
		case '\t':
			buf.WriteString(`\t`)
		case '\b':
			buf.WriteString(`\b`)
		case '\f':
			buf.WriteString(`\f`)
		default:
			if r < 0x20 {
				fmt.Fprintf(buf, `\u%04x`, r)
			} else {
				buf.WriteString(s[i : i+size])
			}
		}
		i += size
	}
	buf.WriteByte('"')
}

// pythonNumber renders Go-native numbers in a stable round-trippable
// form. Only a defensive fallback; stored data goes through Normalize
// first, so numbers are json.Number literals by then.
func pythonNumber(v any) string {
	switch x := v.(type) {
	case float64:
		return strconv.FormatFloat(x, 'g', -1, 64)
	case float32:
		return strconv.FormatFloat(float64(x), 'g', -1, 32)
	case int:
		return strconv.Itoa(x)
	case int64:
		return strconv.FormatInt(x, 10)
	default:
		return fmt.Sprint(x)
	}
}

// Normalize round-trips v through JSON so every number becomes a
// json.Number carrying the exact literal that would be stored. Hashing
// entries before and after a database round trip then yields identical
// bytes, which is what keeps audit hashes stable.
func Normalize(v any) any {
	raw, err := ordjson.Marshal(v)
	if err != nil {
		return v
	}
	parsed, err := ordjson.Parse(raw)
	if err != nil {
		return v
	}
	return parsed
}
