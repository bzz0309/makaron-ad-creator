#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const VERSION = '0.6.2';
const PACKAGE = 'makaron-ad-creator-cli';
const PACKAGE_ROOT = fileURLToPath(new URL('..', import.meta.url));
const MAIN_SKILL = path.join(PACKAGE_ROOT, 'skills', 'makaron-ad-creator');
const PYTHON_ENTRY = path.join(MAIN_SKILL, 'scripts', 'makaron_ad.py');
const APP_HOME = path.resolve(process.env.MAKARON_AD_HOME || path.join(os.homedir(), '.makaron-ad-creator'));
const CONFIG_FILE = path.join(APP_HOME, 'config.json');
const VENV_DIR = path.join(APP_HOME, 'venv');
const WORKSPACE_DIR = path.join(APP_HOME, 'workspace');
const USER_NPM_PREFIX = path.join(APP_HOME, 'npm-global');
const KEYCHAIN_SERVICE = 'makaron-ad-creator-cli';
const KEYCHAIN_ACCOUNT = 'default';
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

function keychainBinary() {
  if (process.env.MAKARON_AD_KEYCHAIN_BIN) return process.env.MAKARON_AD_KEYCHAIN_BIN;
  if (process.platform !== 'darwin') return null;
  return executable('security');
}

function storedApiKey() {
  const keychain = keychainBinary();
  if (!keychain) return null;
  const result = spawnSync(keychain, [
    'find-generic-password', '-a', KEYCHAIN_ACCOUNT, '-s', KEYCHAIN_SERVICE, '-w',
  ], {encoding: 'utf8'});
  if (result.status !== 0) return null;
  const secret = String(result.stdout || '').trim();
  return secret || null;
}

function credentialStatus() {
  const keychain = keychainBinary();
  return {
    backend: keychain ? 'macos-keychain' : 'environment-only',
    stored: Boolean(storedApiKey()),
  };
}

function saveApiKey(secret) {
  const keychain = keychainBinary();
  if (!keychain) {
    fail('KEYCHAIN_UNAVAILABLE', 'Persistent login currently requires macOS Keychain. Other systems can set MAKARON_API_KEY in the Agent environment.');
  }
  const result = spawnSync(keychain, [
    'add-generic-password', '-U', '-a', KEYCHAIN_ACCOUNT, '-s', KEYCHAIN_SERVICE, '-w', secret,
  ], {encoding: 'utf8'});
  if (result.status !== 0) {
    fail('KEYCHAIN_WRITE_FAILED', String(result.stderr || 'Could not save the Makaron API key in macOS Keychain.').trim());
  }
}

function deleteApiKey() {
  const keychain = keychainBinary();
  if (!keychain) return false;
  const result = spawnSync(keychain, [
    'delete-generic-password', '-a', KEYCHAIN_ACCOUNT, '-s', KEYCHAIN_SERVICE,
  ], {encoding: 'utf8'});
  return result.status === 0;
}

