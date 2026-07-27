# TransLoka

TransLoka is a local-first personal PDF translation application.

## Windows local development

Run these commands from PowerShell. The scripts resolve the repository from
their own location, so the current directory does not need to be the repository.

```powershell
.\scripts\setup-local.ps1
.\scripts\start.ps1
```

`setup-local.ps1` validates Node.js 24, pnpm 11, uv, Python 3.12, workspace
files, and installed local dependencies. It does not install anything.

`start.ps1` starts:

- Next.js at `http://127.0.0.1:3000`;
- FastAPI at `http://127.0.0.1:8000`;
- the local worker.

Stop the recorded processes from another PowerShell window:

```powershell
.\scripts\stop.ps1
```

The stop script targets only process IDs recorded by `start.ps1`.

## Manual smoke checklist

1. Run `.\scripts\start.ps1 -CheckOnly` from outside the repository.
2. Run `.\scripts\start.ps1` and confirm all three process IDs are shown.
3. Open `http://127.0.0.1:3000` and confirm the web application loads.
4. Open `http://127.0.0.1:8000/health` and confirm the API reports `ok`.
5. Confirm the worker prints its startup status.
6. Run `.\scripts\stop.ps1` from a second PowerShell window.
7. Confirm the three recorded processes stop and unrelated Node or Python
   processes remain running.
