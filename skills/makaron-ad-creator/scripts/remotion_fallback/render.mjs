#!/usr/bin/env node

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {ensureBrowser, renderMedia, selectComposition} from '@remotion/renderer';

const [designFile, outputFile] = process.argv.slice(2);
if (!designFile || !outputFile) {
  throw new Error('Usage: render.mjs <design.json> <output.mp4>');
}

const design = JSON.parse(fs.readFileSync(designFile, 'utf8'));
const code = String(design.code || '');
const width = Number(design.width);
const height = Number(design.height);
const fps = Number(design.animation?.fps);
const durationInSeconds = Number(design.animation?.durationInSeconds);
const durationInFrames = Math.round(fps * durationInSeconds);
const props = design.props && typeof design.props === 'object' ? design.props : {};

if (!code.includes('function Composition') || code.length > 250_000) {
  throw new Error('The Makaron response did not contain a bounded Composition function.');
}
if (![width, height, fps, durationInSeconds, durationInFrames].every(Number.isFinite)) {
  throw new Error('The Makaron Remotion design has invalid dimensions or timing.');
}
if (width !== 1080 || height !== 1920 || fps !== 30 || durationInSeconds < 15 || durationInSeconds > 20) {
  throw new Error(`Refusing unexpected Remotion contract: ${width}x${height}, ${fps}fps, ${durationInSeconds}s`);
}

const forbidden = [
  /\b(?:require|eval|Function)\s*\(/,
  /\b(?:process|globalThis|WebSocket|XMLHttpRequest|document\.cookie)\b/,
  /\b(?:child_process|node:fs|node:net|node:http|node:https)\b/,
  /^\s*import\s/m,
  /^\s*export\s/m,
];
if (forbidden.some((pattern) => pattern.test(code))) {
  throw new Error('The generated Remotion source contains a forbidden runtime capability.');
}

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'makaron-ad-remotion-'));
const entryPoint = path.join(temporary, 'index.jsx');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..');
const entry = `
import React from 'react';
import {AbsoluteFill, Composition as RemotionComposition, Img, Sequence, interpolate, registerRoot, useCurrentFrame} from 'remotion';
import {Audio, Video} from '@remotion/media';
${code}
const defaultProps = ${JSON.stringify(props)};
const Root = () => <RemotionComposition id="MakaronAd" component={Composition} durationInFrames={${durationInFrames}} fps={${fps}} width={${width}} height={${height}} defaultProps={defaultProps} />;
registerRoot(Root);
`;
fs.writeFileSync(entryPoint, entry, 'utf8');
fs.mkdirSync(path.dirname(path.resolve(outputFile)), {recursive: true});

try {
  await ensureBrowser({chromeMode: 'headless-shell', logLevel: 'warn'});
  const serveUrl = await bundle({
    entryPoint,
    rootDir: root,
    publicDir: null,
    onProgress: () => undefined,
    webpackOverride: (config) => ({
      ...config,
      resolve: {
        ...config.resolve,
        modules: [path.join(root, 'node_modules'), ...(config.resolve?.modules || [])],
      },
    }),
  });
  const composition = await selectComposition({
    serveUrl,
    id: 'MakaronAd',
    inputProps: props,
    chromeMode: 'headless-shell',
    logLevel: 'warn',
  });
  await renderMedia({
    composition,
    serveUrl,
    codec: 'h264',
    audioCodec: 'aac',
    pixelFormat: 'yuv420p',
    outputLocation: path.resolve(outputFile),
    inputProps: props,
    overwrite: true,
    concurrency: 1,
    chromeMode: 'headless-shell',
    timeoutInMilliseconds: 120_000,
    logLevel: 'warn',
  });
  const stats = fs.statSync(outputFile);
  if (!stats.isFile() || stats.size === 0) throw new Error('Remotion rendered an empty output file.');
  process.stdout.write(`${JSON.stringify({ok: true, output: path.resolve(outputFile), bytes: stats.size})}\n`);
} finally {
  fs.rmSync(temporary, {recursive: true, force: true});
}
