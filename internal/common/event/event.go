package event

import "context"

// Event is the interface all domain events implement.
type Event interface {
	EventName() string
}

// Handler processes a single event.
type Handler func(ctx context.Context, event Event) error

// Publisher dispatches events to registered handlers.
type Publisher interface {
	Publish(ctx context.Context, events ...Event) error
}
