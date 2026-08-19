# Release checklist

## Verify

```bash
npm ci
npm test
npm run pack:check
```

Install the generated tarball into a temporary npm prefix and confirm `makaron-ad version`, local `setup`, and `doctor.ok=true` before publishing.
Repeat once with a global-style temporary prefix and a restricted `PATH` to prove the launcher resolves its own Makaron CLI, FFmpeg, and FFprobe instead of accidentally using developer-machine globals.

## Publish npm

The public npm package name is `makaron-ad-creator-cli`. Publishing requires an npm account with permission to claim or update that package.

```bash
npm login
npm whoami
npm publish --access public
```

Never commit npm tokens. After publication, verify from a clean directory:

```bash
npx -y makaron-ad-creator-cli@0.4.0 setup
makaron-ad doctor
```

## GitHub

Merge the reviewed release PR, tag the same version as `v0.4.0`, and attach the npm package URL to the GitHub release notes. Do not publish generated ads or credentials as release assets.
