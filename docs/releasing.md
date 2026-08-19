# Release checklist

## Preserve the rollback point

Never overwrite or delete the version being replaced. Before publishing, confirm that the current npm `latest` has a matching Git tag and GitHub Release, then point the npm `previous` dist-tag at it:

```bash
npm view makaron-ad-creator-cli version
git tag --list 'v*'
gh release list
npm dist-tag add makaron-ad-creator-cli@<current-version> previous
```

Every new version must use a new immutable Git tag and GitHub Release. Attach the exact npm package tarball and a SHA-256 checksum to the release. This makes both source and installable package rollback independent of the current branch.

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
npx -y makaron-ad-creator-cli@0.5.0 setup
makaron-ad doctor
```

## GitHub

Merge the reviewed release PR, tag the same version as `v0.5.0`, and attach the npm package URL to the GitHub release notes. Do not publish generated ads or credentials as release assets.

The release notes must include the previous version and these rollback commands with concrete version numbers:

```bash
npm install -g makaron-ad-creator-cli@<previous-version>
makaron-ad install-skill
makaron-ad version
```

For a source rollback, create a new recovery branch from the old tag rather than moving or deleting published tags:

```bash
git switch -c recovery/<previous-version> v<previous-version>
```
