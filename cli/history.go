package main

import (
	"fmt"
	"math"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type historyModel struct {
	client  *Client
	data    *PriceHistoryOut
	err     string
	loading bool
	fetched bool
}

type historyLoadedMsg struct {
	data *PriceHistoryOut
	err  string
}

func newHistoryModel(c *Client) historyModel {
	return historyModel{client: c, loading: true}
}

func (m historyModel) Init() tea.Cmd {
	return m.fetch()
}

func (m historyModel) fetch() tea.Cmd {
	c := m.client
	return func() tea.Msg {
		h, err := c.GetHistory()
		if err != nil {
			return historyLoadedMsg{err: err.Error()}
		}
		return historyLoadedMsg{data: h}
	}
}

func (m historyModel) Update(msg tea.Msg) (historyModel, tea.Cmd) {
	switch msg := msg.(type) {
	case historyLoadedMsg:
		m.loading = false
		m.fetched = true
		m.data = msg.data
		m.err = msg.err
		return m, nil
	case tea.KeyMsg:
		if msg.String() == "r" {
			m.loading = true
			return m, m.fetch()
		}
	}
	return m, nil
}

func (m historyModel) View() string {
	label := lipgloss.NewStyle().Foreground(lipgloss.Color("245"))
	errStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("203"))
	warnStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("214"))
	wdStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("245"))
	weStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("42"))

	if (m.loading && !m.fetched) || (!m.fetched && m.err == "") {
		return label.Render("Loading history…")
	}
	if m.err != "" {
		return errStyle.Render(m.err)
	}
	d := m.data

	max := 0.0
	for _, b := range d.Weekday {
		if b.AvgNOKPerKWh > max {
			max = b.AvgNOKPerKWh
		}
	}
	for _, b := range d.Weekend {
		if b.AvgNOKPerKWh > max {
			max = b.AvgNOKPerKWh
		}
	}

	var wd, we strings.Builder
	for _, b := range d.Weekday {
		wd.WriteString(wdStyle.Render(sparkChar(b.AvgNOKPerKWh, max)))
	}
	for _, b := range d.Weekend {
		we.WriteString(weStyle.Render(sparkChar(b.AvgNOKPerKWh, max)))
	}

	wdAvg := weightedMean(d.Weekday)
	weAvg := weightedMean(d.Weekend)
	summary := ""
	if !math.IsNaN(wdAvg) && !math.IsNaN(weAvg) {
		diff := weAvg - wdAvg
		cheaper := "weekends"
		if diff > 0 {
			cheaper = "weekdays"
		}
		summary = fmt.Sprintf(
			"Weekday avg %.3f  •  Weekend avg %.3f  →  %s are %.3f NOK/kWh cheaper",
			wdAvg, weAvg, cheaper, math.Abs(diff),
		)
	}

	out := "NO1 — Weekend vs Weekday, two complete Mon–Sun weeks\n\n"
	out += label.Render("Weekday ") + wd.String() + label.Render(fmt.Sprintf("   max %.3f", max)) + "\n"
	out += label.Render("Weekend ") + we.String() + "\n"
	out += label.Render("        ") + label.Render(hourAxis24()) + "\n\n"
	out += summary
	if len(d.MissingDays) > 0 {
		out += "\n" + warnStyle.Render("Excluded: "+strings.Join(d.MissingDays, ", "))
	}
	if m.loading {
		out += "\n" + label.Render("refreshing…")
	}
	return out
}

func weightedMean(buckets []HourBucket) float64 {
	total, count := 0.0, 0
	for _, b := range buckets {
		total += b.AvgNOKPerKWh * float64(b.Count)
		count += b.Count
	}
	if count == 0 {
		return math.NaN()
	}
	return total / float64(count)
}
