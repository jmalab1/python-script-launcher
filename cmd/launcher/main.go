// Command launcher is Launch Control's compiled server: port of
// launcher.py's main(), with the same defaults (127.0.0.1:8765,
// auto-open browser on Windows, graceful Ctrl+C shutdown).
//
// By default it detaches into the background so closing the terminal
// keeps the app running: ./launchctl starts it, ./launchctl -stop stops
// it; -foreground opts out of detaching. In background mode every
// launch - fresh start or restart - also opens the browser.
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"launchcontrol/internal/api"
	"launchcontrol/internal/applog"
	"launchcontrol/internal/config"
	"launchcontrol/internal/daemon"
	"launchcontrol/internal/pythonrt"
	"launchcontrol/internal/runner"
	"launchcontrol/internal/scheduler"
	"launchcontrol/internal/store"
)

const detachTimeout = 10 * time.Second

func main() {
	port := flag.Int("port", config.DefaultPort, "listen port (0 picks a free port)")
	foreground := flag.Bool("foreground", false, "stay attached to this terminal instead of running in the background")
	stopFlag := flag.Bool("stop", false, "stop a background instance started earlier")
	childFlag := flag.Bool("_child", false, "internal: this process IS the detached server")
	// Set by the parent on a fresh start (no instance was replaced) so
	// the detached child opens the browser once it is serving.
	browserFlag := flag.Bool("_browser", false, "internal: open the browser after the detached server is up")
	flag.Parse()

	dataDir := config.DataDir()

	if *stopFlag {
		stopped, err := daemon.Stop(*port)
		switch {
		case err != nil:
			fmt.Println("Could not stop the server:", err)
		case !stopped:
			fmt.Println("No background instance is running.")
		default:
			fmt.Println("Server stopped.")
		}
		return
	}

	// The detached child (and -foreground runs) just serve; the parent
	// process handles daemonising. The child opens the browser when the
	// parent asked it to.
	if *childFlag || *foreground {
		serve(*port, dataDir, *browserFlag)
		return
	}

	// Default: detach, replacing any earlier background instance first
	// so "run the command" always means "restart it".
	if *port == 0 {
		fmt.Println("Port 0 (auto) only works with -foreground; pick a real port for background mode.")
		os.Exit(1)
	}

	replacePrevious(*port)
	exe, err := os.Executable()
	if err != nil {
		fmt.Println("Cannot locate the executable:", err)
		os.Exit(1)
	}

	childPID, err := daemon.StartDetached(
		exe, buildChildArgs(*port), os.Environ(), detachTimeout,
		func() bool { return daemon.PortOpen(*port) },
	)
	if err != nil {
		fmt.Println("Failed to start:", err)
		os.Exit(1)
	}
	if err := daemon.RecordPID(*port, childPID); err != nil {
		slog.Warn("Could not record the server PID file", "err", err)
	}

	fmt.Printf("Launch Control running in the background (PID %d) at http://127.0.0.1:%d\n", childPID, *port)
	fmt.Println("  - log: data/server.log (tail with: tail -f data/server.log)")
	fmt.Println("  - stop it with: ./dist/launchctl -stop")
}

// replacePrevious frees the port so a fresh instance can take over:
// running the launcher again stops the previous background instance
// first. A port held by some other program is never touched.
func replacePrevious(port int) {
	if !daemon.PortOpen(port) {
		return
	}
	if pid, ok := daemon.IsRunning(port); ok {
		fmt.Printf("Stopping previous instance (PID %d)...\n", pid)
		if _, err := daemon.Stop(port); err != nil {
			fmt.Println("Could not stop the previous instance:", err)
			os.Exit(1)
		}
		// Wait for the kernel to release the port.
		for i := 0; i < 20 && daemon.PortOpen(port); i++ {
			time.Sleep(100 * time.Millisecond)
		}
		if daemon.PortOpen(port) {
			fmt.Println("Previous instance did not release the port in time - not starting.")
			os.Exit(1)
		}
		return
	}
	fmt.Printf("Port %d is already in use by another program - not starting.\n", port)
	os.Exit(1)
}

// buildChildArgs assembles the detached child's command line. The
// browser flag is always passed down so every launch (including a
// restart over a previous instance) opens the UI.
func buildChildArgs(port int) []string {
	return []string{"-port", strconv.Itoa(port), "-_child", "-_browser"}
}

// serve is the detached/foreground server: logging, database,
// scheduler and the HTTP listener, stopped cleanly on Ctrl+C. When
// openUI is set it opens the browser shortly after the server is up.
func serve(port int, dataDir string, openUI bool) {
	// One-time adoption: earlier builds kept their data next to the
	// executable; move it onto the per-user state location before
	// anything else touches it.
	config.AdoptLegacyDataDir()
	rotator := applog.Setup(config.LogFile(), config.LogMaxBytes, config.LogBackupCount)
	if rotator != nil {
		defer rotator.Close()
	}

	if err := os.MkdirAll(dataDir, 0o750); err != nil {
		slog.Error("Cannot create data directory", "dir", dataDir, "err", err)
		shutdown(1)
	}

	db, err := store.Open(config.DBPath(), dataDir)
	if err != nil {
		slog.Error("Cannot open database", "path", config.DBPath(), "err", err)
		shutdown(1)
	}
	defer db.Close()

	runs := runner.NewManager(db, func() (string, error) {
		return pythonrt.Resolve()
	})
	sched := scheduler.New(db, runs)

	listener, err := net.Listen("tcp", net.JoinHostPort("127.0.0.1", fmt.Sprint(port)))
	if err != nil {
		slog.Error("Could not start server on port", "port", port, "err", err)
		slog.Error("Is another instance of Launch Control already running?")
		shutdown(1)
	}
	defer listener.Close()
	portNum := listener.Addr().(*net.TCPAddr).Port

	server := newServer(api.New(db, runs, sched, dataDir, config.LogFile()))

	// The scheduler starts only once the server is bound, mirroring the
	// Python main().
	sched.Start()
	defer sched.Stop()

	slog.Info(fmt.Sprintf("Launch Control running at http://127.0.0.1:%d", portNum))
	slog.Info("Press Ctrl+C to stop.")

	if openUI {
		// Open the browser shortly after the server is reachable, like
		// the Python timer did.
		go func() {
			time.Sleep(1 * time.Second)
			openBrowser(fmt.Sprintf("http://127.0.0.1:%d", portNum))
		}()
	}

	// Serve on the main goroutine, stopping on Ctrl+C.
	go func() {
		sig := make(chan os.Signal, 1)
		signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
		<-sig
		slog.Info("Shutting down.")
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		// Shutdown's error (e.g. the 5s timeout expiring) does not change
		// the exit path, so the error is deliberately dropped.
		_ = server.Shutdown(ctx)
	}()
	if err := server.Serve(listener); err != nil && err != http.ErrServerClosed {
		slog.Error("Server error", "err", err)
		shutdown(1)
	}
}

// shutdown exits without leaving the Windows console reader hanging.
func shutdown(code int) {
	os.Exit(code)
}

// newServer builds the HTTP server with a header read timeout so slow
// clients cannot tie up connections forever (Slowloris-style).
func newServer(handler http.Handler) *http.Server {
	return &http.Server{
		Handler:           handler,
		ReadHeaderTimeout: 10 * time.Second,
	}
}
