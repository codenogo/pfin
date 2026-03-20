package currency

import "testing"

func TestParse_Valid(t *testing.T) {
	cases := []string{"USD", "EUR", "GBP", "KES", "JPY"}
	for _, code := range cases {
		c, err := Parse(code)
		if err != nil {
			t.Errorf("Parse(%q) unexpected error: %v", code, err)
		}
		if c.String() != code {
			t.Errorf("Parse(%q).String() = %q, want %q", code, c.String(), code)
		}
	}
}

func TestParse_Invalid(t *testing.T) {
	cases := []string{"", "XYZ", "usd", "US", "USDD"}
	for _, code := range cases {
		_, err := Parse(code)
		if err == nil {
			t.Errorf("Parse(%q) expected error, got nil", code)
		}
	}
}

func TestIsValid(t *testing.T) {
	if !USD.IsValid() {
		t.Error("USD should be valid")
	}
	if Currency("XYZ").IsValid() {
		t.Error("XYZ should be invalid")
	}
}
