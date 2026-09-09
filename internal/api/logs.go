package api

import (
	"os"
	"strconv"
	"strings"

	"launchcontrol/internal/ordjson"
)

// Log tailing defaults, matching the Python logs module.
const (
	defaultLogLines = 500
	maxLogLines     = 5000
)

// TailLogs serves the Logs panel. Two read modes share the endpoint:
// a full tail (no `after`) returning the last `lines` complete lines,
// and an incremental read from a byte offset returning only lines
// appended since then. A trailing unterminated line is withheld and
// next_offset never advances past complete lines, so no partial or
// duplicated lines reach the client. When the file has shrunk (rotated
// or truncated) the handler falls back to a full tail with reset:true.
func (a *API) TailLogs(linesRaw string, afterRaw *string) *ordjson.OMap {
	path := a.LogPath
	info, err := os.Stat(path)
	if err != nil {
		return ordjson.New().Set("entries", []any{}).Set("next_offset", 0).Set("reset", true)
	}
	size := info.Size()

	lines := defaultLogLines
	if n, err := strconv.Atoi(linesRaw); err == nil {
		lines = n
	}
	if lines < 1 {
		lines = 1
	}
	if lines > maxLogLines {
		lines = maxLogLines
	}

	if afterRaw != nil {
		if offset, err := strconv.ParseInt(*afterRaw, 10, 64); err == nil && offset >= 0 && offset <= size {
			return a.readLogsFrom(path, size, offset)
		}
	}
	return a.readLogsTail(path, size, lines)
}

func (a *API) readLogsTail(path string, size int64, lines int) *ordjson.OMap {
	data := readLogBytes(path, 0, size)
	completed, nextOffset := splitCompleteLines(data, 0)
	start := 0
	if len(completed) > lines {
		start = len(completed) - lines
	}
	return ordjson.New().
		Set("entries", toStringsAnyStrings(completed[start:])).
		Set("next_offset", nextOffset).
		Set("reset", true)
}

func (a *API) readLogsFrom(path string, size, offset int64) *ordjson.OMap {
	data := readLogBytes(path, offset, size-offset)
	completed, nextOffset := splitCompleteLines(data, offset)
	start := 0
	if len(completed) > maxLogLines {
		start = len(completed) - maxLogLines
	}
	return ordjson.New().
		Set("entries", toStringsAnyStrings(completed[start:])).
		Set("next_offset", nextOffset).
		Set("reset", false)
}

func readLogBytes(path string, start, length int64) []byte {
	if length <= 0 {
		return nil
	}

	f, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer f.Close()
	if start > 0 {
		if _, err := f.Seek(start, 0); err != nil {
			return nil
		}
	}
	buf := make([]byte, length)
	n, _ := f.Read(buf)
	return buf[:n]
}

// splitCompleteLines decodes a byte chunk into complete lines, keeping
// the offset just past the last newline. A trailing partial line is
// withheld; "\r\n" line endings lose the carriage return.
func splitCompleteLines(data []byte, base int64) ([]string, int64) {
	lastNL := lastByte(data, '\n')
	if lastNL < 0 {
		return nil, base
	}

	text := strings.ToValidUTF8(string(data[:lastNL+1]), "\uFFFD")
	lines := strings.Split(text, "\n")
	// Drop the empty piece after the final newline.
	lines = lines[:len(lines)-1]
	out := make([]string, len(lines))
	for i, line := range lines {
		out[i] = strings.TrimSuffix(line, "\r")
	}
	return out, base + int64(lastNL) + 1
}

func lastByte(data []byte, b byte) int {
	for i := len(data) - 1; i >= 0; i-- {
		if data[i] == b {
			return i
		}
	}
	return -1
}

func toStringsAnyStrings(lines []string) []any {
	out := make([]any, len(lines))
	for i, l := range lines {
		out[i] = l
	}
	return out
}
