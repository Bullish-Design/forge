# Validation Checklist

- [ ] `forge-overlay --help` shows new timeout option.
- [ ] Option default is visible and > 5s.
- [ ] Env var override works.
- [ ] App constructs HTTP client with configured timeout.
- [ ] Timeout failures return explicit timeout-flavored error payload.
- [ ] Existing non-timeout upstream failures still map to 502 JSON error.
