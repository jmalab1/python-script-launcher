package ordjson

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestParsePreservesKeyOrderAndNumberLiterals(t *testing.T) {
	// Keys are deliberately out of alphabetical order and numbers are
	// written in forms a plain float64 round-trip would rewrite.
	raw := `{"zebra":1.50,"apple":3.0,"mango":1e2}`

	v, err := Parse([]byte(raw))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}

	m, ok := v.(*OMap)
	if !ok {
		t.Fatalf("Parse of an object must return *OMap, got %T", v)
	}
	wantKeys := []string{"zebra", "apple", "mango"}
	if got := m.Keys(); !equalStrings(got, wantKeys) {
		t.Fatalf("Keys() = %v, want %v (original order, not sorted)", got, wantKeys)
	}

	out, err := Marshal(v)
	if err != nil {
		t.Fatalf("Marshal: %v", err)
	}
	if string(out) != raw {
		t.Fatalf("round trip = %s, want %s (order and numeric literals must survive)", out, raw)
	}
}

func TestParseNestedObjectsArraysAndPrimitives(t *testing.T) {
	raw := `{"name":"run","flag":true,"off":false,"none":null,"steps":[{"at":1.50,"cmds":["a","b",3.0]},[1,2]],"n":-7}`

	v, err := Parse([]byte(raw))
	if err != nil {
		t.Fatalf("Parse: %v", err)
	}

	out, err := Marshal(v)
	if err != nil {
		t.Fatalf("Marshal: %v", err)
	}
	if string(out) != raw {
		t.Fatalf("round trip = %s, want %s", out, raw)
	}

	m := v.(*OMap)
	nested := GetArr(m, "steps")
	if nested == nil || len(nested) != 2 {
		t.Fatalf("steps = %v, want two entries", nested)
	}
	first, ok := nested[0].(*OMap)
	if !ok {
		t.Fatalf("steps[0] = %T, want *OMap", nested[0])
	}
	if GetStr(first, "cmds") != "" {
		t.Error("GetStr on a non-string must be empty")
	}
	cmds := GetArr(first, "cmds")
	if len(cmds) != 3 {
		t.Fatalf("cmds = %v, want three entries", cmds)
	}
	if n := cmds[2]; n != json.Number("3.0") {
		t.Errorf("cmds[2] = %v (%T), want json.Number(\"3.0\")", n, n)
	}

	if _, ok := GetNumber(m, "n"); !ok {
		t.Error("n must decode as json.Number")
	}
}

func TestParseTopLevelPrimitives(t *testing.T) {
	cases := []struct {
		raw  string
		want any
	}{
		{`123`, json.Number("123")},
		{`1.25`, json.Number("1.25")},
		{`"hello"`, "hello"},
		{`true`, true},
		{`false`, false},
		{`null`, nil},
		{`[1,"a",null]`, []any{json.Number("1"), "a", nil}},
		{`[]`, []any{}},
		{`{}`, New()},
	}

	for _, c := range cases {
		v, err := Parse([]byte(c.raw))
		if err != nil {
			t.Errorf("Parse(%s): %v", c.raw, err)
			continue
		}
		if !equalAny(v, c.want) {
			t.Errorf("Parse(%s) = %#v, want %#v", c.raw, v, c.want)
		}
	}
}

func TestParseErrors(t *testing.T) {
	cases := []string{
		`{"a":}`,   // value missing after colon
		`{"a":1`,   // truncated object
		`{"a" 1}`,  // missing colon
		`not json`, // bare garbage
		``,         // empty input
	}

	for _, raw := range cases {
		if _, err := Parse([]byte(raw)); err == nil {
			t.Errorf("Parse(%q) = nil error, want failure", raw)
		}
	}

	// The stdlib decoder rejects a misplaced '}' or ']' before the
	// decode switch can see it, so the defensive "unexpected
	// delimiter" branch is exercised directly.
	for _, d := range []json.Delim{'}', ']'} {
		dec := json.NewDecoder(strings.NewReader(""))
		if _, err := decodeFromToken(dec, d); err == nil || !strings.Contains(err.Error(), "unexpected delimiter") {
			t.Errorf("decodeFromToken(%v) err = %v, want unexpected delimiter", d, err)
		}
	}

	// A bare closing delimiter at the start is rejected by the
	// standard decoder before that switch runs.
	if _, err := Parse([]byte(`}`)); err == nil {
		t.Error("Parse(}) must fail")
	}
	if _, err := Parse([]byte(`]`)); err == nil {
		t.Error("Parse(]) must fail")
	}
}

func TestMarshalFallbackGoTypes(t *testing.T) {
	type point struct {
		X int    `json:"x"`
		Y string `json:"y"`
	}

	cases := []struct {
		name string
		in   any
		want string
	}{
		{"nil", nil, "null"},
		{"true", true, "true"},
		{"false", false, "false"},
		{"string", "hi", `"hi"`},
		{"escaped string", "say \"hi\"\n", `"say \"hi\"\n"`},
		{"json.Number", json.Number("1.50"), "1.50"},
		{"int", 42, "42"},
		{"float64", 1.5, "1.5"},
		{"slice", []any{json.Number("1"), "a", nil}, `[1,"a",null]`},
		{"struct", point{X: 1, Y: "z"}, `{"x":1,"y":"z"}`},
		{"plain map", map[string]any{"k": 2}, `{"k":2}`},
	}

	for _, c := range cases {
		out, err := Marshal(c.in)
		if err != nil {
			t.Errorf("Marshal(%s): %v", c.name, err)
			continue
		}
		if string(out) != c.want {
			t.Errorf("Marshal(%s) = %s, want %s", c.name, out, c.want)
		}
	}
}

