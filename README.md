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
powershell -ExecutionPolicy Bypass -Command "(New-Object Net.WebClient).DownloadFile('https://raw.githubusercontent.com/panupong-web/soonai.ai/main/install.ps1',(Join-Path $env:TEMP 'soonai-install.ps1')); & (Join-Path $env:TEMP 'soonai-install.ps1') -Install"
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

The first launch does not require Ollama. If Ollama is not installed, SoonAI
opens the provider setup flow so you can choose Ollama, LM Studio, or a cloud
provider instead.

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

## License activation (service deployed; gate remains opt-in)

The public repository includes an optional Cloudflare Worker license service at `https://soonai-license.soonai-2026.workers.dev`. It permits up to three activated devices per key. Both the Python CLI and Node CLI expose `soonai license activate`, `soonai license status`, and `soonai license deactivate`. The gate remains opt-in until the HTTPS endpoint is verified and a real license has been tested. Licensing discourages casual sharing in the official clients; it cannot prevent users from copying or modifying public MIT-licensed source. See [license-service/README.md](license-service/README.md).

## Binary / desktop launch

This project also includes a packaged Windows executable in the `exesoonai` folder for easier local use without needing Python or a terminal.

Verify its SHA-256 before running it:

```powershell
Get-FileHash .\exesoonai\soonai.exe -Algorithm SHA256
Get-Content .\exesoonai\SHA256SUMS.txt
```

Compare the hashes. The checksum detects accidental changes; because it is hosted in the same public repository, it is not a substitute for a trusted digital signature.

## License

MIT

## Security

See [SECURITY.md](SECURITY.md) for credential-storage details, EXE checksum instructions, update trust boundaries, and vulnerability reporting.

