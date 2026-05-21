package main

import (
	"flag"
	"fmt"
	"os"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	backendURL := flag.String("backend", "http://localhost:8000", "Backend base URL")
	area := flag.String("area", "NO1", "Default price area (NO1..NO5)")
	hours := flag.Int("hours", 4, "Default charge duration in hours")
	awayStart := flag.String("away-start", "", "Away start HH:MM (optional)")
	awayEnd := flag.String("away-end", "", "Away end HH:MM (optional)")
	flag.Parse()

	client := NewClient(*backendURL)
	m := newRootModel(client, *area, *hours, *awayStart, *awayEnd, time.Now())

	if _, err := tea.NewProgram(m, tea.WithAltScreen()).Run(); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
