#!/usr/bin/env node

import fs from 'fs';
import path from 'path';
import os from 'os';
import crypto from 'crypto';
import readline from 'readline';
import { spawnSync } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const APP_NAME = 'soonai';
const APP_VERSION = '1.0.2';
const DEFAULT_CONFIG_NAME = '.soonai.json';
const DATACENTER_CONFIG_PATH = path.join(os.homedir(), '.soonai', 'datacenter.json');
const DATACENTER_KEY_PATH = path.join(os.homedir(), '.soonai', '.datacenter.key');
const LICENSE_STATE_PATH = path.join(os.homedir(), '.soonai', 'node-license.json');
const LOCAL_MODEL_ROOT = path.join(os.homedir(), 'soonai-models');

function printHelp() {
  const help = `
SoonAI CLI

Usage:
  soonai <command> [options]

Commands:
  init                 Create a local SoonAI config in the current project
  status               Show current configuration and workspace status
  setup                Guided setup for a local project
  run                  Run a default local task or script
  doctor               Check environment and CLI readiness
  config               Show or manage config values
  datacenter           Configure a real datacenter connection profile
  license              Activate, inspect, or release a license seat
  model                Create and manage a custom local AI model project
  train                Train a custom model locally or on datacenter infrastructure
  help                 Show this help message
  version              Show CLI version

Examples:
  soonai init
  soonai status
  soonai setup
  soonai run
  soonai doctor
  soonai config
  soonai /datacenter
  soonai license activate
  soonai model init my-model
  soonai train --model my-model --cluster local

Options:
  -h, --help           Show help
  -v, --version        Show version

Notes:
  SoonAI is a local CLI assistant designed to help with coding tasks,
  project setup, quick checks, and local workflow automation.
  It keeps project-level configuration in the current directory and uses
  the machine's local environment without requiring external packages.
`;

  console.log(help.trim());
}

function printVersion() {
  console.log(`${APP_NAME} ${APP_VERSION}`);
}

function ensureDir(targetPath) {
  if (!fs.existsSync(targetPath)) {
    fs.mkdirSync(targetPath, { recursive: true });
  }
}

function getUserHome() {
  return os.homedir();
}

function getProjectConfigPath(projectDir) {
  return path.join(projectDir, DEFAULT_CONFIG_NAME);
}

function defaultConfig() {
  return {
    name: 'soonai-project',
    createdAt: new Date().toISOString(),
    version: APP_VERSION,
    workspace: process.cwd(),
    features: {
      localAssistant: true,
      developerMode: true,
      safeMode: true,
      autoSetup: false
    },
    commands: {
      default: 'npm test',
      setup: 'npm install'
    }
  };
}

