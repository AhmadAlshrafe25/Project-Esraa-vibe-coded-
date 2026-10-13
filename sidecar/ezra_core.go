package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"runtime"
	"strings"
	"time"
)

// SystemMetrics holds sub-millisecond hardware & OS diagnostics.
type SystemMetrics struct {
	OS          string   `json:"os"`
	Arch        string   `json:"arch"`
	NumCPU      int      `json:"num_cpu"`
	Timestamp   string   `json:"timestamp"`
	Uptime      string   `json:"uptime,omitempty"`
	Distro      string   `json:"distro"`
	Status      string   `json:"status"`
}

func detectDistro() string {
	data, err := os.ReadFile("/etc/os-release")
	if err != nil {
		return "Linux Generic"
	}
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		if strings.HasPrefix(line, "PRETTY_NAME=") {
			return strings.Trim(strings.TrimPrefix(line, "PRETTY_NAME="), "\"")
		}
	}
	return "Linux"
}

func getMetrics() SystemMetrics {
	distro := detectDistro()
	return SystemMetrics{
		OS:        runtime.GOOS,
		Arch:      runtime.GOARCH,
		NumCPU:    runtime.NumCPU(),
		Timestamp: time.Now().Format("2006-01-02 15:04:05"),
		Distro:    distro,
		Status:    "operational",
	}
}

func main() {
	mode := flag.String("mode", "status", "Mode of operation: status | ping | distro")
	flag.Parse()

	switch *mode {
	case "ping":
		fmt.Println("pong")
	case "distro":
		fmt.Println(detectDistro())
	case "status":
		metrics := getMetrics()
		b, err := json.MarshalIndent(metrics, "", "  ")
		if err != nil {
			fmt.Printf(`{"status":"error","message":"%s"}`+"\n", err)
			return
		}
		fmt.Println(string(b))
	default:
		fmt.Println(`{"status":"error","message":"unknown mode"}`)
	}
}