function readHidden(prompt) {
  if (!process.stdin.isTTY || typeof process.stdin.setRawMode !== 'function') {
    fail('INTERACTIVE_LOGIN_REQUIRED', 'Run makaron-ad login in an interactive terminal, or set MAKARON_API_KEY once before running login.');
  }
  process.stderr.write(prompt);
  process.stdin.setEncoding('utf8');
  process.stdin.setRawMode(true);
  process.stdin.resume();
  return new Promise((resolve, reject) => {
    let secret = '';
    const finish = () => {
      process.stdin.off('data', onData);
      process.stdin.setRawMode(false);
      process.stdin.pause();
      process.stderr.write('\n');
      resolve(secret.trim());
    };
    const onData = (chunk) => {
      for (const character of chunk) {
        if (character === '\u0003') {
          process.stdin.off('data', onData);
          process.stdin.setRawMode(false);
          process.stdin.pause();
          process.stderr.write('\n');
          reject(new CliError('LOGIN_CANCELLED', 'Login cancelled.'));
          return;
        }
        if (character === '\r' || character === '\n') {
          finish();
          return;
        }
        if (character === '\u007f' || character === '\b') secret = secret.slice(0, -1);
        else secret += character;
      }
    };
    process.stdin.on('data', onData);
  });
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

function writableUserBin() {
  const pathEntries = String(process.env.PATH || '').split(path.delimiter).filter(Boolean);
  const fallback = path.join(APP_HOME, 'bin');
  fs.mkdirSync(fallback, {recursive: true});
  return {directory: fallback, already_on_path: pathEntries.map((entry) => path.resolve(entry)).includes(fallback)};
}

function linkUserCommands(prefix) {
  const selected = writableUserBin();
  const links = [];
  for (const name of ['makaron-ad', 'makaron-ad-creator-cli']) {
    const source = path.join(prefix, 'bin', name);
    if (!fs.existsSync(source)) fail('USER_INSTALL_INVALID', `npm user-prefix install did not create ${source}`);
    const destination = path.join(selected.directory, name);
    try { fs.rmSync(destination, {force: true}); } catch { /* Ignore an absent link. */ }
    fs.symlinkSync(source, destination);
    links.push(destination);
  }
  return {
    bin: selected.directory,
    commands: links,
    path_configured: selected.already_on_path,
    path_hint: selected.already_on_path ? null : `Add this directory to PATH: ${selected.directory}`,
  };
}

function installGlobalCli() {
  const args = ['install', '-g', `${PACKAGE}@${VERSION}`];
  const result = spawnSync('npm', args, {cwd: PACKAGE_ROOT, env: process.env, encoding: 'utf8', timeout: 10 * 60 * 1000});
  if (result.error) fail('COMMAND_START_FAILED', `npm: ${result.error.message}`, true);
  if (result.status === 0) {
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
    return {mode: 'global', command: ['npm', ...args]};
  }
  const detail = String(result.stderr || result.stdout || '').trim();
  if (!/(?:EACCES|EPERM|permission denied)/i.test(detail)) {
    fail('COMMAND_FAILED', `npm exited with ${result.status}${detail ? `: ${detail.slice(-4000)}` : ''}`, true, {exit_code: result.status});
  }
  fs.mkdirSync(USER_NPM_PREFIX, {recursive: true});
  run('npm', [...args, '--prefix', USER_NPM_PREFIX], {inherit: true, timeout: 10 * 60 * 1000});
  return {
    mode: 'user-prefix',
    prefix: USER_NPM_PREFIX,
    command: ['npm', ...args, '--prefix', USER_NPM_PREFIX],
    launcher: linkUserCommands(USER_NPM_PREFIX),
    recovered_from: 'global-install-permission-denied',
  };
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
  if (!env.MAKARON_API_KEY) {
    const secret = storedApiKey();
    if (secret) env.MAKARON_API_KEY = secret;
  }
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
      permission_fallback: ['npm', 'install', '-g', `${PACKAGE}@${VERSION}`, '--prefix', USER_NPM_PREFIX],
      private_runtime: {directory: VENV_DIR, requirement: 'Pillow>=10,<13'},
      skill_install: installSkill({...options, global: true, yes: true}),
      config_file: CONFIG_FILE,
      workspace: WORKSPACE_DIR,
    };
  }
  const cliInstall = options['skip-global-install'] ? {mode: 'skipped'} : installGlobalCli();
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
  return {ok: checked.ok, installed: true, cli_install: cliInstall, config_file: CONFIG_FILE, runtime, skill_install: skillInstall, doctor: checked};
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
  const credential = credentialStatus();
  const makaronAuthHint = Boolean(process.env.MAKARON_API_KEY || credential.stored || fs.existsSync(path.join(os.homedir(), '.makaron', 'auth.json')));
  const checks = {
    package: {name: PACKAGE, version: VERSION, root: PACKAGE_ROOT},
    config: {file: CONFIG_FILE, present: fs.existsSync(CONFIG_FILE), workspace: config.workspace || WORKSPACE_DIR},
    python: {command: python, version: pythonVersion(python), pillow: pillowVersion(python)},
    ffmpeg: runtime.ffmpeg,
    ffprobe: runtime.ffprobe,
    makaron: {command: runtime.makaron, auth_hint_present: makaronAuthHint, credential},
    skill: {bundled: fs.existsSync(path.join(MAIN_SKILL, 'SKILL.md')), directory: MAIN_SKILL},
    python_doctor: pythonDoctor,
  };
  checks.ok = Boolean(python && runtime.ffmpeg && runtime.ffprobe && runtime.makaron && checks.skill.bundled && pythonDoctor?.pass);
  if (!makaronAuthHint) checks.makaron.next_step = 'Run makaron-ad login before live generation if Makaron is not already authenticated through the system keyring.';
  return checks;
}

