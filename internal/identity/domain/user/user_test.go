package user

import "testing"

func TestNewUser_Valid(t *testing.T) {
	u, err := NewUser("test@example.com", "$2a$10$hashhere", "Test User")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if u.Email != "test@example.com" {
		t.Errorf("Email = %q, want test@example.com", u.Email)
	}
	if u.DisplayName != "Test User" {
		t.Errorf("DisplayName = %q, want Test User", u.DisplayName)
	}
	if u.ID.String() == "00000000-0000-0000-0000-000000000000" {
		t.Error("ID should be generated")
	}
}

func TestNewUser_EmailNormalization(t *testing.T) {
	u, _ := NewUser("  TEST@Example.COM  ", "$2a$10$hash", "User")
	if u.Email != "test@example.com" {
		t.Errorf("Email = %q, expected normalized", u.Email)
	}
}

func TestNewUser_InvalidInputs(t *testing.T) {
	cases := []struct {
		name        string
		email, hash, display string
	}{
		{"empty email", "", "hash", "User"},
		{"no @", "invalid", "hash", "User"},
		{"empty display", "a@b.com", "hash", ""},
		{"empty hash", "a@b.com", "", "User"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			_, err := NewUser(tc.email, tc.hash, tc.display)
			if err == nil {
				t.Error("expected error")
			}
		})
	}
}

func TestUpdateDisplayName(t *testing.T) {
	u, _ := NewUser("a@b.com", "hash", "Old")
	if err := u.UpdateDisplayName("New Name"); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if u.DisplayName != "New Name" {
		t.Errorf("DisplayName = %q, want New Name", u.DisplayName)
	}
	if err := u.UpdateDisplayName(""); err == nil {
		t.Error("empty name should error")
	}
}