function loadConfig(projectDir) {
  const configPath = getProjectConfigPath(projectDir);
  if (!fs.existsSync(configPath)) {
    return null;
  }

  try {
    const raw = fs.readFileSync(configPath, 'utf8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveConfig(projectDir, data) {
  const configPath = getProjectConfigPath(projectDir);
  ensureDir(projectDir);
  fs.writeFileSync(configPath, JSON.stringify(data, null, 2) + '\n', 'utf8');
  return configPath;
}

function normalizeArgs(argv) {
  const args = [...argv];
  const result = {
    command: null,
    flags: [],
    values: [],
    raw: args
  };

  const flagWithValue = new Set([
    '--model', '--cluster', '--gpus', '--epochs', '--batch-size', '--batch_size', '--dataset', '--output', '--reset', '--list', '--host', '--hostname', '--username', '--token', '--password', '--storage', '--environment', '--env', '--set'
  ]);

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    const cleaned = arg.startsWith('/') ? arg.slice(1) : arg;

    if (cleaned === '--help' || cleaned === '-h') {
      result.flags.push('help');
      continue;
    }
    if (cleaned === '--version' || cleaned === '-v') {
      result.flags.push('version');
      continue;
    }
    if (cleaned.startsWith('-')) {
      result.flags.push(cleaned);
      if (flagWithValue.has(cleaned)) {
        const next = args[i + 1];
        if (next && !next.startsWith('-')) {
          result.values.push(cleaned, next);
          i += 1;
        } else {
          result.values.push(cleaned);
        }
      }
      continue;
    }
    if (!result.command) {
      result.command = cleaned;
    } else {
      result.values.push(cleaned);
    }
  }

  return result;
}

function detectPackageManager() {
  const pkgJsonPath = path.join(process.cwd(), 'package.json');
  if (fs.existsSync(pkgJsonPath)) {
    try {
      const pkg = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf8'));
      if (pkg.packageManager) {
        return pkg.packageManager.split('@')[0] || 'npm';
      }
    } catch {
      // ignore
    }
  }

  return 'npm';
}

function runCommand(command, args = []) {
  const child = spawnSync(command, args, {
    stdio: 'inherit',
    shell: false,
    env: process.env
  });

  if (child.error) {
    console.error(`Failed to run command: ${command}`);
    console.error(child.error.message);
    return 1;
  }

  return child.status ?? 1;
}

function commandInit() {
  const projectDir = process.cwd();
  const existing = loadConfig(projectDir);

  if (existing) {
    console.log(`Configuration already exists at: ${getProjectConfigPath(projectDir)}`);
    console.log('Use "soonai status" to view it or "soonai setup" to reconfigure.');
    return 0;
  }

  const config = defaultConfig();
  const configPath = saveConfig(projectDir, config);
  console.log(`SoonAI initialized successfully.`);
  console.log(`Config file created: ${configPath}`);
  console.log('Run "soonai setup" to customize the project workflow.');
  return 0;
}

function commandStatus() {
  const projectDir = process.cwd();
  const configPath = getProjectConfigPath(projectDir);
  const config = loadConfig(projectDir);

  console.log(`Project directory: ${projectDir}`);
  console.log(`Config file: ${configPath}`);

  if (!config) {
    console.log('Status: not initialized');
    console.log('Run "soonai init" to create a config file.');
    return 0;
  }

  console.log('Status: initialized');
  console.log(`Name: ${config.name || 'soonai-project'}`);
  console.log(`Version: ${config.version || APP_VERSION}`);
  console.log(`Workspace: ${config.workspace || projectDir}`);
  console.log(`Local assistant: ${config.features?.localAssistant ? 'enabled' : 'disabled'}`);
  console.log(`Developer mode: ${config.features?.developerMode ? 'enabled' : 'disabled'}`);
  console.log(`Safe mode: ${config.features?.safeMode ? 'enabled' : 'disabled'}`);
  return 0;
}

function commandSetup() {
  const projectDir = process.cwd();
  let config = loadConfig(projectDir) || defaultConfig();

  if (!config.name) {
    config.name = 'soonai-project';
  }

  config.workspace = projectDir;
  config.createdAt = config.createdAt || new Date().toISOString();
  config.features = {
    ...config.features,
    localAssistant: true,
    developerMode: true,
    safeMode: true,
    autoSetup: true
  };

  const pkgManager = detectPackageManager();
  if (!config.commands) {
    config.commands = {};
  }
  config.commands.default = config.commands.default || 'npm test';
  config.commands.setup = config.commands.setup || `${pkgManager} install`;

  const configPath = saveConfig(projectDir, config);
  console.log('SoonAI setup complete.');
  console.log(`Updated config: ${configPath}`);
  console.log(`Preferred package manager: ${pkgManager}`);
  console.log('You can now run: soonai status');
  return 0;
}

function commandRun() {
  const projectDir = process.cwd();
  const config = loadConfig(projectDir);

  if (!config) {
    console.log('No SoonAI config found in this directory.');
    console.log('Run "soonai init" first.');
    return 1;
  }

  const defaultTask = config.commands?.default || 'npm test';
  console.log(`Running default task: ${defaultTask}`);

  const parts = defaultTask.trim().split(/\s+/);
  const command = parts[0];
  const args = parts.slice(1);
  return runCommand(command, args);
}

function commandDoctor() {
  const checks = [];
  const nodeVersion = process.version;
  checks.push(`Node.js: ${nodeVersion}`);
  checks.push(`Platform: ${process.platform}`);
  checks.push(`Current directory: ${process.cwd()}`);

  const configPath = getProjectConfigPath(process.cwd());
  if (fs.existsSync(configPath)) {
    checks.push(`Config file: ${configPath}`);
  } else {
    checks.push('Config file: not initialized');
  }

  const pkgJsonPath = path.join(process.cwd(), 'package.json');
  if (fs.existsSync(pkgJsonPath)) {
    checks.push('Project package.json: found');
  } else {
    checks.push('Project package.json: not found');
  }

  const shell = process.env.SHELL || process.env.ComSpec || 'unknown';
  checks.push(`Shell: ${shell}`);

  console.log('SoonAI Doctor');
  console.log('-------------------');
  for (const item of checks) {
    console.log(item);
  }

  console.log('');
  console.log('Status: ready for local CLI use');
  return 0;
}

function commandConfig(args) {
  const projectDir = process.cwd();
  const config = loadConfig(projectDir) || defaultConfig();

  if (args.length === 0) {
    console.log(JSON.stringify(config, null, 2));
    return 0;
  }

  const [key, ...rest] = args;
  const value = rest.join(' ');

  if (!key) {
    console.log('Usage: soonai config <key> <value>');
    return 1;
  }

  if (!config.features) {
    config.features = {};
  }

  if (key === 'name') {
    config.name = value;
  } else if (key === 'default') {
    config.commands = config.commands || {};
    config.commands.default = value;
  } else if (key === 'setup') {
    config.commands = config.commands || {};
    config.commands.setup = value;
  } else if (key === 'localAssistant') {
    config.features.localAssistant = value === 'true';
  } else if (key === 'developerMode') {
    config.features.developerMode = value === 'true';
  } else if (key === 'safeMode') {
    config.features.safeMode = value === 'true';
  } else {
    console.log(`Unknown config key: ${key}`);
    console.log('Available keys: name, default, setup, localAssistant, developerMode, safeMode');
    return 1;
  }

  saveConfig(projectDir, config);
  console.log(`Config updated: ${key} = ${value}`);
  return 0;
}

function getModelRoot() {
  ensureDir(LOCAL_MODEL_ROOT);
  return LOCAL_MODEL_ROOT;
}

function modelNameToSafeName(input) {
  const raw = String(input || '').trim();
  if (!raw) {
    throw new Error('Model name is required. Example: soonai model init my-model');
  }
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'custom-model';
}

function createModelProjectFileTree(modelName) {
  const root = path.join(getModelRoot(), modelName);
  if (fs.existsSync(root)) {
    throw new Error(`Model project already exists: ${root}`);
  }

  const modelFile = `import torch
import torch.nn as nn


class CustomModel(nn.Module):
    def __init__(self, input_size: int = 2, hidden_size: int = 32, output_size: int = 1):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, output_size),
        )

    def forward(self, x):
        return self.net(x)


def build_model(device=None):
    model = CustomModel()
    if device is not None:
        model = model.to(device)
    return model
`;

  const trainFile = `import argparse
import json
import os
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim

from model import build_model


def build_dataset():
    x = torch.tensor(
        [
            [0.0, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
            [1.0, 1.0],
        ],
        dtype=torch.float32,
    )
    y = torch.tensor([0.0, 1.0, 1.0, 0.0], dtype=torch.float32).view(-1, 1)
    return x, y


def main():
    parser = argparse.ArgumentParser(description='Train a local custom AI model with PyTorch.')
    parser.add_argument('--epochs', type=int, default=200)
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--lr', type=float, default=0.05)
    parser.add_argument('--output-dir', type=str, default='checkpoints')
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = build_model(device)
    optimizer = optim.SGD(model.parameters(), lr=args.lr)
    criterion = nn.MSELoss()

    x, y = build_dataset()
    x = x.to(device)
    y = y.to(device)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        optimizer.zero_grad()
        preds = model(x)
        loss = criterion(preds, y)
        loss.backward()
        optimizer.step()

        if epoch % 50 == 0 or epoch == 1:
            print(f'epoch={epoch} loss={loss.item():.6f}')

    torch.save(model.state_dict(), output_dir / 'model.pth')
    meta = {
        'model': 'CustomModel',
        'device': str(device),
        'epochs': args.epochs,
        'checkpoint': str(output_dir / 'model.pth')
    }
    with open(output_dir / 'metadata.json', 'w', encoding='utf-8') as fh:
        json.dump(meta, fh, indent=2)

    print(f'\\nTraining finished. Model saved to: {output_dir / "model.pth"}')


if __name__ == '__main__':
    main()
`;

  const requirementsFile = `torch>=2.0.0\nnumpy>=2.0.0\n`;

  const readmeFile = [
    '# ' + modelName,
    '',
    'This project was generated by SoonAI as a local custom AI model workspace.',
    '',
    '## Files',
    '- model.py: real PyTorch model definition',
    '- train.py: real training script using a simple example dataset',
    '- requirements.txt: dependencies for local training',
    '',
    '## Run locally',
    '```bash',
    'python -m venv .venv',
    'source .venv/bin/activate',
    'pip install -r requirements.txt',
    'python train.py --epochs 200 --output-dir checkpoints',
    '```',
    '',
    '## Datacenter usage',
    'SoonAI can connect this model to a datacenter configuration and submit it to Slurm or Kubernetes for distributed training.',
    ''
  ].join('\n');

  ensureDir(root);
  fs.writeFileSync(path.join(root, 'model.py'), modelFile, 'utf8');
  fs.writeFileSync(path.join(root, 'train.py'), trainFile, 'utf8');
  fs.writeFileSync(path.join(root, 'requirements.txt'), requirementsFile, 'utf8');
  fs.writeFileSync(path.join(root, 'README.md'), readmeFile, 'utf8');

  return root;
}

function listModelProjects() {
  const root = getModelRoot();
  if (!fs.existsSync(root)) {
    return [];
  }

  return fs.readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

function commandModel(args) {
  if (!args || args.length === 0) {
    console.log('Usage: soonai model <init|list|info> [name]');
    return 0;
  }

  const subcommand = args[0];

  if (subcommand === 'list') {
    const projects = listModelProjects();
    if (projects.length === 0) {
      console.log('No custom AI models found in ~/soonai-models');
      return 0;
    }
    console.log('Local model projects:');
    for (const project of projects) {
      console.log(`- ${project}`);
    }
    return 0;
  }

  if (subcommand === 'init') {
    const name = modelNameToSafeName(args[1]);
    try {
      const modelRoot = createModelProjectFileTree(name);
      console.log('[OK] Custom AI model project created.');
      console.log(`Location: ${modelRoot}`);
      console.log('Next step: soonai train --model ' + name + ' --cluster local');
      return 0;
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error));
      return 1;
    }
  }

  if (subcommand === 'info') {
    const name = modelNameToSafeName(args[1] || '');
    const root = path.join(getModelRoot(), name);
    if (!fs.existsSync(root)) {
      console.log(`Model project not found: ${name}`);
      return 1;
    }
    console.log(`Model directory: ${root}`);
    console.log('Files:');
    for (const file of fs.readdirSync(root)) {
      console.log(`- ${file}`);
    }
    return 0;
  }

  console.log('Usage: soonai model <init|list|info> [name]');
  return 0;
}

