package command

import (
	"context"
	"testing"

	"github.com/codenogo/pfin/internal/common/event"
	"github.com/codenogo/pfin/internal/identity/domain/user"
	"github.com/codenogo/pfin/pkg/errs"
	"github.com/google/uuid"
)

// mockUserRepo is a test double for user.Repository.
type mockUserRepo struct {
	users  map[string]*user.User
	createErr error
}

func newMockUserRepo() *mockUserRepo {
	return &mockUserRepo{users: make(map[string]*user.User)}
}

func (m *mockUserRepo) Create(ctx context.Context, u *user.User) error {
	if m.createErr != nil {
		return m.createErr
	}
	if _, exists := m.users[u.Email]; exists {
		return errs.Conflict("email already registered")
	}
	m.users[u.Email] = u
	return nil
}

func (m *mockUserRepo) GetByID(ctx context.Context, id uuid.UUID) (*user.User, error) {
	for _, u := range m.users {
		if u.ID == id {
			return u, nil
		}
	}
	return nil, errs.NotFound("user", id.String())
}

func (m *mockUserRepo) GetByEmail(ctx context.Context, email string) (*user.User, error) {
	u, ok := m.users[email]
	if !ok {
		return nil, errs.NotFound("user", email)
	}
	return u, nil
}

func (m *mockUserRepo) Update(ctx context.Context, u *user.User) error {
	m.users[u.Email] = u
	return nil
}

func TestRegister_Success(t *testing.T) {
	repo := newMockUserRepo()
	bus := event.NewBus()
	handler := NewRegisterHandler(repo, bus)

	u, err := handler.Handle(context.Background(), RegisterCmd{
		Email:       "test@example.com",
		Password:    "MyP@ss1!",
		DisplayName: "Test User",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if u.Email != "test@example.com" {
		t.Errorf("Email = %q", u.Email)
	}
	if len(repo.users) != 1 {
		t.Errorf("repo should have 1 user, got %d", len(repo.users))
	}
}

func TestRegister_DuplicateEmail(t *testing.T) {
	repo := newMockUserRepo()
	bus := event.NewBus()
	handler := NewRegisterHandler(repo, bus)

	handler.Handle(context.Background(), RegisterCmd{
		Email: "test@example.com", Password: "MyP@ss1!", DisplayName: "User 1",
	})

	_, err := handler.Handle(context.Background(), RegisterCmd{
		Email: "test@example.com", Password: "MyP@ss2!", DisplayName: "User 2",
	})
	if err == nil {
		t.Fatal("expected conflict error")
	}
}

func TestRegister_InvalidPassword(t *testing.T) {
	repo := newMockUserRepo()
	bus := event.NewBus()
	handler := NewRegisterHandler(repo, bus)

	_, err := handler.Handle(context.Background(), RegisterCmd{
		Email: "test@example.com", Password: "weak", DisplayName: "User",
	})
	if err == nil {
		t.Fatal("expected validation error")
	}
}
