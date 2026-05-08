# Sample Story (Auto-001): Echo handler with empty-message guard (api project)

Status: ready-for-dev


## Story

As a practitioner trying the Automator for the first time on an `api`-project workspace,
I want a complete one-file backend implementation with a happy-path response shape and an empty-input error shape,
So that the first end-to-end loop demonstrates multi-AC iteration, observed-behavior assertions, and an exploratory empty-state heuristic without depending on browser drivers, real network calls, or semantic-verification tooling.

This is a deliberately small `api` project so the first loop terminates in well under five minutes on a typical developer laptop (per NFR-P3 / FR44). Everything lives in one Python file at `src/sample_auto_001/echo.py` with one pure function `echo_handler(request)`. No HTTP framework, no database, no env-provisioning beyond the repo's own working directory.

## Acceptance Criteria

1. **Happy-path echo (Tier-2 outcome evidence).** Given a request `{"message": "hello"}`, `echo_handler(request)` returns a Python `dict` whose `status` key equals the integer `200` and whose `body` key equals `{"echo": "hello"}`. The verification observes the returned value's structure and content (Tier-2 outcome evidence), not just the existence of the function.

2. **Empty-state guard (empty-state exploratory heuristic + Tier-2 outcome evidence).** Given a request with `{"message": ""}` OR a request that is the empty mapping `{}` (no `message` key at all), `echo_handler(request)` returns a Python `dict` whose `status` key equals the integer `400` and whose `body` key equals `{"error": "message is required"}`. This AC exercises the empty-state exploratory heuristic — the absence of a value is a first-class shape distinct from a present-but-different value.

3. **Non-string rejection (error-state exploratory heuristic + Tier-2 outcome evidence).** Given a request whose `message` key is present but is NOT a Python `str` (e.g., `{"message": 42}` or `{"message": ["hi"]}`), `echo_handler(request)` returns a Python `dict` whose `status` key equals the integer `400` and whose `body` key equals `{"error": "message must be a string"}`. This AC exercises the error-state exploratory heuristic — a malformed input shape is verified to produce a distinct, intentional error response rather than a crash or a generic 500.

## Tasks / Subtasks

- [ ] Task 1 — Scaffold the project module (AC: #1)
  - [ ] Create `src/sample_auto_001/__init__.py` (empty package marker).
  - [ ] Create `src/sample_auto_001/echo.py` with one function `echo_handler(request: dict) -> dict`.
  - [ ] Implement the happy-path branch: when `request.get("message")` is a non-empty `str`, return `{"status": 200, "body": {"echo": request["message"]}}`.

- [ ] Task 2 — Implement the empty-state guard (AC: #2)
  - [ ] Add the empty-state branch to `echo_handler`: when `request.get("message")` is `""` OR when `"message"` is absent from `request`, return `{"status": 400, "body": {"error": "message is required"}}`.
  - [ ] Confirm this branch fires for both `{"message": ""}` and `{}` (the empty mapping).

- [ ] Task 3 — Implement the non-string rejection (AC: #3)
  - [ ] Add the non-string branch to `echo_handler`: when `"message"` is present in `request` and `request["message"]` is NOT a `str`, return `{"status": 400, "body": {"error": "message must be a string"}}`.
  - [ ] Place the non-string check AFTER the empty-state check so an empty-string input takes the empty-state branch, not the non-string branch.

- [ ] Task 4 — Add unit tests for the three ACs (AC: #1, #2, #3)
  - [ ] Create `tests/test_echo.py`.
  - [ ] Add `test_happy_path_echo` exercising AC-1 with a typical input and asserting the full returned dict shape.
  - [ ] Add `test_empty_message_string_returns_400` and `test_missing_message_key_returns_400` exercising AC-2.
  - [ ] Add `test_non_string_message_returns_400` exercising AC-3 with an integer AND a list input.
  - [ ] Run the test suite locally and confirm all four tests pass.

## Dev Agent Record

### Agent Model Used

### Completion Notes List

### File List

### Debug Log References