function parseCommandFlags(argv) {
  const result = {
    cluster: 'local',
    model: null,
    gpus: '0',
    epochs: '1',
    batchSize: '1',
    dataset: '',
    output: '',
    host: '',
    hostname: '',
    username: '',
    token: '',
    storage: '',
    environment: '',
    run: false,
    extra: []
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--cluster') {
      result.cluster = argv[i + 1] || result.cluster;
      i += 1;
      continue;
    }
    if (arg === '--model') {
      result.model = argv[i + 1] || result.model;
      i += 1;
      continue;
    }
    if (arg === '--gpus') {
      result.gpus = argv[i + 1] || result.gpus;
      i += 1;
      continue;
    }
    if (arg === '--epochs') {
      result.epochs = argv[i + 1] || result.epochs;
      i += 1;
      continue;
    }
    if (arg === '--batch-size' || arg === '--batch_size') {
      result.batchSize = argv[i + 1] || result.batchSize;
      i += 1;
      continue;
    }
    if (arg === '--dataset' || arg === '--storage') {
      result.dataset = argv[i + 1] || result.dataset;
      result.storage = result.dataset;
      i += 1;
      continue;
    }
    if (arg === '--output') {
      result.output = argv[i + 1] || result.output;
      i += 1;
      continue;
    }
    if (arg === '--host' || arg === '--hostname') {
      result.host = argv[i + 1] || result.host;
      result.hostname = result.host;
      i += 1;
      continue;
    }
    if (arg === '--username') {
      result.username = argv[i + 1] || result.username;
      i += 1;
      continue;
    }
    if (arg === '--token' || arg === '--password') {
      result.token = argv[i + 1] || result.token;
      i += 1;
      continue;
    }
    if (arg === '--env' || arg === '--environment') {
      result.environment = argv[i + 1] || result.environment;
      i += 1;
      continue;
    }
    if (arg === '--run') {
      result.run = true;
      continue;
    }
    result.extra.push(arg);
  }

  return result;
}

