# SoonAI

SoonAI is a local CLI coding assistant for Windows, macOS, and Linux.

## Install

### Windows

Run `install.bat`, or from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Install
```

The installer creates an isolated virtual environment under
`%LOCALAPPDATA%\SoonAI` and adds that directory to the current user's PATH.

### macOS and Linux

```sh
chmod +x install.sh
./install.sh
```

The installer uses `~/.local/share/soonai` for application files and
`~/.local/bin/soonai` for the launcher. Set `SOONAI_INSTALL_DIR` or
`SOONAI_BIN_DIR` to customize these locations.

The installer adds `~/.local/bin` to `~/.profile` and `~/.zprofile` when
possible. If your shell uses another startup file, add this line manually:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Open a new terminal after installation, then run:

```text
soonai --version
soonai setup
```

To update an existing installation, pull the latest source and run the
installer again. The installer reuses the existing virtual environment and
keeps user data:

```sh
git pull origin main
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Install
```

On macOS/Linux:

```sh
./install.sh
```

The installer does not copy secrets or session data from the source tree.

## Project hooks

Optional tool hooks can run before or after a tool action. Create
`.soonai/hooks.json` in the project root:

```json
{
  "before_tool": {
    "run_tests": "python -m pytest -q"
  },
  "after_tool": {
    "write_file": "git diff --check"
  }
}
```

Hooks are restricted to SoonAI's safe-shell allowlist and have a 30-second
timeout. A failing `before_tool` hook blocks the tool; a failing `after_tool`
hook reports an error. Hooks are never copied by the installer.
