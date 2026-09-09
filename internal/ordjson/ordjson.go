// Package ordjson provides order-preserving JSON handling.
//
// The app's data is dynamic (JSON blobs in SQLite, exactly like the
// Python original), and two behaviours depend on object key order:
// the run panel renders workflow steps via Object.entries, and history
// round-trips must not reshuffle stored keys. Go's map[string]any sorts
// keys alphabetically when marshalled, so every object is decoded into
// OMap — the equivalent of a Python dict — and marshalled in insertion
// order. Numbers are kept as json.Number so the original literal
// survives storage round-trips untouched.
package ordjson

import (
	"bytes"
	"encoding/json"
	"fmt"
)

// OMap is an insertion-ordered string-keyed map.
type OMap struct {
	keys []string
	vals map[string]any
}

// New returns an empty ordered map.
func New() *OMap {
	return &OMap{vals: map[string]any{}}
}

// Get returns the value for key, or nil when missing.
func (m *OMap) Get(key string) any {
	if m == nil {
		return nil
	}
	return m.vals[key]
}

// GetOK returns the value and whether the key exists.
func (m *OMap) GetOK(key string) (any, bool) {
	if m == nil {
		return nil, false
	}
	v, ok := m.vals[key]
	return v, ok
}

// Set stores a value, appending the key on first use (Python dict
// semantics: new keys land at the end).
func (m *OMap) Set(key string, value any) *OMap {
	if _, ok := m.vals[key]; !ok {
		m.keys = append(m.keys, key)
	}
	m.vals[key] = value
	return m
}

// Delete removes a key if present.
func (m *OMap) Delete(key string) {
	if _, ok := m.vals[key]; ok {
		delete(m.vals, key)
		for i, k := range m.keys {
			if k == key {
				m.keys = append(m.keys[:i], m.keys[i+1:]...)
				break
			}
		}
	}
}

// Keys returns the keys in insertion order.
func (m *OMap) Keys() []string {
	if m == nil {
		return nil
	}
	return m.keys
}

// Len returns the number of keys.
func (m *OMap) Len() int {
	if m == nil {
		return 0
	}
	return len(m.keys)
}

// Clone deep-copies the map (Python copy.deepcopy): nested OMaps and
// slices are copied recursively, so mutating the clone never touches
// the original — used for audit before/after snapshots.
func (m *OMap) Clone() *OMap {
	if m == nil {
		return nil
	}
	out := New()
	for _, k := range m.keys {
		out.Set(k, cloneValue(m.vals[k]))
	}
	return out
}

func cloneValue(v any) any {
	switch x := v.(type) {
	case *OMap:
		return x.Clone()
	case []any:
		out := make([]any, len(x))
		for i, item := range x {
			out[i] = cloneValue(item)
		}
		return out
	default:
		return v
	}
}

// Parse decodes JSON text into any, turning objects into *OMap and
// numbers into json.Number.
func Parse(data []byte) (any, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	v, err := decodeValue(dec)
	if err != nil {
		return nil, err
	}
	return v, nil
}

func decodeValue(dec *json.Decoder) (any, error) {
	tok, err := dec.Token()
	if err != nil {
		return nil, err
	}
	return decodeFromToken(dec, tok)
}

func decodeFromToken(dec *json.Decoder, tok json.Token) (any, error) {
	delim, ok := tok.(json.Delim)
	if !ok {
		// json.Number, string, bool or nil arrive as plain tokens.
		return tok, nil
	}
	switch delim {
	case '{':
		m := New()
		for dec.More() {
			keyTok, err := dec.Token()
			if err != nil {
				return nil, err
			}
			key, ok := keyTok.(string)
			if !ok {
				return nil, fmt.Errorf("non-string object key")
			}
			v, err := decodeValue(dec)
			if err != nil {
				return nil, err
			}
			m.Set(key, v)
		}
		// Consume the closing brace.
		if _, err := dec.Token(); err != nil {
			return nil, err
		}
		return m, nil
	case '[':
		arr := []any{}
		for dec.More() {
			v, err := decodeValue(dec)
			if err != nil {
				return nil, err
			}
			arr = append(arr, v)
		}
		if _, err := dec.Token(); err != nil {
			return nil, err
		}
		return arr, nil
	default:
		return nil, fmt.Errorf("unexpected delimiter %v", delim)
	}
}

