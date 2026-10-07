# Windows setup

Tested path: Windows 10/11, Python 3.10+, Claude Desktop, AutoCAD Electrical 2026.

## 1. Get the code
Download the repo as a zip from GitHub (*Code → Download ZIP*) and extract it somewhere that will not
be cleaned up, for example `C:\Tools\autocad-electrical-mcp`. Do **not** leave it in `Downloads`: Claude Desktop
starts the program from inside this folder, so moving or deleting the folder breaks the connection.
(If you used `git clone`, the same applies.)

## 2. Run the installer
Open PowerShell **in the repo folder** (the one that contains `pyproject.toml`):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-windows.ps1
```

It creates `.venv`, installs the package, runs `--selftest`, and adds an `acad-electrical` entry to
`%APPDATA%\Claude\claude_desktop_config.json` (a backup is saved as `.bak`; other entries are kept).
Options: `-Workspace D:\drawings` (where models and outputs go), `-NoConfig` (skip the config step).

## 3. Restart Claude Desktop
Quit it completely from the system tray, reopen it, and start a **new** chat. In *Settings → Developer*
the `acad-electrical` server should show *running*.

## 4. Try it
- Offline drawings: *"Run `list_floors` for project demo."* then follow the walk-through in the README.
- Live AutoCAD: open a drawing, press Esc once so no command is running, then *"Run `live_connect`."*
  See [live.md](live.md). First time, use a scratch drawing and *"Run `live_selftest`."*

## Manual install (instead of the script)
```powershell
cd C:\Tools\autocad-electrical-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\acad-electrical-mcp.exe --selftest
```
Then put this in `claude_desktop_config.json` (double backslashes):
```json
{ "mcpServers": { "acad-electrical": {
  "command": "C:\\Tools\\autocad-electrical-mcp\\.venv\\Scripts\\acad-electrical-mcp.exe",
  "env": { "ACAD_MCP_WORKSPACE": "C:\\Users\\YOU\\Documents\\acad_drawings" } } } }
```

## Common problems
| Symptom | Cause / fix |
| --- | --- |
| `spawn ... ENOENT` / "system cannot find the path" in the Claude log | The folder in the config no longer exists (moved/deleted). Reinstall in the new folder and re-run the installer. |
| `No module named 'mcp.server.fastmcp'` | mcp 2.x got installed. `pip install "mcp>=1.9,<2"` in the venv. |
| `pip: ... does not appear to be a Python project` | You ran it outside the repo folder; `cd` into the folder with `pyproject.toml`. |
| Server "running" but no tools in the chat | Quit Claude Desktop from the tray, reopen, start a **new** chat, toggle the connector on. |
| `AutoCAD did not answer` / calls rejected | AutoCAD is busy or in a command/dialog. Press Esc and retry. |
