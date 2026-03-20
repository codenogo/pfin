package user

import "testing"

func TestValidatePassword(t *testing.T) {
	cases := []struct {
		name    string
		pass    string
		wantErr bool
	}{
		{"valid", "Abcdef1!", false},
		{"too short", "Ab1!", true},
		{"no uppercase", "abcdef1!", true},
		{"no lowercase", "ABCDEF1!", true},
		{"no digit", "Abcdefg!", true},
		{"no special", "Abcdefg1", true},
		{"complex valid", "MyP@ssw0rd!123", false},
		{"8 chars exact", "Aa1!bcde", false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := ValidatePassword(tc.pass)
			if tc.wantErr && err == nil {
				t.Errorf("expected error for %q", tc.pass)
			}
			if !tc.wantErr && err != nil {
				t.Errorf("unexpected error for %q: %v", tc.pass, err)
			}
		})
	}
}

func TestHashAndCheckPassword(t *testing.T) {
	plain := "Abcdef1!"
	hash, err := HashPassword(plain)
	if err != nil {
		t.Fatalf("HashPassword: %v", err)
	}
	if hash == plain {
		t.Error("hash should differ from plain")
	}
	if err := CheckPassword(hash, plain); err != nil {
		t.Errorf("CheckPassword should succeed: %v", err)
	}
	if err := CheckPassword(hash, "wrongpassword"); err == nil {
		t.Error("CheckPassword should fail for wrong password")
	}
}
