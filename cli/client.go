package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

type Client struct {
	baseURL string
	http    *http.Client
}

func NewClient(baseURL string) *Client {
	return &Client{baseURL: baseURL, http: &http.Client{Timeout: 30 * time.Second}}
}

type HourPrice struct {
	NOKPerKWh float64   `json:"NOK_per_kWh"`
	TimeStart time.Time `json:"time_start"`
	TimeEnd   time.Time `json:"time_end"`
}

type PricesOut struct {
	Area      string      `json:"area"`
	Date      string      `json:"date"`
	Published bool        `json:"published"`
	Prices    []HourPrice `json:"prices"`
}

type ChargeWindow struct {
	Area           string    `json:"area"`
	Hours          int       `json:"hours"`
	Start          time.Time `json:"start"`
	End            time.Time `json:"end"`
	AvgNOKPerKWh   float64   `json:"avg_NOK_per_kWh"`
	TotalNOKPerKWh float64   `json:"total_NOK_per_kWh"`
}

type HourBucket struct {
	Hour         int     `json:"hour"`
	AvgNOKPerKWh float64 `json:"avg_NOK_per_kWh"`
	Count        int     `json:"count"`
}

type PriceHistoryOut struct {
	Weekday     []HourBucket `json:"weekday"`
	Weekend     []HourBucket `json:"weekend"`
	MissingDays []string     `json:"missing_days"`
}

// NotFoundError signals an HTTP 404 from the backend — callers may treat this
// as "no result" rather than a transport failure (e.g. cheapest window when
// every hour is blocked by the away-range).
type NotFoundError struct{ path string }

func (e NotFoundError) Error() string { return "404: " + e.path }

func (c *Client) GetPrices(area, day string) (*PricesOut, error) {
	q := url.Values{}
	q.Set("area", area)
	if day != "" {
		q.Set("day", day)
	}
	return doGet[PricesOut](c, "/api/prices?"+q.Encode())
}

func (c *Client) GetCheapest(area string, hours int, day, awayStart, awayEnd string) (*ChargeWindow, error) {
	q := url.Values{}
	q.Set("area", area)
	q.Set("hours", strconv.Itoa(hours))
	if day != "" {
		q.Set("day", day)
	}
	if awayStart != "" && awayEnd != "" {
		q.Set("away_start", awayStart)
		q.Set("away_end", awayEnd)
	}
	return doGet[ChargeWindow](c, "/api/prices/cheapest?"+q.Encode())
}

func (c *Client) GetHistory() (*PriceHistoryOut, error) {
	return doGet[PriceHistoryOut](c, "/api/prices/history")
}

func doGet[T any](c *Client, path string) (*T, error) {
	resp, err := c.http.Get(c.baseURL + path)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return nil, NotFoundError{path: path}
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %d from %s", resp.StatusCode, path)
	}
	var out T
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}
