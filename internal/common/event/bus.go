package event

import (
	"context"
	"sync"
)

// Bus is a synchronous in-process event dispatcher.
// All handlers run in the caller's goroutine before Publish returns.
type Bus struct {
	mu       sync.RWMutex
	handlers map[string][]Handler
}

// NewBus creates a new synchronous event bus.
func NewBus() *Bus {
	return &Bus{handlers: make(map[string][]Handler)}
}

// Subscribe registers a handler for an event type.
func (b *Bus) Subscribe(eventName string, handler Handler) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.handlers[eventName] = append(b.handlers[eventName], handler)
}

// Publish dispatches events to all registered handlers synchronously.
// Returns the first error encountered.
func (b *Bus) Publish(ctx context.Context, events ...Event) error {
	b.mu.RLock()
	defer b.mu.RUnlock()

	for _, evt := range events {
		handlers, ok := b.handlers[evt.EventName()]
		if !ok {
			continue
		}
		for _, h := range handlers {
			if err := h(ctx, evt); err != nil {
				return err
			}
		}
	}
	return nil
}
