package user

import (
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
)

// User is the aggregate root for the Identity bounded context.
type User struct {
	ID           uuid.UUID
	Email        string
	PasswordHash string
	DisplayName  string
	CreatedAt    time.Time
	UpdatedAt    time.Time
}

// NewUser creates a new User with validated fields. Password must already be hashed.
func NewUser(email, passwordHash, displayName string) (*User, error) {
	email = strings.TrimSpace(strings.ToLower(email))
	if email == "" {
		return nil, fmt.Errorf("email is required")
	}
	if !strings.Contains(email, "@") || !strings.Contains(email, ".") {
		return nil, fmt.Errorf("invalid email format")
	}
	displayName = strings.TrimSpace(displayName)
	if displayName == "" {
		return nil, fmt.Errorf("display name is required")
	}
	if passwordHash == "" {
		return nil, fmt.Errorf("password hash is required")
	}
	now := time.Now()
	return &User{
		ID:           uuid.New(),
		Email:        email,
		PasswordHash: passwordHash,
		DisplayName:  displayName,
		CreatedAt:    now,
		UpdatedAt:    now,
	}, nil
}

// UpdateDisplayName changes the user's display name.
func (u *User) UpdateDisplayName(name string) error {
	name = strings.TrimSpace(name)
	if name == "" {
		return fmt.Errorf("display name is required")
	}
	u.DisplayName = name
	u.UpdatedAt = time.Now()
	return nil
}
