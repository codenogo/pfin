package event

import "context"

// CompositePublisher dispatches events to a sync bus first (critical side effects),
// then to an async bus (non-critical side effects). If the sync bus returns an error,
// the async bus is skipped.
type CompositePublisher struct {
	sync  *Bus
	async *AsyncBus
}

// NewCompositePublisher creates a publisher that combines sync and async dispatch.
func NewCompositePublisher(sync *Bus, async *AsyncBus) *CompositePublisher {
	return &CompositePublisher{sync: sync, async: async}
}

// Publish dispatches to sync handlers first, then async handlers.
func (p *CompositePublisher) Publish(ctx context.Context, events ...Event) error {
	if err := p.sync.Publish(ctx, events...); err != nil {
		return err
	}
	return p.async.Publish(ctx, events...)
}

// SyncBus returns the underlying sync bus for subscription.
func (p *CompositePublisher) SyncBus() *Bus {
	return p.sync
}

// AsyncBus returns the underlying async bus for subscription.
func (p *CompositePublisher) AsyncBus() *AsyncBus {
	return p.async
}

// Close shuts down the async bus workers.
func (p *CompositePublisher) Close() {
	p.async.Close()
}