// Marshal serializes any Parse-produced value (and plain Go values)
// back to JSON, writing OMap keys in insertion order and json.Number
// literals verbatim.
func Marshal(v any) ([]byte, error) {
	var buf bytes.Buffer
	if err := writeValue(&buf, v); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func writeValue(buf *bytes.Buffer, v any) error {
	switch x := v.(type) {
	case nil:
		buf.WriteString("null")
	case bool:
		if x {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case json.Number:
		buf.WriteString(x.String())
	case string:
		return writeJSONString(buf, x)
	case *OMap:
		buf.WriteByte('{')
		for i, k := range x.keys {
			if i > 0 {
				buf.WriteByte(',')
			}
			if err := writeJSONString(buf, k); err != nil {
				return err
			}
			buf.WriteByte(':')
			if err := writeValue(buf, x.vals[k]); err != nil {
				return err
			}
		}
		buf.WriteByte('}')
	case []any:
		buf.WriteByte('[')
		for i, item := range x {
			if i > 0 {
				buf.WriteByte(',')
			}
			if err := writeValue(buf, item); err != nil {
				return err
			}
		}
		buf.WriteByte(']')
	default:
		// Go-native values (float64, int, structs...) fall back to the
		// standard encoder.
		raw, err := json.Marshal(x)
		if err != nil {
			return err
		}
		buf.Write(raw)
	}
	return nil
}

func writeJSONString(buf *bytes.Buffer, s string) error {
	raw, err := json.Marshal(s)
	if err != nil {
		return err
	}
	buf.Write(raw)
	return nil
}

// --- typed accessors, mirroring Python's dict.get usage in handlers ---

// GetStr returns the string value of key, or "" when missing or not a
// string.
func GetStr(m *OMap, key string) string {
	v, ok := m.GetOK(key)
	if !ok {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}

// GetBool returns the bool value of key, or false. Numbers and strings
// are not coerced (the frontend sends real booleans).
func GetBool(m *OMap, key string) bool {
	v, _ := m.GetOK(key)
	b, _ := v.(bool)
	return b
}

// GetArr returns the array value of key, or nil.
func GetArr(m *OMap, key string) []any {
	v, _ := m.GetOK(key)
	arr, _ := v.([]any)
	return arr
}

// GetMap returns the object value of key, or nil.
func GetMap(m *OMap, key string) *OMap {
	v, _ := m.GetOK(key)
	mm, _ := v.(*OMap)
	return mm
}

// GetFloat returns the numeric value of key as float64, accepting
// json.Number and float64. The second result is false when the value is
// missing or not numeric.
func GetFloat(m *OMap, key string) (float64, bool) {
	v, ok := m.GetOK(key)
	if !ok || v == nil {
		return 0, false
	}
	switch x := v.(type) {
	case json.Number:
		f, err := x.Float64()
		if err != nil {
			return 0, false
		}
		return f, true
	case float64:
		return x, true
	case int:
		return float64(x), true
	case int64:
		return float64(x), true
	default:
		return 0, false
	}
}

// GetNumber returns the value as json.Number when it is one.
func GetNumber(m *OMap, key string) (json.Number, bool) {
	v, ok := m.GetOK(key)
	if !ok {
		return "", false
	}
	n, ok := v.(json.Number)
	return n, ok
}

// SetFloat stores a float with Python time.time()-style precision: the
// shortest decimal that round-trips, which matches what json.dumps
// wrote for the same value.
func SetFloat(m *OMap, key string, f float64) *OMap {
	return m.Set(key, Number(f))
}

// Number returns f as a json.Number in shortest round-trip form so
// stored floats never get reformatted by a marshal/unmarshal cycle.
// For the magnitudes this app stores (epoch seconds, durations) this
// matches Python's repr() output.
func Number(f float64) json.Number {
	return json.Number(fmt.Sprintf("%v", f))
}