function generateTrainingPlan(config, modelName) {
  const clusterName = config.clusterType || 'local';
  const jobDir = path.join(getModelRoot(), modelName);
  ensureDir(jobDir);

  if (clusterName === 'slurm') {
    const scriptPath = path.join(jobDir, 'job_slurm.sh');
    const script = `#!/bin/bash
#SBATCH --job-name=${modelName}
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:${config.gpuCount || 1}
#SBATCH --time=01:00:00

set -e
cd ${jobDir}
python -m pip install -r requirements.txt
python train.py --epochs ${config.epochs || 200} --output-dir checkpoints
`;
    fs.writeFileSync(scriptPath, script, 'utf8');
    return { scriptPath, type: 'slurm' };
  }

  if (clusterName === 'kubernetes') {
    const scriptPath = path.join(jobDir, 'job_kubernetes.yaml');
    const yaml = `apiVersion: batch/v1
kind: Job
metadata:
  name: ${modelName}
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: trainer
          image: pytorch/pytorch:latest
          command: ["bash", "-lc"]
          args:
            - |
              cd /workspace/${modelName}
              pip install -r requirements.txt
              python train.py --epochs ${config.epochs || 200} --output-dir checkpoints
          resources:
            limits:
              nvidia.com/gpu: ${config.gpuCount || 1}
`;
    fs.writeFileSync(scriptPath, yaml, 'utf8');
    return { scriptPath, type: 'kubernetes' };
  }

  const scriptPath = path.join(jobDir, 'run_local.sh');
  const script = `#!/usr/bin/env bash
set -e
cd "${jobDir}"
python -m pip install -r requirements.txt
python train.py --epochs ${config.epochs || 200} --output-dir checkpoints
`;
  fs.writeFileSync(scriptPath, script, 'utf8');
  fs.chmodSync(scriptPath, 0o755);
  return { scriptPath, type: 'local' };
}

function findPythonExecutable() {
  const candidates = [
    { cmd: 'py', args: ['-3'] },
    { cmd: 'python', args: [] },
    { cmd: 'python3', args: [] }
  ];

  for (const candidate of candidates) {
    try {
      const result = spawnSync(candidate.cmd, [...candidate.args, '--version'], {
        stdio: 'ignore',
        shell: false
      });
      if (result.status === 0) {
        return { cmd: candidate.cmd, args: candidate.args };
      }
    } catch {
      // ignore and continue
    }
  }

  return null;
}

