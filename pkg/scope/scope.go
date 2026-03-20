package scope

import (
	"fmt"

	"github.com/google/uuid"
)

// Kind represents the scope type.
type Kind string

const (
	KindPersonal  Kind = "personal"
	KindHousehold Kind = "household"
)

// Scope represents the ownership context of a financial entity.
// An entity is either personal (owned by a user) or household (owned by a household).
type Scope struct {
	kind        Kind
	userID      uuid.UUID
	householdID uuid.UUID
}

// NewPersonal creates a personal scope for the given user.
func NewPersonal(userID uuid.UUID) (Scope, error) {
	if userID == uuid.Nil {
		return Scope{}, fmt.Errorf("personal scope requires a user ID")
	}
	return Scope{kind: KindPersonal, userID: userID}, nil
}

// NewHousehold creates a household scope for the given household.
func NewHousehold(householdID uuid.UUID) (Scope, error) {
	if householdID == uuid.Nil {
		return Scope{}, fmt.Errorf("household scope requires a household ID")
	}
	return Scope{kind: KindHousehold, householdID: householdID}, nil
}

// IsPersonal returns true if this is a personal scope.
func (s Scope) IsPersonal() bool {
	return s.kind == KindPersonal
}

// IsHousehold returns true if this is a household scope.
func (s Scope) IsHousehold() bool {
	return s.kind == KindHousehold
}

// Kind returns the scope kind.
func (s Scope) Kind() Kind {
	return s.kind
}

// UserID returns the user ID. Only valid for personal scope.
func (s Scope) UserID() uuid.UUID {
	return s.userID
}

// HouseholdID returns the household ID. Only valid for household scope.
func (s Scope) HouseholdID() uuid.UUID {
	return s.householdID
}

// String returns a human-readable representation.
func (s Scope) String() string {
	if s.kind == KindPersonal {
		return fmt.Sprintf("personal(%s)", s.userID)
	}
	return fmt.Sprintf("household(%s)", s.householdID)
}
