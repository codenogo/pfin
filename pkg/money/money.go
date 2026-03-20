package money

import (
	"fmt"

	"github.com/codenogo/pfin/pkg/currency"
	"github.com/shopspring/decimal"
)

// Money is an immutable value object representing a monetary amount with currency.
type Money struct {
	amount   decimal.Decimal
	currency currency.Currency
}

// New creates a Money from a decimal and currency.
func New(amount decimal.Decimal, c currency.Currency) Money {
	return Money{amount: amount, currency: c}
}

// NewFromString creates a Money from a string amount and currency.
func NewFromString(amount string, c currency.Currency) (Money, error) {
	d, err := decimal.NewFromString(amount)
	if err != nil {
		return Money{}, fmt.Errorf("invalid money amount %q: %w", amount, err)
	}
	return Money{amount: d, currency: c}, nil
}

// NewFromInt creates a Money from an integer amount (in minor units, e.g., cents) and currency.
func NewFromInt(minorUnits int64, c currency.Currency) Money {
	d := decimal.New(minorUnits, -2)
	return Money{amount: d, currency: c}
}

// Zero returns a zero-value Money in the given currency.
func Zero(c currency.Currency) Money {
	return Money{amount: decimal.Zero, currency: c}
}

// Amount returns the underlying decimal amount.
func (m Money) Amount() decimal.Decimal {
	return m.amount
}

// Currency returns the currency.
func (m Money) Currency() currency.Currency {
	return m.currency
}

// Add returns the sum of two Money values. Currencies must match.
func (m Money) Add(other Money) (Money, error) {
	if m.currency != other.currency {
		return Money{}, fmt.Errorf("cannot add %s and %s", m.currency, other.currency)
	}
	return Money{amount: m.amount.Add(other.amount), currency: m.currency}, nil
}

// Sub returns the difference. Currencies must match.
func (m Money) Sub(other Money) (Money, error) {
	if m.currency != other.currency {
		return Money{}, fmt.Errorf("cannot subtract %s from %s", other.currency, m.currency)
	}
	return Money{amount: m.amount.Sub(other.amount), currency: m.currency}, nil
}

// Mul returns the product of this Money and a scalar.
func (m Money) Mul(factor decimal.Decimal) Money {
	return Money{amount: m.amount.Mul(factor), currency: m.currency}
}

// Negate returns the negated amount.
func (m Money) Negate() Money {
	return Money{amount: m.amount.Neg(), currency: m.currency}
}

// IsZero returns true if the amount is zero.
func (m Money) IsZero() bool {
	return m.amount.IsZero()
}

// IsNegative returns true if the amount is less than zero.
func (m Money) IsNegative() bool {
	return m.amount.IsNegative()
}

// Equal returns true if both amount and currency match.
func (m Money) Equal(other Money) bool {
	return m.currency == other.currency && m.amount.Equal(other.amount)
}

// String returns a formatted representation like "100.00 USD".
func (m Money) String() string {
	return m.amount.StringFixed(2) + " " + m.currency.String()
}
