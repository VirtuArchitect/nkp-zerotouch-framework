# Dashboard Implementation Notes

`dashboard/app.py` is intentionally dependency-light and runs as a local
operator console. As the console grows, split it into focused modules before
adding more large workflows.

Recommended future structure:

```text
dashboard/
  app.py              # HTTP entrypoint
  auth.py             # sessions, RBAC, CSRF
  routes/             # page handlers
  services/           # jobs, environments, settings, artifacts
  templates/          # shared HTML rendering helpers
  static/             # assets and CSS
```

Keep the current file stable until a refactor can be covered by route smoke
tests for login, environments, jobs, artifacts, plan review, kubeconfig,
settings, and health.