function ensureModelVenv(modelDir) {
  const venvDir = path.join(modelDir, '.venv');
  const pythonExe = process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python');

  if (fs.existsSync(pythonExe)) {
    return pythonExe;
  }

  const python = findPythonExecutable();
  if (!python) {
    throw new Error('Python 3 is required to train a local model. Install Python 3.12+ and try again.');
  }

  const commandArgs = [...python.args, '-m', 'venv', venvDir];
  const result = spawnSync(python.cmd, commandArgs, {
    stdio: 'inherit',
    shell: false
  });

  if (result.status !== 0) {
    throw new Error(`Failed to create a local virtual environment for the model at ${modelDir}`);
  }

  return pythonExe;
}

function runLocalModelTraining(modelDir, epochs) {
  const venvPython = ensureModelVenv(modelDir);
  const requirementsPath = path.join(modelDir, 'requirements.txt');
  const trainScript = path.join(modelDir, 'train.py');

  const installResult = spawnSync(venvPython, ['-m', 'pip', 'install', '-r', requirementsPath], {
    cwd: modelDir,
    stdio: 'inherit',
    shell: false
  });
  if (installResult.status !== 0) {
    throw new Error('Model dependency installation failed.');
  }

  const trainResult = spawnSync(venvPython, ['train.py', '--epochs', String(epochs), '--output-dir', 'checkpoints'], {
    cwd: modelDir,
    stdio: 'inherit',
    shell: false
  });

  if (trainResult.status !== 0) {
    throw new Error('Local model training failed.');
  }

  console.log('');
  console.log('[OK] Local training completed.');
  console.log(`Checkpoint directory: ${path.join(modelDir, 'checkpoints')}`);
  return 0;
}

function commandTrain(argv) {
  const flags = parseCommandFlags(argv);

  if (!flags.model) {
    console.log('Usage: soonai train --model <name> [--cluster local|slurm|kubernetes] [--gpus N] [--epochs N] [--run]');
    return 1;
  }

  const modelName = modelNameToSafeName(flags.model);
  const modelDir = path.join(getModelRoot(), modelName);
  if (!fs.existsSync(modelDir)) {
    console.log(`Model project not found: ${modelName}`);
    console.log('Create it first: soonai model init ' + modelName);
    return 1;
  }

  const datacenterConfig = loadDatacenterConfig();
  const clusterName = (flags.cluster || datacenterConfig?.clusterType || 'local').toLowerCase();

  if (clusterName !== 'local' && !datacenterConfig) {
    console.log('No datacenter profile was found on this machine.');
    console.log('Configure it first: soonai /datacenter');
    return 1;
  }

  const resolvedConfig = {
    clusterType: clusterName,
    gpuCount: flags.gpus || datacenterConfig?.gpuCount || '1',
    epochs: flags.epochs || datacenterConfig?.epochs || '200',
    storagePath: flags.dataset || datacenterConfig?.storagePath || '',
    modelPath: path.join(modelDir, 'model.py')
  };

  const plan = generateTrainingPlan(resolvedConfig, modelName);

  console.log('[OK] Model training plan created.');
  console.log(`Model: ${modelName}`);
  console.log(`Cluster: ${clusterName}`);
  console.log(`Job script: ${plan.scriptPath}`);

  if (clusterName === 'local' && flags.run) {
    try {
      return runLocalModelTraining(modelDir, Number(resolvedConfig.epochs) || 1);
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error));
      return 1;
    }
  }

  if (clusterName === 'local') {
    console.log('To run immediately:');
    console.log(`  bash "${plan.scriptPath}"`);
  } else {
    console.log('To submit to datacenter:');
    console.log(`  ${clusterName === 'slurm' ? 'sbatch' : 'kubectl apply -f'} "${plan.scriptPath}"`);
  }

  return 0;
}

function getDatacenterConfigDir() {
  ensureDir(path.dirname(DATACENTER_CONFIG_PATH));
  return path.dirname(DATACENTER_CONFIG_PATH);
}

function loadDatacenterConfig() {
  if (!fs.existsSync(DATACENTER_CONFIG_PATH)) {
    return null;
  }

  let config;
  try {
    const raw = fs.readFileSync(DATACENTER_CONFIG_PATH, 'utf8');
    config = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof config.token === 'string' && config.token.startsWith('aes256gcm:')) {
    config.token = unprotectDatacenterToken(config.token);
  }
  return config;
}

function saveDatacenterConfig(data) {
  getDatacenterConfigDir();
  const stored = { ...data };
  if (stored.token) {
    stored.token = protectDatacenterToken(stored.token);
    if (process.platform === 'win32' && stored.token === data.token) {
      throw new Error('Unable to protect the datacenter token with Windows DPAPI; refusing to save it as plaintext.');
    }
  }
  fs.writeFileSync(DATACENTER_CONFIG_PATH, JSON.stringify(stored, null, 2) + '\n', {
    encoding: 'utf8',
    mode: 0o600
  });
  if (process.platform !== 'win32') {
    try {
      fs.chmodSync(DATACENTER_CONFIG_PATH, 0o600);
    } catch {
      // Keep the config usable on filesystems that do not support chmod.
    }
  }
  return DATACENTER_CONFIG_PATH;
}

