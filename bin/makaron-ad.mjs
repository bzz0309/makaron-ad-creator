#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const VERSION = '0.3.0';
const PACKAGE = 'makaron-ad-creator-cli';
const PACKAGE_ROOT = fileURLToPath(new URL('..', import.meta.url));
const MAIN_SKILL = path.join(PACKAGE_ROOT, 'skills', 'makaron-ad-creator');
const PYTHON_ENTRY = path.join(MAIN_SKILL, 'scripts', 'makaron_ad.py');
const APP_HOME = path.resolve(process.env.MAKARON_AD_HOME || path.join(os.homedir(), '.makaron-ad-creator'));
const CONFIG_FILE = path.join(APP_HOME, 'config.json');
const VENV_DIR = path.join(APP_HOME, 'venv');
const WORKSPACE_DIR = path.join(APP_HOME, 'workspace');
const require = createRequire(import.meta.url);

class CliError extends Error {
  constructor(code, message, retryable = false, details = {}) {
    super(message);
    this.code = code;
    this.retryable = retryable;
    this.details = details;
  }
}

function emit(value) {
  process.stdout.write(`${JSON.stringify(redact(value), null, 2)}\n`);
}

function fail(code, message, retryable = false, details = {}) {
  throw new CliError(code, message, retryable, details);
}

function redact(value) {
  if (typeof value === 'string') {
    return value
      .replace(/mk_(?:live|test)?_?[A-Za-z0-9_-]{8,}/g, '[REDACTED_MAKARON_KEY]')
      .replace(/gh[opusr]_[A-Za-z0-9_]{8,}/g, '[REDACTED_GITHUB_TOKEN]');
  }
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, redact(item)]));
  }
  return value;
}

function parseArgs(argv) {
  const options = {_: []};
  const flags = new Set([
    'dry-run', 'global', 'yes', 'help', 'json', 'skip-global-install',
    'skip-skill-install', 'use-system-python', 'live',
  ]);
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith('--')) {
      options._.push(token);
      continue;
    }
    const key = token.slice(2);
    if (flags.has(key)) options[key] = true;
    else if (index + 1 < argv.length) options[key] = argv[++index];
    else fail('MISSING_OPTION_VALUE', `Missing value for --${key}`);
  }
  return options;
}