async function login() {
  const supplied = String(process.env.MAKARON_API_KEY || '').trim();
  const secret = supplied || await readHidden('Paste Makaron API key (input hidden), then press Enter: ');
  if (!secret) fail('API_KEY_REQUIRED', 'No Makaron API key was provided.');
  const runtime = runtimeEnvironment(readJson(CONFIG_FILE));
  if (!runtime.makaron) fail('MAKARON_CLI_REQUIRED', 'Makaron CLI is unavailable. Run setup first.');
  const verification = spawnSync(runtime.makaron, ['credits'], {
    env: {...runtime.env, MAKARON_API_KEY: secret},
    encoding: 'utf8',
    timeout: 60_000,
  });
  if (verification.error) fail('MAKARON_LOGIN_FAILED', verification.error.message, true);
  if (verification.status !== 0) {
    const detail = String(verification.stderr || verification.stdout || '').trim().slice(-2000);
    fail('MAKARON_LOGIN_FAILED', `The API key could not be verified${detail ? `: ${detail}` : ''}`, false);
  }
  saveApiKey(secret);
  emit({ok: true, authenticated: true, credential: credentialStatus(), message: 'Makaron API key verified and saved in macOS Keychain.'});
}

function logout() {
  const removed = deleteApiKey();
  emit({ok: true, removed, message: removed ? 'Stored Makaron API key removed from macOS Keychain.' : 'No stored Makaron API key was found.'});
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
  console.log(`${PACKAGE} ${VERSION}\n\nUsage:\n  npx -y ${PACKAGE} setup [--agent codex]\n  makaron-ad login\n  makaron-ad create --image /path/input.jpg --skill "Marketplace Skill Name" [--locale en|ja|yue|all]\n  makaron-ad status <campaign-id|campaign-directory|campaign.json>\n  makaron-ad run <campaign-id|campaign-directory|campaign.json>\n\nAgent-friendly shorthand:\n  makaron-ad /path/input.jpg "Marketplace Skill Name" [--locale yue]\n\nCommands:\n  setup          Install the global CLI, private Python/Pillow runtime, and Agent Skill\n  install-skill  Install only the bundled makaron-ad-creator Skill\n  login          Verify once and save the API key in macOS Keychain\n  logout         Remove the saved API key from macOS Keychain\n  credits        Show Makaron credit balance using the saved login\n  doctor         Check runtime, Makaron, FFmpeg, and Skill availability\n  create         Generate one or more selected locales (default: EN/JA/YUE)\n  status         Inspect by campaign ID, directory, or campaign.json path\n  run            Resume by campaign ID, directory, or campaign.json path\n\nLocale mapping is fixed: en→English UI, ja→Japanese UI, yue→Traditional-Chinese UI. All workflow command results are JSON. Live create operations use Makaron credits. Supplying an image attests that it is authorized for the requested ad production.`);
}

function selectedLocales(options) {
  const raw = String(options.locale || options.locales || 'all').trim().toLowerCase();
  if (!raw || raw === 'all') return ['en', 'ja', 'yue'];
  const values = raw.split(',').map((value) => value.trim()).filter(Boolean);
  const allowed = new Set(['en', 'ja', 'yue']);
  if (!values.length || values.some((value) => !allowed.has(value))) {
    fail('INVALID_LOCALE', '--locale must be en, ja, yue, all, or a comma-separated subset.');
  }
  if (new Set(values).size !== values.length) fail('INVALID_LOCALE', '--locale must not contain duplicates.');
  return values;
}

function normalizePythonArgs(command, options) {
  if (command === 'create') {
    const image = options.image || options._[0];
    const skill = options.skill || options['skill-name'] || options._[1];
    if (!image || !skill) fail('INPUT_REQUIRED', 'create requires --image <file> and --skill <Marketplace Skill name>.');
    const locales = selectedLocales(options);
    if (options['dry-run']) {
      emit({ok: true, dry_run: true, action: 'create-selected-locale-ad', image: path.resolve(image), skill_name: skill, outputs: locales});
      return null;
    }
    return ['make', image, skill, '--locales', locales.join(',')];
  }
  return [command, ...options._];
}

async function main() {
  const argv = process.argv.slice(2);
  const commands = new Set(['setup', 'install-skill', 'login', 'logout', 'credits', 'doctor', 'create', 'make', 'run', 'status', 'complete', 'fail', 'retry', 'plan', 'init', 'help', 'version']);
  if (argv.length >= 2 && !commands.has(argv[0]) && !argv[0].startsWith('-')) argv.unshift('create');
  const [command = 'help', ...rest] = argv;
  if (command === 'help' || command === '--help') return help();
  if (command === 'version' || command === '--version') return console.log(VERSION);
  if (command === 'doctor') return emit(doctor());
  if (command === 'login') return login();
  if (command === 'logout') return logout();
  if (command === 'credits') return runMakaron([command, ...rest]);
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