func TestMarshalUnsupportedTypeError(t *testing.T) {
	if _, err := Marshal(map[string]any{"ch": make(chan int)}); err == nil {
		t.Error("Marshal of an unsupported type must fail, not silently corrupt")
	}
}

func TestSetGetGetOKDeleteKeepOrder(t *testing.T) {
	m := New()

	m.Set("b", 1).Set("a", 2).Set("c", 3)
	if got := m.Keys(); !equalStrings(got, []string{"b", "a", "c"}) {
		t.Fatalf("Keys() = %v, want insertion order", got)
	}
	if m.Len() != 3 {
		t.Fatalf("Len() = %d, want 3", m.Len())
	}

	if v, ok := m.GetOK("a"); !ok || v != 2 {
		t.Fatalf("GetOK(a) = %v, %v", v, ok)
	}
	if v := m.Get("missing"); v != nil {
		t.Errorf("Get(missing) = %v, want nil", v)
	}
	if _, ok := m.GetOK("missing"); ok {
		t.Error("GetOK(missing) must report false")
	}

	// Overwriting an existing key must not move it.
	m.Set("b", 9)
	if got := m.Keys(); !equalStrings(got, []string{"b", "a", "c"}) {
		t.Fatalf("Keys() after re-set = %v, want unchanged order", got)
	}
	if v := m.Get("b"); v != 9 {
		t.Errorf("Get(b) = %v, want the overwritten 9", v)
	}

	// Deleting a middle key keeps the order of the rest.
	m.Delete("a")
	if got := m.Keys(); !equalStrings(got, []string{"b", "c"}) {
		t.Fatalf("Keys() after delete = %v, want [b c]", got)
	}
	if m.Len() != 2 {
		t.Fatalf("Len() after delete = %d, want 2", m.Len())
	}

	// Deleting a missing key is a no-op.
	m.Delete("nope")
	if got := m.Keys(); !equalStrings(got, []string{"b", "c"}) {
		t.Fatalf("Keys() after no-op delete = %v", got)
	}

	// Re-adding a deleted key lands at the end, like a Python dict.
	m.Set("a", 4)
	if got := m.Keys(); !equalStrings(got, []string{"b", "c", "a"}) {
		t.Fatalf("Keys() after re-add = %v, want [b c a]", got)
	}
}

func TestNilMapMethodsAreSafe(t *testing.T) {
	var m *OMap

	if v := m.Get("k"); v != nil {
		t.Errorf("nil Get = %v, want nil", v)
	}
	if _, ok := m.GetOK("k"); ok {
		t.Error("nil GetOK must report false")
	}
	if got := m.Keys(); got != nil {
		t.Errorf("nil Keys = %v, want nil", got)
	}
	if m.Len() != 0 {
		t.Errorf("nil Len = %d, want 0", m.Len())
	}
	if got := m.Clone(); got != nil {
		t.Errorf("nil Clone = %v, want nil", got)
	}
}

func TestCloneDeepCopyIndependence(t *testing.T) {
	m := New()
	m.Set("num", json.Number("1.50"))
	m.Set("nested", New().Set("deep", "original"))
	m.Set("arr", []any{New().Set("in-slice", "original"), json.Number("2")})

	c := m.Clone()
	if got := c.Keys(); !equalStrings(got, m.Keys()) {
		t.Fatalf("clone Keys = %v, want same order", got)
	}

	// Mutating the clone's nested map must not touch the original.
	GetMap(c, "nested").Set("deep", "changed")
	if got := GetStr(GetMap(m, "nested"), "deep"); got != "original" {
		t.Errorf("original nested value = %q, want %q (clone leaked)", got, "original")
	}

	// Same for the map nested inside the slice.
	GetArr(c, "arr")[0].(*OMap).Set("in-slice", "changed")
	if got := GetStr(GetArr(m, "arr")[0].(*OMap), "in-slice"); got != "original" {
		t.Errorf("original in-slice value = %q, want %q (clone leaked)", got, "original")
	}

	// Replacing a slice element in the clone must not touch the original.
	GetArr(c, "arr")[1] = json.Number("999")
	if got := GetArr(m, "arr")[1]; got != json.Number("2") {
		t.Errorf("original arr[1] = %v, want json.Number(\"2\") (clone leaked)", got)
	}
}

