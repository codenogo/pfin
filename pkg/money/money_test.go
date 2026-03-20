package money

import (
	"testing"

	"github.com/codenogo/pfin/pkg/currency"
	"github.com/shopspring/decimal"
)

func TestNewFromString(t *testing.T) {
	m, err := NewFromString("100.50", currency.USD)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if m.String() != "100.50 USD" {
		t.Errorf("got %q, want %q", m.String(), "100.50 USD")
	}
}

func TestNewFromString_Invalid(t *testing.T) {
	_, err := NewFromString("not-a-number", currency.USD)
	if err == nil {
		t.Error("expected error for invalid amount")
	}
}

func TestNewFromInt(t *testing.T) {
	m := NewFromInt(1050, currency.USD)
	if m.String() != "10.50 USD" {
		t.Errorf("got %q, want %q", m.String(), "10.50 USD")
	}
}

func TestAdd(t *testing.T) {
	a, _ := NewFromString("50.00", currency.USD)
	b, _ := NewFromString("30.25", currency.USD)
	sum, err := a.Add(b)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if sum.String() != "80.25 USD" {
		t.Errorf("got %q, want %q", sum.String(), "80.25 USD")
	}
}

func TestAdd_CurrencyMismatch(t *testing.T) {
	a, _ := NewFromString("50.00", currency.USD)
	b, _ := NewFromString("30.00", currency.EUR)
	_, err := a.Add(b)
	if err == nil {
		t.Error("expected error for currency mismatch")
	}
}

func TestSub(t *testing.T) {
	a, _ := NewFromString("100.00", currency.USD)
	b, _ := NewFromString("30.50", currency.USD)
	diff, err := a.Sub(b)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if diff.String() != "69.50 USD" {
		t.Errorf("got %q, want %q", diff.String(), "69.50 USD")
	}
}

func TestMul(t *testing.T) {
	m, _ := NewFromString("10.00", currency.USD)
	result := m.Mul(decimal.NewFromInt(3))
	if result.String() != "30.00 USD" {
		t.Errorf("got %q, want %q", result.String(), "30.00 USD")
	}
}

func TestNegate(t *testing.T) {
	m, _ := NewFromString("50.00", currency.USD)
	neg := m.Negate()
	if neg.String() != "-50.00 USD" {
		t.Errorf("got %q, want %q", neg.String(), "-50.00 USD")
	}
}

func TestIsZero(t *testing.T) {
	z := Zero(currency.USD)
	if !z.IsZero() {
		t.Error("zero money should be zero")
	}
	m, _ := NewFromString("1.00", currency.USD)
	if m.IsZero() {
		t.Error("1.00 should not be zero")
	}
}

func TestIsNegative(t *testing.T) {
	m, _ := NewFromString("-5.00", currency.USD)
	if !m.IsNegative() {
		t.Error("-5.00 should be negative")
	}
	p, _ := NewFromString("5.00", currency.USD)
	if p.IsNegative() {
		t.Error("5.00 should not be negative")
	}
}

func TestEqual(t *testing.T) {
	a, _ := NewFromString("100.00", currency.USD)
	b, _ := NewFromString("100.00", currency.USD)
	c, _ := NewFromString("100.00", currency.EUR)
	if !a.Equal(b) {
		t.Error("same amount and currency should be equal")
	}
	if a.Equal(c) {
		t.Error("different currencies should not be equal")
	}
}

func TestImmutability(t *testing.T) {
	a, _ := NewFromString("100.00", currency.USD)
	b, _ := NewFromString("50.00", currency.USD)
	_, _ = a.Add(b)
	if a.String() != "100.00 USD" {
		t.Errorf("original should be unchanged, got %q", a.String())
	}
}
