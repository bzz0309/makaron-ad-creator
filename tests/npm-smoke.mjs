import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cli = path.join(root, 'bin', 'makaron-ad.mjs');
const fixedLogoCta = path.join(root, 'skills', 'makaron-ad-creator', 'assets', 'makaron-logo-cta.mp4');
const uploadLogoCta = path.join(root, 'skills', 'makaron-ad-creator', 'assets', 'makaron-logo-cta-3s.mp4');
const remotionFallback = fs.readFileSync(path.join(root, 'skills', 'makaron-ad-creator', 'scripts', 'remotion_fallback', 'render.mjs'), 'utf8');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'makaron-ad-npm-smoke-'));
const fakeKeychain = path.join(temporary, 'fake-security');
const fakeMakaron = path.join(temporary, 'fake-makaron');
const fakeKeyFile = path.join(temporary, 'stored-key');
const fakeNpmBin = path.join(temporary, 'fake-npm-bin');
const fakeNpm = path.join(fakeNpmBin, 'npm');
fs.writeFileSync(fakeKeychain, [
  '#!/usr/bin/env node',
  "const fs = require('node:fs');",
  "const args = process.argv.slice(2);",
  "const file = process.env.MAKARON_AD_TEST_KEYCHAIN_FILE;",
  "if (args[0] === 'find-generic-password') { if (!fs.existsSync(file)) process.exit(44); process.stdout.write(fs.readFileSync(file, 'utf8')); process.exit(0); }",
  "if (args[0] === 'add-generic-password') { fs.writeFileSync(file, args.at(-1), {mode: 0o600}); process.exit(0); }",
  "if (args[0] === 'delete-generic-password') { if (!fs.existsSync(file)) process.exit(44); fs.unlinkSync(file); process.exit(0); }",
  'process.exit(2);',
].join('\n'), {mode: 0o700});
fs.writeFileSync(fakeMakaron, [
  '#!/usr/bin/env node',
  "if (!process.env.MAKARON_API_KEY) { process.stderr.write('missing API key'); process.exit(2); }",
  "if (process.argv[2] === 'credits') { process.stdout.write('Credits: 100\\n'); process.exit(0); }",
  'process.exit(0);',
].join('\n'), {mode: 0o700});
fs.mkdirSync(fakeNpmBin, {recursive: true});
fs.writeFileSync(fakeNpm, [
  '#!/usr/bin/env node',
  "const fs = require('node:fs');",
  "const path = require('node:path');",
  "const args = process.argv.slice(2);",
  "const prefixIndex = args.indexOf('--prefix');",
  "if (prefixIndex < 0) { process.stderr.write('npm ERR! code EACCES\\nnpm ERR! permission denied\\n'); process.exit(1); }",
  "const prefix = args[prefixIndex + 1];",
  "const bin = path.join(prefix, 'bin');",
  "fs.mkdirSync(bin, {recursive: true});",
  "for (const name of ['makaron-ad', 'makaron-ad-creator-cli']) fs.writeFileSync(path.join(bin, name), '#!/bin/sh\\nexit 0\\n', {mode: 0o700});",
].join('\n'), {mode: 0o700});
const env = {
  ...process.env,
  MAKARON_AD_HOME: temporary,
  MAKARON_AD_KEYCHAIN_BIN: fakeKeychain,
  MAKARON_AD_TEST_KEYCHAIN_FILE: fakeKeyFile,
};

function invoke(args, extraEnv = {}) {
  const result = spawnSync(process.execPath, [cli, ...args], {cwd: root, env: {...env, ...extraEnv}, encoding: 'utf8'});
  assert.equal(result.status, 0, `${args.join(' ')} failed:\n${result.stderr}\n${result.stdout}`);
  return result.stdout;
}

assert.match(invoke(['help']), /makaron-ad create/);
assert.equal(invoke(['version']).trim(), '0.6.2');
assert.equal(fs.existsSync(fixedLogoCta), true);
assert.ok(fs.statSync(fixedLogoCta).size > 1_000_000);
assert.equal(fs.existsSync(uploadLogoCta), true);
assert.ok(fs.statSync(uploadLogoCta).size > 100_000);
assert.match(remotionFallback, /\bLoop\b/);
assert.match(remotionFallback, /React\.__makaronEditableId/);
assert.match(remotionFallback, /runtimeVoiceoverVolume/);
assert.match(remotionFallback, /isVoiceover/);
assert.match(remotionFallback, /captions/);
assert.match(remotionFallback, /replace\(\/\\\\n\/g/);

const drySetup = JSON.parse(invoke(['setup', '--dry-run']));
assert.equal(drySetup.ok, true);
assert.equal(drySetup.global_install.join(' '), 'npm install -g makaron-ad-creator-cli@0.6.2');
assert.equal(drySetup.permission_fallback.join(' '), `npm install -g makaron-ad-creator-cli@0.6.2 --prefix ${path.join(temporary, 'npm-global')}`);
assert.equal(drySetup.skill_install.command.includes('makaron-ad-creator'), true);

const dryCreate = JSON.parse(invoke(['create', '--image', '/tmp/input.jpg', '--skill', 'Rainy Kiss', '--dry-run']));
assert.equal(dryCreate.ok, true);
assert.deepEqual(dryCreate.outputs, ['en', 'ja', 'yue']);

const dryCantonese = JSON.parse(invoke(['create', '--image', '/tmp/input.jpg', '--skill', 'Screen Burst', '--locale', 'yue', '--dry-run']));
assert.deepEqual(dryCantonese.outputs, ['yue']);

const setup = JSON.parse(invoke(['setup', '--skip-global-install', '--skip-skill-install']));
assert.equal(setup.ok, true);
assert.equal(setup.runtime.mode, 'private-venv');
assert.equal(fs.existsSync(path.join(temporary, 'config.json')), true);

const permissionFallback = JSON.parse(invoke(['setup', '--skip-skill-install'], {
  PATH: `${fakeNpmBin}${path.delimiter}${process.env.PATH}`,
}));
assert.equal(permissionFallback.ok, true);
assert.equal(permissionFallback.cli_install.mode, 'user-prefix');
assert.equal(permissionFallback.cli_install.recovered_from, 'global-install-permission-denied');
assert.equal(fs.existsSync(path.join(temporary, 'npm-global', 'bin', 'makaron-ad')), true);
assert.equal(fs.existsSync(path.join(temporary, 'bin', 'makaron-ad')), true);

const doctor = JSON.parse(invoke(['doctor']));
assert.equal(doctor.ok, true);
assert.equal(doctor.skill.bundled, true);
assert.match(invoke(['init', '--help']), /--confirm-rights/);

const testKey = 'mk_test_persistent_login_12345678';
const loggedIn = JSON.parse(invoke(['login'], {
  MAKARON_API_KEY: testKey,
  MAKARON_AD_MAKARON_BIN: fakeMakaron,
}));
assert.equal(loggedIn.ok, true);
assert.equal(loggedIn.credential.stored, true);
const storedDoctor = JSON.parse(invoke(['doctor'], {MAKARON_API_KEY: ''}));
assert.equal(storedDoctor.makaron.credential.stored, true);
assert.match(invoke(['credits'], {MAKARON_API_KEY: '', MAKARON_AD_MAKARON_BIN: fakeMakaron}), /Credits: 100/);
const loggedOut = JSON.parse(invoke(['logout'], {MAKARON_API_KEY: ''}));
assert.equal(loggedOut.removed, true);
assert.equal(fs.existsSync(fakeKeyFile), false);

fs.rmSync(temporary, {recursive: true, force: true});
console.log('npm smoke: OK');