function readJson(file, fallback = {}) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), {recursive: true});
  const temporary = `${file}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, {mode: 0o600});
  fs.renameSync(temporary, file);
  fs.chmodSync(file, 0o600);
}

function executable(name, extraPath = process.env.PATH || '') {
  const extensions = process.platform === 'win32' ? ['', '.exe', '.cmd', '.bat'] : [''];
  for (const directory of String(extraPath).split(path.delimiter)) {
    if (!directory) continue;
    for (const extension of extensions) {
      const candidate = path.join(directory, `${name}${extension}`);
      try {
        fs.accessSync(candidate, fs.constants.X_OK);
        return candidate;
      } catch {
        // Continue searching.
      }
    }
  }
  return null;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd || PACKAGE_ROOT,
    env: options.env || process.env,
    encoding: 'utf8',
    stdio: options.inherit ? 'inherit' : ['ignore', 'pipe', 'pipe'],
    timeout: options.timeout || 30 * 60 * 1000,
  });
  if (result.error) fail('COMMAND_START_FAILED', `${command}: ${result.error.message}`, true);
  if (result.status !== 0) {
    const detail = String(result.stderr || result.stdout || '').trim().slice(-4000);
    fail('COMMAND_FAILED', `${command} exited with ${result.status}${detail ? `: ${detail}` : ''}`, true, {exit_code: result.status});
  }
  return result;
}

function bundledBinary(moduleName, property = 'path') {
  try {
    const value = require(moduleName);
    return value?.[property] || null;
  } catch {
    return null;
  }
}

function runtimeEnvironment(config = readJson(CONFIG_FILE)) {
  const directories = [];
  const localBin = path.join(PACKAGE_ROOT, 'node_modules', '.bin');
  if (fs.existsSync(localBin)) directories.push(localBin);
  const ffmpeg = bundledBinary('@ffmpeg-installer/ffmpeg');
  const ffprobe = bundledBinary('@ffprobe-installer/ffprobe');
  if (ffmpeg) directories.push(path.dirname(ffmpeg));
  if (ffprobe) directories.push(path.dirname(ffprobe));
  directories.push(process.env.PATH || '');
  const env = {
    ...process.env,
    PATH: directories.join(path.delimiter),
    PYTHONDONTWRITEBYTECODE: process.env.PYTHONDONTWRITEBYTECODE || '1',
    MAKARON_AD_WORKSPACE: process.env.MAKARON_AD_WORKSPACE || config.workspace || WORKSPACE_DIR,
  };
  const makaron = process.env.MAKARON_AD_MAKARON_BIN || executable('makaron', env.PATH);
  if (makaron) env.MAKARON_AD_MAKARON_BIN = makaron;
  return {env, ffmpeg: ffmpeg || executable('ffmpeg', env.PATH), ffprobe: ffprobe || executable('ffprobe', env.PATH), makaron};
}

function pythonInVenv() {
  return process.platform === 'win32'
    ? path.join(VENV_DIR, 'Scripts', 'python.exe')
    : path.join(VENV_DIR, 'bin', 'python3');
}

function pythonVersion(command) {
  if (!command || !fs.existsSync(command) && !executable(command)) return null;
  const result = spawnSync(command, ['-c', 'import sys; print("%d.%d.%d" % sys.version_info[:3])'], {encoding: 'utf8'});
  if (result.status !== 0) return null;
  const version = String(result.stdout || '').trim();
  const [major, minor] = version.split('.').map(Number);
  return major > 3 || major === 3 && minor >= 11 ? version : null;
}

function systemPython(options = {}) {
  const candidates = [options.python, process.env.MAKARON_AD_PYTHON, executable('python3'), executable('python')].filter(Boolean);
  for (const candidate of candidates) {
    if (pythonVersion(candidate)) return candidate;
  }
  return null;
}

function pillowVersion(python) {
  if (!python) return null;
  const result = spawnSync(python, ['-c', 'import PIL; print(PIL.__version__)'], {encoding: 'utf8'});
  return result.status === 0 ? String(result.stdout || '').trim() : null;
}

function ensurePython(options) {
  const base = systemPython(options);
  if (!base) fail('PYTHON_REQUIRED', 'Python 3.11 or newer is required to run the bundled v5 workflow renderer.');
  if (options['use-system-python']) {
    if (!pillowVersion(base)) fail('PILLOW_REQUIRED', 'The selected system Python does not have Pillow. Omit --use-system-python so setup can create a private runtime.');
    return {python: base, mode: 'system', python_version: pythonVersion(base), pillow_version: pillowVersion(base)};
  }
  const venvPython = pythonInVenv();
  if (!pythonVersion(venvPython)) {
    fs.mkdirSync(APP_HOME, {recursive: true});
    run(base, ['-m', 'venv', '--system-site-packages', VENV_DIR], {timeout: 5 * 60 * 1000});
  }
  if (!pillowVersion(venvPython)) {
    run(venvPython, ['-m', 'pip', 'install', '--disable-pip-version-check', 'Pillow>=10,<13'], {inherit: true, timeout: 10 * 60 * 1000});
  }
  return {python: venvPython, mode: 'private-venv', python_version: pythonVersion(venvPython), pillow_version: pillowVersion(venvPython)};
}

function installSkill(options) {
  if (!fs.existsSync(path.join(MAIN_SKILL, 'SKILL.md'))) fail('SKILL_MISSING', `Bundled Skill not found: ${MAIN_SKILL}`);
  const args = ['-y', 'skills', 'add', MAIN_SKILL, '--skill', 'makaron-ad-creator', '--copy'];
  if (options.global !== false) args.push('--global');
  if (options.agent) args.push('--agent', options.agent);
  if (options.yes !== false) args.push('--yes');
  if (options['dry-run']) return {ok: true, dry_run: true, command: ['npx', ...args], skill_dir: MAIN_SKILL};
  run('npx', args, {inherit: true, timeout: 10 * 60 * 1000});
  return {ok: true, installed: true, skill: 'makaron-ad-creator'};
}

function setup(options) {
  const globalInstall = ['npm', 'install', '-g', `${PACKAGE}@${VERSION}`];
  if (options['dry-run']) {
    return {
      ok: true,
      dry_run: true,
      global_install: globalInstall,
      private_runtime: {directory: VENV_DIR, requirement: 'Pillow>=10,<13'},
      skill_install: installSkill({...options, global: true, yes: true}),
      config_file: CONFIG_FILE,
      workspace: WORKSPACE_DIR,
    };
  }
  if (!options['skip-global-install']) run('npm', ['install', '-g', `${PACKAGE}@${VERSION}`], {inherit: true, timeout: 10 * 60 * 1000});
  const runtime = ensurePython(options);
  fs.mkdirSync(WORKSPACE_DIR, {recursive: true});
  const config = {
    version: 1,
    package_version: VERSION,
    python: runtime.python,
    python_mode: runtime.mode,
    workspace: WORKSPACE_DIR,
    updated_at: new Date().toISOString(),
  };
  writeJson(CONFIG_FILE, config);
  const skillInstall = options['skip-skill-install'] ? {ok: true, skipped: true} : installSkill({...options, global: true, yes: true});
  const checked = doctor();
  return {ok: checked.ok, installed: true, config_file: CONFIG_FILE, runtime, skill_install: skillInstall, doctor: checked};
}

function configuredPython(config = readJson(CONFIG_FILE)) {
  const candidates = [process.env.MAKARON_AD_PYTHON, config.python, pythonInVenv(), systemPython()].filter(Boolean);
  for (const candidate of candidates) {
    if (pythonVersion(candidate) && pillowVersion(candidate)) return candidate;
  }
  return null;
}

function doctor() {
  const config = readJson(CONFIG_FILE);
  const python = configuredPython(config);
  const runtime = runtimeEnvironment(config);
  let pythonDoctor = null;
  if (python && fs.existsSync(PYTHON_ENTRY)) {
    const result = spawnSync(python, [PYTHON_ENTRY, 'doctor'], {env: runtime.env, encoding: 'utf8', timeout: 60_000});
    if (result.status === 0) {
      try { pythonDoctor = JSON.parse(result.stdout); } catch { pythonDoctor = {pass: false, raw: result.stdout}; }
    }
  }
  const makaronAuthHint = Boolean(process.env.MAKARON_API_KEY || fs.existsSync(path.join(os.homedir(), '.makaron', 'auth.json')));
  const checks = {
    package: {name: PACKAGE, version: VERSION, root: PACKAGE_ROOT},
    config: {file: CONFIG_FILE, present: fs.existsSync(CONFIG_FILE), workspace: config.workspace || WORKSPACE_DIR},
    python: {command: python, version: pythonVersion(python), pillow: pillowVersion(python)},
    ffmpeg: runtime.ffmpeg,
    ffprobe: runtime.ffprobe,
    makaron: {command: runtime.makaron, auth_hint_present: makaronAuthHint},
    skill: {bundled: fs.existsSync(path.join(MAIN_SKILL, 'SKILL.md')), directory: MAIN_SKILL},
    python_doctor: pythonDoctor,
  };
  checks.ok = Boolean(python && runtime.ffmpeg && runtime.ffprobe && runtime.makaron && checks.skill.bundled && pythonDoctor?.pass);
  if (!makaronAuthHint) checks.makaron.next_step = 'Run makaron-ad login before live generation if Makaron is not already authenticated through the system keyring.';
  return checks;
}

function runPython(args) {
  const config = readJson(CONFIG_FILE);
  const python = configuredPython(config);
  if (!python) fail('SETUP_REQUIRED', `No configured Python/Pillow runtime. Run: npx -y ${PACKAGE} setup`);
  if (!fs.existsSync(PYTHON_ENTRY)) fail('PYTHON_ENTRY_MISSING', `Bundled Python entry not found: ${PYTHON_ENTRY}`);
  const runtime = runtimeEnvironment(config);
  if (!runtime.makaron) fail('MAKARON_CLI_REQUIRED', 'Makaron CLI is unavailable. Run setup or install makaron-cli.');
  const result = spawnSync(python, [PYTHON_ENTRY, ...args], {
    env: runtime.env,
    encoding: 'utf8',
    stdio: ['inherit', 'pipe', 'inherit'],
  });
  if (result.error) fail('PYTHON_RUN_FAILED', result.error.message, true);
  if (result.stdout) process.stdout.write(redact(result.stdout));
  if (result.status !== 0) process.exitCode = result.status;
}

function runMakaron(args) {
  const runtime = runtimeEnvironment(readJson(CONFIG_FILE));
  if (!runtime.makaron) fail('MAKARON_CLI_REQUIRED', 'Makaron CLI is unavailable. Run setup first.');
  const result = spawnSync(runtime.makaron, args, {env: runtime.env, stdio: 'inherit'});
  if (result.error) fail('MAKARON_RUN_FAILED', result.error.message, true);
  if (result.status !== 0) process.exitCode = result.status;
}

function help() {
  console.log(`${PACKAGE} ${VERSION}\n\nUsage:\n  npx -y ${PACKAGE} setup [--agent codex]\n  makaron-ad login\n  makaron-ad create --image /path/input.jpg --skill "Marketplace Skill Name"\n\nAgent-friendly shorthand:\n  makaron-ad /path/input.jpg "Marketplace Skill Name"\n\nCommands:\n  setup          Install the global CLI, private Python/Pillow runtime, and Agent Skill\n  install-skill  Install only the bundled makaron-ad-creator Skill\n  login          Authenticate the bundled Makaron CLI on this computer\n  credits        Show Makaron credit balance\n  doctor         Check runtime, Makaron, FFmpeg, and Skill availability\n  create         Run the full one-image to EN/JA/YUE ad workflow\n  status         Inspect a resumable campaign\n  run            Resume a campaign\n\nAll workflow command results are JSON. Live create operations use Makaron credits. Supplying an image attests that it is authorized for the requested ad production.`);
}

function normalizePythonArgs(command, options) {
  if (command === 'create') {
    const image = options.image || options._[0];
    const skill = options.skill || options['skill-name'] || options._[1];
    if (!image || !skill) fail('INPUT_REQUIRED', 'create requires --image <file> and --skill <Marketplace Skill name>.');
    if (options['dry-run']) {
      emit({ok: true, dry_run: true, action: 'create-three-locale-ad', image: path.resolve(image), skill_name: skill, outputs: ['en', 'ja', 'yue']});
      return null;
    }
    return ['make', image, skill];
  }
  return [command, ...options._];
}

async function main() {
  const argv = process.argv.slice(2);
  const commands = new Set(['setup', 'install-skill', 'login', 'credits', 'doctor', 'create', 'make', 'run', 'status', 'complete', 'fail', 'retry', 'plan', 'init', 'help', 'version']);
  if (argv.length >= 2 && !commands.has(argv[0]) && !argv[0].startsWith('-')) argv.unshift('create');
  const [command = 'help', ...rest] = argv;
  if (command === 'help' || command === '--help') return help();
  if (command === 'version' || command === '--version') return console.log(VERSION);
  if (command === 'doctor') return emit(doctor());
  if (command === 'login' || command === 'credits') return runMakaron([command, ...rest]);
  if (!['setup', 'install-skill', 'create', 'make'].includes(command)) return runPython([command, ...rest]);
  const options = parseArgs(rest);
  if (options.help) return help();
  if (command === 'setup') return emit(setup(options));
  if (command === 'install-skill') return emit(installSkill(options));
  const pythonArgs = normalizePythonArgs('create', options);
  if (pythonArgs) runPython(pythonArgs);
}

main().catch((error) => {
  const value = error instanceof CliError
    ? {ok: false, error: {code: error.code, message: error.message, retryable: error.retryable, details: error.details}}
    : {ok: false, error: {code: 'UNEXPECTED_ERROR', message: error?.message || String(error), retryable: false}};
  process.stderr.write(`${JSON.stringify(redact(value), null, 2)}\n`);
  process.exitCode = 1;
});