function protectDatacenterToken(token) {
  if (!token || token.startsWith('aes256gcm:')) {
    return token;
  }

  ensureDir(path.dirname(DATACENTER_KEY_PATH));
  let key;
  if (fs.existsSync(DATACENTER_KEY_PATH)) {
    key = Buffer.from(fs.readFileSync(DATACENTER_KEY_PATH, 'utf8').trim(), 'base64');
    if (process.platform !== 'win32') {
      fs.chmodSync(DATACENTER_KEY_PATH, 0o600);
    }
  } else {
    key = crypto.randomBytes(32);
    fs.writeFileSync(DATACENTER_KEY_PATH, key.toString('base64') + '\n', { mode: 0o600 });
  }
  if (key.length !== 32) {
    throw new Error('Invalid datacenter encryption key.');
  }
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  const encrypted = Buffer.concat([cipher.update(String(token), 'utf8'), cipher.final()]);
  const payload = Buffer.concat([iv, cipher.getAuthTag(), encrypted]).toString('base64');
  return `aes256gcm:${payload}`;
}

function unprotectDatacenterToken(token) {
  if (!token || !token.startsWith('aes256gcm:')) {
    return token;
  }

  try {
    const key = Buffer.from(fs.readFileSync(DATACENTER_KEY_PATH, 'utf8').trim(), 'base64');
    const payload = Buffer.from(token.slice('aes256gcm:'.length), 'base64');
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, payload.subarray(0, 12));
    decipher.setAuthTag(payload.subarray(12, 28));
    return decipher.update(payload.subarray(28), undefined, 'utf8') + decipher.final('utf8');
  } catch {
    throw new Error('Cannot decrypt the saved datacenter token. The local encryption key may be missing or damaged; refusing to silently discard the credential.');
  }
}

function publicDatacenterConfig(config) {
  if (!config) {
    return config;
  }
  return { ...config, token: config.token ? '[stored securely]' : '' };
}

function licenseServiceUrl() {
  const value = String(process.env.SOONAI_LICENSE_API_URL || '').trim().replace(/\/$/u, '');
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error('License service is not configured. Set SOONAI_LICENSE_API_URL after deploying the Worker.');
  }
  const localHttp = parsed.protocol === 'http:' && ['127.0.0.1', 'localhost', '::1'].includes(parsed.hostname);
  if (parsed.protocol !== 'https:' && !localHttp) {
    throw new Error('The license service URL must use HTTPS.');
  }
  return value;
}

function readLicenseState() {
  if (!fs.existsSync(LICENSE_STATE_PATH)) return {};
  const state = JSON.parse(fs.readFileSync(LICENSE_STATE_PATH, 'utf8'));
  if (state.sessionToken) state.sessionToken = unprotectDatacenterToken(state.sessionToken);
  return state;
}

function writeLicenseState(state) {
  ensureDir(path.dirname(LICENSE_STATE_PATH));
  const saved = { ...state };
  if (saved.sessionToken) saved.sessionToken = protectDatacenterToken(saved.sessionToken);
  fs.writeFileSync(LICENSE_STATE_PATH, JSON.stringify(saved, null, 2) + '\n', {
    encoding: 'utf8',
    mode: 0o600
  });
  if (process.platform !== 'win32') fs.chmodSync(LICENSE_STATE_PATH, 0o600);
}