func TestTypedAccessors(t *testing.T) {
	m := New()
	m.Set("s", "text")
	m.Set("b-true", true)
	m.Set("b-false", false)
	m.Set("num", json.Number("2.5"))
	m.Set("not-num", "words")
	m.Set("arr", []any{json.Number("1")})
	m.Set("map", New().Set("k", "v"))
	m.Set("nil", nil)

	if got := GetStr(m, "s"); got != "text" {
		t.Errorf("GetStr = %q, want text", got)
	}
	if got := GetStr(m, "num"); got != "" {
		t.Errorf("GetStr on non-string = %q, want empty", got)
	}
	if got := GetStr(m, "missing"); got != "" {
		t.Errorf("GetStr missing = %q, want empty", got)
	}

	if !GetBool(m, "b-true") || GetBool(m, "b-false") {
		t.Error("GetBool must return the stored value")
	}
	if GetBool(m, "num") || GetBool(m, "s") || GetBool(m, "missing") {
		t.Error("GetBool must not coerce non-bool values")
	}

	if got := GetArr(m, "arr"); got == nil || len(got) != 1 {
		t.Errorf("GetArr = %v, want one entry", got)
	}
	if got := GetArr(m, "s"); got != nil {
		t.Errorf("GetArr on non-array = %v, want nil", got)
	}

	if got := GetMap(m, "map"); got == nil || GetStr(got, "k") != "v" {
		t.Errorf("GetMap = %v, want the stored map", got)
	}
	if got := GetMap(m, "s"); got != nil {
		t.Errorf("GetMap on non-map = %v, want nil", got)
	}

	floatCases := []struct {
		key  string
		want float64
		ok   bool
	}{
		{"num", 2.5, true},
		{"missing", 0, false},
		{"not-num", 0, false},
		{"nil", 0, false},
		{"s", 0, false},
	}
	for _, c := range floatCases {
		got, ok := GetFloat(m, c.key)
		if ok != c.ok || got != c.want {
			t.Errorf("GetFloat(%q) = %v, %v; want %v, %v", c.key, got, ok, c.want, c.ok)
		}
	}
	if got, ok := GetFloat(New().Set("f64", 3.5), "f64"); !ok || got != 3.5 {
		t.Errorf("GetFloat(float64) = %v, %v", got, ok)
	}
	if got, ok := GetFloat(New().Set("i", 7), "i"); !ok || got != 7 {
		t.Errorf("GetFloat(int) = %v, %v", got, ok)
	}
	if got, ok := GetFloat(New().Set("i64", int64(-2)), "i64"); !ok || got != -2 {
		t.Errorf("GetFloat(int64) = %v, %v", got, ok)
	}

	if n, ok := GetNumber(m, "num"); !ok || n != json.Number("2.5") {
		t.Errorf("GetNumber = %v, %v", n, ok)
	}
	if _, ok := GetNumber(m, "not-num"); ok {
		t.Error("GetNumber on a string must report false")
	}
	if _, ok := GetNumber(m, "missing"); ok {
		t.Error("GetNumber on a missing key must report false")
	}

	// A json.Number holding non-numeric text is not a usable float.
	if _, ok := GetFloat(New().Set("bad", json.Number("abc")), "bad"); ok {
		t.Error("GetFloat on a non-numeric json.Number must report false")
	}

	// Typed accessors on a nil map must be safe too.
	if GetStr(nil, "k") != "" || GetBool(nil, "k") || GetArr(nil, "k") != nil || GetMap(nil, "k") != nil {
		t.Error("typed accessors on nil map must return zero values")
	}
	if _, ok := GetFloat(nil, "k"); ok {
		t.Error("GetFloat on nil map must report false")
	}
}

func TestSetFloatAndNumberShortestForm(t *testing.T) {
	m := New()
	SetFloat(m, "t", 1.5)
	SetFloat(m, "d", 3.0)

	if n, ok := GetNumber(m, "t"); !ok || n != json.Number("1.5") {
		t.Errorf("SetFloat stored %v, want 1.5", n)
	}
	// 3.0 is written shortest-form, matching Python's repr().
	if n, ok := GetNumber(m, "d"); !ok || n != json.Number("3") {
		t.Errorf("SetFloat stored %v, want 3", n)
	}

	cases := []struct {
		f    float64
		want string
	}{
		{1.5, "1.5"},
		{3.0, "3"},
		{0.25, "0.25"},
		{100000, "100000"},
		{-7.75, "-7.75"},
	}
	for _, c := range cases {
		if got := Number(c.f); got != json.Number(c.want) {
			t.Errorf("Number(%v) = %q, want %q", c.f, got, c.want)
		}
	}
}

func equalStrings(got, want []string) bool {
	if len(got) != len(want) {
		return false
	}
	for i := range got {
		if got[i] != want[i] {
			return false
		}
	}
	return true
}

func equalAny(a, b any) bool {
	switch x := a.(type) {
	case *OMap:
		y, ok := b.(*OMap)
		if !ok || x.Len() != y.Len() {
			return false
		}
		for _, k := range x.Keys() {
			if !equalAny(x.Get(k), y.Get(k)) {
				return false
			}
		}
		return true
	case []any:
		y, ok := b.([]any)
		if !ok || len(x) != len(y) {
			return false
		}
		for i := range x {
			if !equalAny(x[i], y[i]) {
				return false
			}
		}
		return true
	default:
		return a == b
	}
}
