package event

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"
)

func TestComposite_SyncThenAsync(t *testing.T) {
	syncBus := NewBus()
	asyncBus := NewAsyncBus(1, 10)

	pub := NewCompositePublisher(syncBus, asyncBus)
	defer pub.Close()

	var syncCalled atomic.Bool
	var asyncCalled atomic.Bool

	syncBus.Subscribe("composite.test", func(ctx context.Context, e Event) error {
		syncCalled.Store(true)
		return nil
	})
	asyncBus.Subscribe("composite.test", func(ctx context.Context, e Event) error {
		asyncCalled.Store(true)
		return nil
	})

	pub.Publish(context.Background(), testEvent{name: "composite.test"})

	// Sync handler runs immediately (before Publish returns)
	if !syncCalled.Load() {
		t.Error("sync handler should have been called immediately")
	}

	// Async handler runs shortly after
	time.Sleep(50 * time.Millisecond)
	if !asyncCalled.Load() {
		t.Error("async handler should have been called")
	}
}

func TestComposite_SyncErrorBlocksAsync(t *testing.T) {
	syncBus := NewBus()
	asyncBus := NewAsyncBus(1, 10)

	pub := NewCompositePublisher(syncBus, asyncBus)
	defer pub.Close()

	syncErr := errors.New("sync failed")
	syncBus.Subscribe("fail.test", func(ctx context.Context, e Event) error {
		return syncErr
	})

	var asyncCalled atomic.Bool
	asyncBus.Subscribe("fail.test", func(ctx context.Context, e Event) error {
		asyncCalled.Store(true)
		return nil
	})

	err := pub.Publish(context.Background(), testEvent{name: "fail.test"})
	if !errors.Is(err, syncErr) {
		t.Errorf("expected sync error, got %v", err)
	}

	time.Sleep(50 * time.Millisecond)
	if asyncCalled.Load() {
		t.Error("async should not run when sync fails")
	}
}
