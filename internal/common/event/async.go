package event

import (
	"context"
	"log/slog"
	"sync"
)

// AsyncBus dispatches events to handlers asynchronously via goroutine workers.
// Errors are logged, not returned to the caller.
type AsyncBus struct {
	mu       sync.RWMutex
	handlers map[string][]Handler
	queue    chan envelope
	wg       sync.WaitGroup
	done     chan struct{}
}

type envelope struct {
	ctx   context.Context
	event Event
}

// NewAsyncBus creates an async event bus with the given worker count and queue size.
func NewAsyncBus(workers, queueSize int) *AsyncBus {
	b := &AsyncBus{
		handlers: make(map[string][]Handler),
		queue:    make(chan envelope, queueSize),
		done:     make(chan struct{}),
	}
	for i := 0; i < workers; i++ {
		b.wg.Add(1)
		go b.worker()
	}
	return b
}

// Subscribe registers a handler for an event type.
func (b *AsyncBus) Subscribe(eventName string, handler Handler) {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.handlers[eventName] = append(b.handlers[eventName], handler)
}

// Publish enqueues events for async processing. Does not block on handler execution.
func (b *AsyncBus) Publish(ctx context.Context, events ...Event) error {
	for _, evt := range events {
		select {
		case b.queue <- envelope{ctx: ctx, event: evt}:
		case <-b.done:
			return nil
		}
	}
	return nil
}

// Close signals workers to drain the queue and stop.
func (b *AsyncBus) Close() {
	close(b.done)
	close(b.queue)
	b.wg.Wait()
}

func (b *AsyncBus) worker() {
	defer b.wg.Done()
	for env := range b.queue {
		b.mu.RLock()
		handlers := b.handlers[env.event.EventName()]
		b.mu.RUnlock()

		for _, h := range handlers {
			if err := h(env.ctx, env.event); err != nil {
				slog.Error("async event handler failed",
					"event", env.event.EventName(),
					"error", err,
				)
			}
		}
	}
}
