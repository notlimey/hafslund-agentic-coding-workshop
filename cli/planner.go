package main

import (
	"errors"
	"fmt"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

var areas = []string{"NO1", "NO2", "NO3", "NO4", "NO5"}

type plannerModel struct {
	client     *Client
	area       string
	day        time.Time
	hours      int
	awayStart  string
	awayEnd    string
	prices     *PricesOut
	window     *ChargeWindow
	windowMiss bool
	err        string
	loading    bool
}

type plannerLoadedMsg struct {
	prices     *PricesOut
	window     *ChargeWindow
	windowMiss bool
	err        string
}

func newPlannerModel(c *Client, area string, hours int, awayStart, awayEnd string, today time.Time) plannerModel {
	return plannerModel{
		client:    c,
		area:      area,
		day:       today,
		hours:     hours,
		awayStart: awayStart,
		awayEnd:   awayEnd,
		loading:   true,
	}
}

func (m plannerModel) Init() tea.Cmd {
	return m.fetch()
}

func (m plannerModel) fetch() tea.Cmd {
	area, day, hours := m.area, m.day.Format("2006-01-02"), m.hours
	ws, we := m.awayStart, m.awayEnd
	c := m.client
	return func() tea.Msg {
		msg := plannerLoadedMsg{}
		prices, err := c.GetPrices(area, day)
		if err != nil {
			msg.err = fmt.Sprintf("prices: %v", err)
			return msg
		}
		msg.prices = prices
		if !prices.Published {
			return msg
		}
		win, err := c.GetCheapest(area, hours, day, ws, we)
		if err != nil {
			var nf NotFoundError
			if errors.As(err, &nf) {
				msg.windowMiss = true
				return msg
			}
			msg.err = fmt.Sprintf("cheapest: %v", err)
			return msg
		}
		msg.window = win
		return msg
	}
}

func (m plannerModel) Update(msg tea.Msg) (plannerModel, tea.Cmd) {
	switch msg := msg.(type) {
	case plannerLoadedMsg:
		m.loading = false
		m.err = msg.err
		m.prices = msg.prices
		m.window = msg.window
		m.windowMiss = msg.windowMiss
		return m, nil
	case tea.KeyMsg:
		switch msg.String() {
		case "a":
			m.area = nextArea(m.area, +1)
			m.loading = true
			return m, m.fetch()
		case "A":
			m.area = nextArea(m.area, -1)
			m.loading = true
			return m, m.fetch()
		case "[":
			m.day = m.day.AddDate(0, 0, -1)
			m.loading = true
			return m, m.fetch()
		case "]":
			m.day = m.day.AddDate(0, 0, 1)
			m.loading = true
			return m, m.fetch()
		case "-", "_":
			if m.hours > 1 {
				m.hours--
				m.loading = true
				return m, m.fetch()
			}
		case "+", "=":
			if m.hours < 12 {
				m.hours++
				m.loading = true
				return m, m.fetch()
			}
		case "r":
			m.loading = true
			return m, m.fetch()
		}
	}
	return m, nil
}

func nextArea(cur string, delta int) string {
	for i, a := range areas {
		if a == cur {
			return areas[(i+delta+len(areas))%len(areas)]
		}
	}
	return areas[0]
}

func (m plannerModel) View() string {
	label := lipgloss.NewStyle().Foreground(lipgloss.Color("245"))
	val := lipgloss.NewStyle().Bold(true)
	errStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("203"))

	away := "off"
	if m.awayStart != "" && m.awayEnd != "" {
		away = m.awayStart + "–" + m.awayEnd
	}
	inputs := fmt.Sprintf(
		"%s %s   %s %s   %s %s   %s %s",
		label.Render("Area:"), val.Render(m.area),
		label.Render("Day:"), val.Render(m.day.Format("2006-01-02")),
		label.Render("Hours:"), val.Render(fmt.Sprintf("%d", m.hours)),
		label.Render("Away:"), val.Render(away),
	)
	keys := label.Render("a/A area  •  [/] day  •  -/+ hours  •  r refresh")

	var body string
	switch {
	case m.loading && m.prices == nil:
		body = label.Render("Loading…")
	case m.err != "":
		body = errStyle.Render(m.err)
	case m.prices == nil:
		body = label.Render("No data.")
	case !m.prices.Published:
		body = label.Render(fmt.Sprintf(
			"Prices for %s in %s are not published yet — try after 13:00 CET.",
			m.prices.Date, m.area,
		))
	default:
		body = renderRecommendation(m) + "\n\n" + renderPriceSparkline(m.prices.Prices, m.window)
	}

	if m.loading && m.prices != nil {
		body += "\n" + label.Render("refreshing…")
	}
	return inputs + "\n" + keys + "\n\n" + body
}

func renderRecommendation(m plannerModel) string {
	switch {
	case m.windowMiss:
		return fmt.Sprintf("No %dh window fits — widen availability or shorten the charge.", m.hours)
	case m.window != nil:
		return fmt.Sprintf(
			"Charge %s from %s to %s — avg %.3f NOK/kWh (%dh).",
			m.area,
			m.window.Start.Local().Format("15:04"),
			m.window.End.Local().Format("15:04"),
			m.window.AvgNOKPerKWh, m.window.Hours,
		)
	}
	return ""
}

func renderPriceSparkline(prices []HourPrice, win *ChargeWindow) string {
	if len(prices) == 0 {
		return ""
	}
	max := 0.0
	for _, p := range prices {
		if p.NOKPerKWh > max {
			max = p.NOKPerKWh
		}
	}
	defaultStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("245"))
	winStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("42")).Bold(true)
	axisStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("245"))

	var winStart, winEnd int64
	if win != nil {
		winStart = win.Start.Unix()
		winEnd = win.End.Unix()
	}
	var bars strings.Builder
	for _, p := range prices {
		ch := sparkChar(p.NOKPerKWh, max)
		if win != nil && p.TimeStart.Unix() >= winStart && p.TimeStart.Unix() < winEnd {
			bars.WriteString(winStyle.Render(ch))
		} else {
			bars.WriteString(defaultStyle.Render(ch))
		}
	}
	scale := defaultStyle.Render(fmt.Sprintf("  max %.3f NOK/kWh", max))
	return bars.String() + scale + "\n" + axisStyle.Render(hourAxis24())
}
