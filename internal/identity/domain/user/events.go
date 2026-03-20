package user

import (
	"time"

	"github.com/google/uuid"
)

// UserRegistered is emitted when a new user completes registration.
type UserRegistered struct {
	UserID    uuid.UUID
	Email     string
	Timestamp time.Time
}

// EventName implements event.Event.
func (e UserRegistered) EventName() string {
	return "identity.user.registered"
}
