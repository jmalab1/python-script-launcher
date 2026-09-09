// Package assets embeds the frontend so a compiled binary is fully
// self-contained: index.html and everything under static/ are baked in
// at build time.
package assets

import (
	"embed"
	"io/fs"
)

//go:embed index.html
var indexHTML []byte

//go:embed all:static
var staticFS embed.FS

// IndexHTML returns the raw index.html bytes.
func IndexHTML() []byte { return indexHTML }

// Static returns the embedded static/ tree rooted at "static".
func Static() fs.FS {
	sub, err := fs.Sub(staticFS, "static")
	if err != nil {
		// Cannot happen: "static" is embedded above.
		panic(err)
	}
	return sub
}
