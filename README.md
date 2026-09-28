# SoonAI

SoonAI is a local CLI coding assistant for Windows, macOS, and Linux.

It helps developers run local workflows, manage project setup, connect to datacenter environments, and create custom AI model projects without requiring Python knowledge in the day-to-day flow.

## Quick install

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/panupong-web/soonai.ai/main/install.sh | sh
```

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest https://raw.githubusercontent.com/panupong-web/soonai.ai/main/install.ps1 -OutFile $env:TEMP\soonai-install.ps1; & $env:TEMP\soonai-install.ps1 -Install"
```

### Local repo install

```bash
git clone https://github.com/panupong-web/soonai.ai.git
cd soonai.ai
chmod +x install.sh
./install.sh
```

On Windows:

```powershell
cd C:\path\to\soonai.ai
powershell -ExecutionPolicy Bypass -File .\install.ps1 -Install
```

After installation, open a new terminal and run:

```bash
soonai --version
soonai setup
```

## What SoonAI does

- installs Python 3.12+ automatically when needed
- creates a local virtual environment for the app
- adds the launcher command `soonai` to PATH
- stores user data outside the repo, in machine-local folders
- supports local project setup and datacenter configuration
- can create local custom model projects and training plans

## User data paths

- Windows: `%LOCALAPPDATA%\SoonAI`
- macOS/Linux: `~/.soonai`

Use:

```bash
soonai status
```

to inspect the active paths and configuration.

## Common commands

```bash
soonai --help
soonai setup
soonai status
soonai /datacenter
soonai model init demo-model
soonai train --model demo-model --cluster local --epochs 1
```

## Datacenter setup

SoonAI can save real datacenter connection details locally on the machine:

```bash
soonai /datacenter
```

This stores settings in:

- Windows: `%USERPROFILE%\.soonai\datacenter.json`
- macOS/Linux: `~/.soonai/datacenter.json`

The profile can then be used for distributed jobs, Slurm/Kubernetes submission, and model training workflows.

## Binary / desktop launch

This project also includes a packaged Windows executable in the `exesoonai` folder for easier local use without needing Python or a terminal.

## License

MIT