async function requestLicense(route, body, sessionToken = '') {
  const headers = { 'content-type': 'application/json' };
  if (sessionToken) headers.authorization = `Bearer ${sessionToken}`;
  const response = await fetch(`${licenseServiceUrl()}${route}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(10000)
  });
  const payload = await response.json().catch(() => ({}));
  return { response, payload };
}

async function nodeLicenseStatus() {
  const state = readLicenseState();
  if (!state.sessionToken) return { valid: false, message: 'This device is not activated.' };
  try {
    const { response, payload } = await requestLicense('/v1/validate', {}, state.sessionToken);
    if (response.ok && payload.valid === true) {
      state.lastValidated = Date.now();
      writeLicenseState(state);
      return { valid: true, message: 'License active.' };
    }
    if (response.status === 401 || response.status === 403) {
      return { valid: false, message: payload.error || 'License is invalid or revoked.' };
    }
    throw new Error(payload.error || `License service returned HTTP ${response.status}.`);
  } catch (error) {
    const elapsed = Date.now() - Number(state.lastValidated || 0);
    if (elapsed > 0 && elapsed <= 72 * 60 * 60 * 1000) {
      return { valid: true, message: 'License active in offline grace period.' };
    }
    return { valid: false, message: error instanceof Error ? error.message : String(error) };
  }
}

function promptLicenseKey() {
  if (!process.stdin.isTTY || typeof process.stdin.setRawMode !== 'function') {
    return Promise.reject(new Error('License activation requires an interactive terminal.'));
  }
  return new Promise((resolve, reject) => {
    const input = process.stdin;
    readline.emitKeypressEvents(input);
    const oldRaw = Boolean(input.isRaw);
    let value = '';
    const cleanup = () => {
      input.removeListener('keypress', onKeypress);
      input.setRawMode(oldRaw);
      input.pause();
      process.stdout.write('\n');
    };
    const onKeypress = (text, key = {}) => {
      if (key.ctrl && key.name === 'c') {
        cleanup();
        reject(new Error('Activation cancelled.'));
      } else if (key.name === 'return' || key.name === 'enter') {
        cleanup();
        resolve(value.trim());
      } else if (key.name === 'backspace') {
        if (value.length) {
          value = value.slice(0, -1);
          process.stdout.write('\b \b');
        }
      } else if (text && !key.ctrl && !key.meta) {
        value += text;
        process.stdout.write('*'.repeat(text.length));
      }
    };
    process.stdout.write('SoonAI license key: ');
    input.setRawMode(true);
    input.resume();
    input.on('keypress', onKeypress);
  });
}

async function commandLicense(args) {
  const action = args[0] || 'status';
  if (action === 'activate') {
    try {
      licenseServiceUrl();
      const key = await promptLicenseKey();
      if (!key) throw new Error('No license key was entered.');
      const state = readLicenseState();
      const deviceId = state.deviceId || `${crypto.randomUUID()}${crypto.randomUUID().replaceAll('-', '')}`;
      const { response, payload } = await requestLicense('/v1/activate', {
        license_key: key,
        device_id: deviceId
      });
      if (!response.ok || !payload.session_token) {
        throw new Error(payload.error || `Activation failed with HTTP ${response.status}.`);
      }
      writeLicenseState({ deviceId, sessionToken: payload.session_token, lastValidated: Date.now() });
      console.log(`License activated for this device (maximum ${payload.max_devices || 3} devices).`);
      return 0;
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error));
      return 1;
    }
  }

  if (action === 'deactivate') {
    try {
      const state = readLicenseState();
      if (state.sessionToken) {
        const { response } = await requestLicense('/v1/deactivate', {}, state.sessionToken);
        if (!response.ok && response.status !== 401) throw new Error('Unable to deactivate this device.');
      }
      writeLicenseState({ deviceId: state.deviceId || '' });
      console.log('License seat released for this device.');
      return 0;
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error));
      return 1;
    }
  }

  if (action !== 'status') {
    console.error('Usage: soonai license <activate|status|deactivate>');
    return 1;
  }
  const status = await nodeLicenseStatus();
  console.log(status.message);
  return status.valid ? 0 : 1;
}

function showDatacenterHelp() {
  console.log(`
Datacenter configuration for SoonAI

Usage:
  soonai /datacenter
  soonai datacenter
  soonai datacenter --list
  soonai datacenter --reset

This command opens an interactive setup wizard to save a real datacenter
connection profile on this machine.

Saved settings are stored locally at:
  ${DATACENTER_CONFIG_PATH}

Fields collected:
  - cluster type (Slurm / Kubernetes / Custom)
  - hostname or API endpoint
  - username
  - token or password
  - storage path
  - GPU count
  - model path
  - environment name
`);
}

function printDatacenterMenu() {
  console.log('');
  console.log('=== SoonAI Datacenter Setup ===');
  console.log('1) Save or update datacenter settings');
  console.log('2) View saved datacenter settings');
  console.log('3) Remove saved settings');
  console.log('4) Cancel');
  console.log('');
}

function promptQuestion(rl, question) {
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      resolve(answer.trim());
    });
  });
}

async function runDatacenterWizard() {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  try {
    const existing = loadDatacenterConfig();
    const clusterType = await promptQuestion(rl, `Cluster type [slurm/kubernetes/custom]${existing?.clusterType ? ` (${existing.clusterType})` : ''}: `);
    const hostname = await promptQuestion(rl, `Datacenter host / API endpoint${existing?.hostname ? ` (${existing.hostname})` : ''}: `);
    const username = await promptQuestion(rl, `Username${existing?.username ? ` (${existing.username})` : ''}: `);
    const token = await promptQuestion(rl, `Token / password${existing?.token ? ` (hidden)` : ''}: `);
    const storagePath = await promptQuestion(rl, `Storage path${existing?.storagePath ? ` (${existing.storagePath})` : ''}: `);
    const gpuCount = await promptQuestion(rl, `GPU count${existing?.gpuCount ? ` (${existing.gpuCount})` : ''}: `);
    const modelPath = await promptQuestion(rl, `Model path${existing?.modelPath ? ` (${existing.modelPath})` : ''}: `);
    const environment = await promptQuestion(rl, `Environment name${existing?.environment ? ` (${existing.environment})` : ''}: `);

    const finalData = {
      clusterType: clusterType || existing?.clusterType || 'slurm',
      hostname: hostname || existing?.hostname || '',
      username: username || existing?.username || '',
      token: token || existing?.token || '',
      storagePath: storagePath || existing?.storagePath || '',
      gpuCount: gpuCount || existing?.gpuCount || '0',
      modelPath: modelPath || existing?.modelPath || '',
      environment: environment || existing?.environment || 'production',
      savedAt: new Date().toISOString()
    };

    const savedPath = saveDatacenterConfig(finalData);
    console.log('');
    console.log('[OK] Datacenter information saved locally.');
    console.log(`Saved to: ${savedPath}`);
    console.log('You can use this profile with future distributed training commands.');
    console.log('Example: soonai train --cluster slurm --gpus 8');
  } finally {
    rl.close();
  }
}

async function commandDatacenter(args) {
  if (args.includes('--help') || args.includes('-h')) {
    showDatacenterHelp();
    return 0;
  }

  if (args.includes('--list')) {
    const config = loadDatacenterConfig();
    if (!config) {
      console.log('No datacenter profile has been saved on this machine yet.');
      console.log('Run: soonai /datacenter');
      return 0;
    }
    console.log(JSON.stringify(publicDatacenterConfig(config), null, 2));
    return 0;
  }

  if (args.includes('--reset')) {
    if (fs.existsSync(DATACENTER_CONFIG_PATH)) {
      fs.unlinkSync(DATACENTER_CONFIG_PATH);
      console.log('Datacenter settings were removed from this machine.');
    } else {
      console.log('No datacenter settings were found to remove.');
    }
    return 0;
  }

  const setIndex = args.indexOf('--set');
  if (setIndex !== -1) {
    const config = loadDatacenterConfig() || {};
    const values = parseCommandFlags(args.slice(setIndex + 1));
    const nextConfig = {
      ...config,
      clusterType: values.cluster || config.clusterType || 'slurm',
      hostname: values.hostname || values.host || config.hostname || '',
      username: values.username || config.username || '',
      token: values.token || config.token || '',
      storagePath: values.storage || config.storagePath || '',
      gpuCount: values.gpus || config.gpuCount || '0',
      modelPath: config.modelPath || '',
      environment: values.environment || config.environment || 'production',
      savedAt: new Date().toISOString()
    };

    const savedPath = saveDatacenterConfig(nextConfig);
    console.log('[OK] Datacenter profile saved without interactive prompts.');
    console.log(`Saved to: ${savedPath}`);
    console.log(JSON.stringify(publicDatacenterConfig(nextConfig), null, 2));
    return 0;
  }

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });

  try {
    let choice = '1';
    const hasSaved = !!loadDatacenterConfig();

    if (!hasSaved) {
      choice = '1';
    } else {
      printDatacenterMenu();
      choice = await promptQuestion(rl, 'Choose an option [1-4]: ');
    }

    if (choice === '2') {
      const config = loadDatacenterConfig();
      if (!config) {
        console.log('No saved datacenter config found.');
        return 0;
      }
      console.log(JSON.stringify(publicDatacenterConfig(config), null, 2));
      return 0;
    }

    if (choice === '3') {
      if (fs.existsSync(DATACENTER_CONFIG_PATH)) {
        fs.unlinkSync(DATACENTER_CONFIG_PATH);
        console.log('Saved datacenter profile removed.');
      } else {
        console.log('No saved profile found.');
      }
      return 0;
    }

    if (choice === '4' || !choice) {
      console.log('Datacenter setup cancelled.');
      return 0;
    }

    await runDatacenterWizard();
    return 0;
  } finally {
    rl.close();
  }
}

async function main() {
  const argv = process.argv.slice(2);
  const parsed = normalizeArgs(argv);
  const commandName = parsed.command || 'help';

  if (parsed.flags.includes('version')) {
    printVersion();
    return 0;
  }

  if (argv.length === 0) {
    printHelp();
    return 0;
  }

  if (parsed.flags.includes('help')) {
    if (commandName === 'datacenter') {
      showDatacenterHelp();
      return 0;
    }
    if (commandName === 'license') {
      console.log('Usage: soonai license <activate|status|deactivate>');
      return 0;
    }
    printHelp();
    return 0;
  }

  if (commandName === 'license') {
    return commandLicense(parsed.values);
  }

  const licenseRequired = ['1', 'true', 'yes', 'on'].includes(
    String(process.env.SOONAI_LICENSE_REQUIRED || '').trim().toLowerCase()
  );
  if (licenseRequired && !['help', 'version', 'status'].includes(commandName)) {
    const licenseStatus = await nodeLicenseStatus();
    if (!licenseStatus.valid) {
      console.error(`${licenseStatus.message}\nActivate with: soonai license activate`);
      return 1;
    }
  }

  switch (commandName) {
    case 'init':
      return commandInit();
    case 'status':
      return commandStatus();
    case 'setup':
      return commandSetup();
    case 'run':
      return commandRun();
    case 'doctor':
      return commandDoctor();
    case 'config':
      return commandConfig(parsed.values);
    case 'datacenter':
      return commandDatacenter(argv);
    case 'model':
      return commandModel(parsed.values);
    case 'train':
      return commandTrain(argv);
    case 'help':
      printHelp();
      return 0;
    case 'version':
      printVersion();
      return 0;
    default:
      console.error(`Unknown command: ${commandName}`);
      console.error('');
      printHelp();
      return 1;
  }
}

try {
  process.exitCode = await main();
} catch (error) {
  console.error('SoonAI crashed unexpectedly.');
  console.error(error instanceof Error ? error.message : String(error));
  console.error('');
  printHelp();
  process.exitCode = 1;
}
