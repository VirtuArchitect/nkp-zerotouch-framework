# Dashboard

The dashboard is a local console for inspecting `.zt` state and running safe phases.

Run:

```powershell
python .\dashboard\app.py 8080
```

Open:

```text
http://127.0.0.1:8080
```

Dashboard-safe actions:

- `validate`
- `prepare`
- `generate`
- `verify`
- `backup`
- `runs`

Apply/destructive actions remain CLI-only:

- `registry -Apply`
- `deploy -Apply`
- `destroy -Apply -ConfirmDestroy`
