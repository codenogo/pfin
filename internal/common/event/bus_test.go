package event

import (
	"context"
	"errors"
	"testing"
)

type testEvent struct {
	name string
}

func (e testEvent) EventName() string { return e.name }

func TestBus_PublishToSubscriber(t *testing.T) {
	bus := NewBus()
	called := false
	bus.Subscribe("test.event", func(ctx context.Context, e Event) error {
		called = true
		return nil
	})

	err := bus.Publish(context.Background(), testEvent{name: "test.event"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !called {
		t.Error("handler should have been called")
	}
}

func TestBus_MultipleHandlers(t *testing.T) {
	bus := NewBus()
	count := 0
	bus.Subscribe("test.event", func(ctx context.Context, e Event) error {
		count++
		return nil
	})
	bus.Subscribe("test.event", func(ctx context.Context, e Event) error {
		count++
		return nil
	})

	bus.Publish(context.Background(), testEvent{name: "test.event"})
	if count != 2 {
		t.Errorf("count = %d, want 2", count)
	}
}

func TestBus_ErrorStopsExecution(t *testing.T) {
	bus := NewBus()
	expectedErr := errors.New("handler failed")
	bus.Subscribe("test.event", func(ctx context.Context, e Event) error {
		return expectedErr
	})
	secondCalled := false
	bus.Subscribe("test.event", func(ctx context.Context, e Event) error {
		secondCalled = true
		return nil
	})

	err := bus.Publish(context.Background(), testEvent{name: "test.event"})
	if !errors.Is(err, expectedErr) {
		t.Errorf("error = %v, want %v", err, expectedErr)
	}
	if secondCalled {
		t.Error("second handler should not have been called")
	}
}

func TestBus_UnknownEventNoError(t *testing.T) {
	bus := NewBus()
	err := bus.Publish(context.Background(), testEvent{name: "unknown"})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
}
