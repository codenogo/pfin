package event

import (
	"context"
	"sync/atomic"
	"testing"
	"time"
)

func TestAsyncBus_Delivery(t *testing.T) {
	bus := NewAsyncBus(2, 10)
	defer bus.Close()

	var count atomic.Int32
	bus.Subscribe("async.test", func(ctx context.Context, e Event) error {
		count.Add(1)
		return nil
	})

	for i := 0; i < 5; i++ {
		bus.Publish(context.Background(), testEvent{name: "async.test"})
	}

	// Wait for async delivery
	time.Sleep(100 * time.Millisecond)
	if count.Load() != 5 {
		t.Errorf("count = %d, want 5", count.Load())
	}
}

func TestAsyncBus_ErrorsDoNotPropagate(t *testing.T) {
	bus := NewAsyncBus(1, 10)
	defer bus.Close()

	bus.Subscribe("async.fail", func(ctx context.Context, e Event) error {
		return errTestHandler
	})

	err := bus.Publish(context.Background(), testEvent{name: "async.fail"})
	if err != nil {
		t.Errorf("async publish should not return handler errors, got %v", err)
	}
}

func TestAsyncBus_Close_Drains(t *testing.T) {
	bus := NewAsyncBus(1, 100)

	var count atomic.Int32
	bus.Subscribe("drain.test", func(ctx context.Context, e Event) error {
		count.Add(1)
		return nil
	})

	for i := 0; i < 10; i++ {
		bus.Publish(context.Background(), testEvent{name: "drain.test"})
	}

	bus.Close()
	if count.Load() != 10 {
		t.Errorf("count = %d, want 10 (all should be processed before Close returns)", count.Load())
	}
}

var errTestHandler = context.DeadlineExceeded // reuse a sentinel for testing
