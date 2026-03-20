.PHONY: build test lint run migrate-up migrate-down migrate-create docker-up docker-down

APP_NAME := pfin
BUILD_DIR := bin
MIGRATE := go run -tags 'postgres' github.com/golang-migrate/migrate/v4/cmd/migrate@latest
DATABASE_URL ?= postgres://pfin:pfin@localhost:5432/pfin?sslmode=disable

build:
	go build -o $(BUILD_DIR)/$(APP_NAME) ./cmd/api/...

test:
	go test ./... -v -race

lint:
	golangci-lint run ./...

run:
	go run ./cmd/api/...

migrate-up:
	$(MIGRATE) -path migrations -database "$(DATABASE_URL)" up

migrate-down:
	$(MIGRATE) -path migrations -database "$(DATABASE_URL)" down 1

migrate-create:
	@read -p "Migration name: " name; \
	$(MIGRATE) create -ext sql -dir migrations -seq $$name

docker-up:
	docker compose up -d

docker-down:
	docker compose down
