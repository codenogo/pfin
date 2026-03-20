# Release: $ARGUMENTS
<!-- effort: high -->

Cut a tagged release with notes and optional SBOM.

## Arguments

`/release patch`  
`/release minor`  
`/release major`  
`/release vX.Y.Z`

## Your Task

1. Resolve target version from latest tag (`v*`) and argument.

2. Preflight:
- clean working tree or explicit confirmation to include pending changes
- run project verification commands (build/test/lint) before tagging

3. Generate release notes from commits since previous tag:
```bash
git log <prev-tag>..HEAD --pretty=format:"- %s (%h)" --no-merges
```
Include highlights, fixes, breaking changes, and upgrade notes when needed.

4. Update versioned files where applicable (`package.json`, `pom.xml`, `pyproject.toml`, etc.) and `CHANGELOG.md`.

5. Commit + tag:
```bash
git add -A
git commit -m "chore(release): v<version>"
git tag -a "v<version>" -m "Release v<version>"
```

6. Push and create release:
```bash
git push origin <branch>
git push origin v<version>
gh release create v<version> --title "v<version>" --notes-file RELEASE_NOTES.md
```

7. Optional: generate/upload SBOM if required by policy.

## Output

- New version and previous version
- Files changed for release
- Tag + release URL
- Any manual follow-up steps
