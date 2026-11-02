# @healthcare-os/contracts

API + event contracts enforced by tests, not by checked-in snapshots:

- `tests/contract/test_openapi.py` — required routes, auth-response docs, envelope.
- OpenAPI is generated live at `/api/openapi.json`; P5 publishes a versioned
  snapshot for portal/frontend codegen.

Do not hand-edit contracts here; change the API and update the tests.
