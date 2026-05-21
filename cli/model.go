package main

import (
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type view int

const (
	viewPlanner view = iota
	viewHistory
)

type rootModel struct {
	view    view
	planner plannerModel
	history historyModel
}

func newRootModel(c *Client, area string, hours int, awayStart, awayEnd string, today time.Time) rootModel {
	return rootModel{
		view:    viewPlanner,
		planner: newPlannerModel(c, area, hours, awayStart, awayEnd, today),
		history: newHistoryModel(c),
	}
}

func (m rootModel) Init() tea.Cmd {
	return tea.Batch(m.planner.Init(), m.history.Init())
}

func (m rootModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	if key, ok := msg.(tea.KeyMsg); ok {
		switch key.String() {
		case "ctrl+c", "q":
			return m, tea.Quit
		case "tab":
			m.view = (m.view + 1) % 2
			return m, nil
		case "1":
			m.view = viewPlanner
			return m, nil
		case "2":
			m.view = viewHistory
			return m, nil
		}
	}

	// Route everything else (including loaded-data messages) to both sub-models
	// so an async response that arrives while the other tab is active still
	// updates the right state.
	var cmds []tea.Cmd
	var c tea.Cmd
	m.planner, c = m.planner.Update(msg)
	cmds = append(cmds, c)
	m.history, c = m.history.Update(msg)
	cmds = append(cmds, c)
	return m, tea.Batch(cmds...)
}

func (m rootModel) View() string {
	var body string
	switch m.view {
	case viewPlanner:
		body = m.planner.View()
	case viewHistory:
		body = m.history.View()
	}
	return tabsView(m.view) + "\n\n" + body + "\n\n" + helpView()
}

func tabsView(active view) string {
	activeStyle := lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("15")).
		Background(lipgloss.Color("28")).
		Padding(0, 2)
	inactiveStyle := lipgloss.NewStyle().
		Foreground(lipgloss.Color("245")).
		Padding(0, 2)
	tabs := []string{"Planner [1]", "History [2]"}
	rendered := make([]string, len(tabs))
	for i, t := range tabs {
		if int(active) == i {
			rendered[i] = activeStyle.Render(t)
		} else {
			rendered[i] = inactiveStyle.Render(t)
		}
	}
	return strings.Join(rendered, " ")
}

func helpView() string {
	return lipgloss.NewStyle().
		Foreground(lipgloss.Color("245")).
		Render("tab/1/2 switch view  •  r refresh  •  q quit")
}
