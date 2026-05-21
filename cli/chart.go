package main

import (
	"fmt"
	"math"
)

// 0/8 .. 8/8 cell-fill block runes — gives 9 visible levels in one row.
var sparkRunes = []rune{' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'}

func sparkChar(v, max float64) string {
	if max <= 0 {
		return " "
	}
	f := v / max
	if f < 0 {
		f = 0
	}
	if f > 1 {
		f = 1
	}
	return string(sparkRunes[int(math.Round(f*8))])
}

// hourAxis24 produces a 24-character-wide axis labeled at 0, 6, 12, 18, 23
// so it lines up under a 24-rune sparkline.
func hourAxis24() string {
	buf := make([]byte, 24)
	for i := range buf {
		buf[i] = ' '
	}
	for _, h := range []int{0, 6, 12, 18, 23} {
		pos := h
		if pos+2 > 24 {
			pos = 22
		}
		copy(buf[pos:], fmt.Sprintf("%02d", h))
	}
	return string(buf)
}
