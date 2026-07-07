---
source_url: https://docs.abapgit.org/user-guide/projects/offline/install.html
fetched: 2026-07-02
project: abapGit (https://abapgit.org)
license: MIT (abapGit documentation and source)
note: condensed extract of the official page (navigation chrome removed)
purpose: citable raw-docs evidence for the L2 auto-research of the benchmark
---

# Offline projects

## What offline repositories are

Offline repositories in abapGit enable developers to manage ABAP projects
without internet connectivity or SSL certificates. They are the alternative to
online Git-based repositories for environments with network restrictions.

## When to use them

- Systems without internet access.
- Environments where SSL connections are not available.
- Air-gapped or isolated SAP landscapes.
- Organizations with strict network security policies.

## Setting up an offline repository

1. Launch abapGit by starting transaction `ZABAPGIT`.
2. Select "New Offline".
3. Enter a project name and SAP package name (e.g. package `$DATAMATRIX`).
4. Select "Create Offline Repo".

Best practice from the documentation: "Use a new SAP package for each abapGit
repository and do _not_ use SAP packages that already include other objects."

## Managing objects in offline repos

- Add custom objects directly to the package.
- Import objects through ZIP file uploads.
- Export repository contents as ZIP files for distribution or backup.
