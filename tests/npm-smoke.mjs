import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const cli = path.join(root, 'bin', 'makaron-ad.mjs');
const fixedLogoCta = path.join(root, 'skills', 'makaron-ad-creator', 'assets', 'makaron-logo-cta.mp4');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'makaron-ad-npm-smoke-'));
const env = {...process.env, MAKARON_AD_HOME: temporary};

function invoke(args) {
  const result = spawnSync(process.execPath, [cli, ...args], {cwd: root, env, encoding: 'utf8'});
  assert.equal(result.status, 0, `${args.join(' ')} failed:\n${result.stderr}\n${result.stdout}`);
  return result.stdout;
}

assert.match(invoke(['help']), /makaron-ad create/);
assert.equal(invoke(['version']).trim(), '0.4.0');
assert.equal(fs.existsSync(fixedLogoCta), true);
assert.ok(fs.statSync(fixedLogoCta).size > 1_000_000);

const drySetup = JSON.parse(invoke(['setup', '--dry-run']));
assert.equal(drySetup.ok, true);
assert.equal(drySetup.global_install.join(' '), 'npm install -g makaron-ad-creator-cli@0.4.0');
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

const doctor = JSON.parse(invoke(['doctor']));
assert.equal(doctor.ok, true);
assert.equal(doctor.skill.bundled, true);
assert.match(invoke(['init', '--help']), /--confirm-rights/);

fs.rmSync(temporary, {recursive: true, force: true});
console.log('npm smoke: OK');
