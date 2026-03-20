package scope

import (
	"strings"
	"testing"

	"github.com/google/uuid"
)

func TestNewPersonal(t *testing.T) {
	uid := uuid.New()
	s, err := NewPersonal(uid)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !s.IsPersonal() {
		t.Error("should be personal")
	}
	if s.IsHousehold() {
		t.Error("should not be household")
	}
	if s.UserID() != uid {
		t.Errorf("UserID() = %v, want %v", s.UserID(), uid)
	}
	if s.Kind() != KindPersonal {
		t.Errorf("Kind() = %v, want %v", s.Kind(), KindPersonal)
	}
}

func TestNewPersonal_NilID(t *testing.T) {
	_, err := NewPersonal(uuid.Nil)
	if err == nil {
		t.Error("expected error for nil user ID")
	}
}

func TestNewHousehold(t *testing.T) {
	hid := uuid.New()
	s, err := NewHousehold(hid)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !s.IsHousehold() {
		t.Error("should be household")
	}
	if s.IsPersonal() {
		t.Error("should not be personal")
	}
	if s.HouseholdID() != hid {
		t.Errorf("HouseholdID() = %v, want %v", s.HouseholdID(), hid)
	}
}

func TestNewHousehold_NilID(t *testing.T) {
	_, err := NewHousehold(uuid.Nil)
	if err == nil {
		t.Error("expected error for nil household ID")
	}
}

func TestString(t *testing.T) {
	uid := uuid.New()
	s, _ := NewPersonal(uid)
	if !strings.Contains(s.String(), "personal") {
		t.Errorf("String() = %q, expected to contain 'personal'", s.String())
	}

	hid := uuid.New()
	h, _ := NewHousehold(hid)
	if !strings.Contains(h.String(), "household") {
		t.Errorf("String() = %q, expected to contain 'household'", h.String())
	}
}
