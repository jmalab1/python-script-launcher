//go:build windows

package api

import (
	"golang.org/x/sys/windows"

	"launchcontrol/internal/ordjson"
)

// listDrives enumerates the available drive letters via
// GetLogicalDrives, mirroring the Python ctypes call.
func listDrives() []any {
	bitmask, err := windows.GetLogicalDrives()
	if err != nil {
		return nil
	}
	drives := []any{}
	for i, letter := range "ABCDEFGHIJKLMNOPQRSTUVWXYZ" {
		if bitmask>>uint(i)&1 != 0 {
			drives = append(drives, ordjson.New().
				Set("name", string(letter)+":").
				Set("path", string(letter)+":\\").
				Set("is_dir", true))
		}
	}
	return drives
}
