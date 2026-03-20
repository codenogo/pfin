package currency

import "fmt"

// Currency represents an ISO 4217 currency code.
type Currency string

const (
	USD Currency = "USD"
	EUR Currency = "EUR"
	GBP Currency = "GBP"
	KES Currency = "KES"
	JPY Currency = "JPY"
	CAD Currency = "CAD"
	AUD Currency = "AUD"
	CHF Currency = "CHF"
	CNY Currency = "CNY"
	INR Currency = "INR"
	NGN Currency = "NGN"
	ZAR Currency = "ZAR"
	BRL Currency = "BRL"
	MXN Currency = "MXN"
)

var valid = map[Currency]bool{
	USD: true, EUR: true, GBP: true, KES: true, JPY: true,
	CAD: true, AUD: true, CHF: true, CNY: true, INR: true,
	NGN: true, ZAR: true, BRL: true, MXN: true,
}

// Parse validates and returns a Currency from a string.
func Parse(s string) (Currency, error) {
	c := Currency(s)
	if !valid[c] {
		return "", fmt.Errorf("invalid currency: %q", s)
	}
	return c, nil
}

// IsValid returns true if the currency code is recognized.
func (c Currency) IsValid() bool {
	return valid[c]
}

// String returns the 3-letter ISO 4217 code.
func (c Currency) String() string {
	return string(c)
}
