# Project Rules

1. **Validation Architecture:** All data ingestion models must use explicit type hinting and custom exception handling; never allow raw, unvalidated `dict` objects deep into the business logic.
2. **Testing Coverage:** Every new logic module or utility function must be accompanied by a matching `test_[name].py` file covering at least one happy path and two boundary edge cases.
3. **Data Schemas:** Configuration options with fixed choices (like themes or roles) must be strictly bound using Python's standard `enum.Enum`, never plain strings.
