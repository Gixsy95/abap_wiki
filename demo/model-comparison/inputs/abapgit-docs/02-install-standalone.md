---
source_url: https://docs.abapgit.org/user-guide/getting-started/install.html
fetched: 2026-07-02
project: abapGit (https://abapgit.org)
license: MIT (abapGit documentation and source)
note: condensed extract of the official page (navigation chrome removed)
purpose: citable raw-docs evidence for the L2 auto-research of the benchmark
---

# Installing and running the abapGit standalone version

## Prerequisites

- SAP BASIS version 702 or higher required.
- Works best with SAP GUI for Windows.
- SSL setup needed for online features.

## Standalone vs developer version

**Standalone version**: "targeted at users. It consists of one (huge) program
which contains all the needed code." It is executed via transaction SE38.

**Developer version**: "targeted at developers contributing to the abapGit
codebase." Run via transaction ZABAPGIT. It supports parallel processing and
requires installing the standalone version first.

## Installing the standalone version

1. Download the ABAP code from the GitHub repository (right-click, save-as).
2. Create a new report named `ZABAPGIT_STANDALONE` using SE38, SE80, or ADT.
3. In source code edit mode, upload the downloaded file via
   Utilities -> More Utilities -> Upload/Download -> Upload.
4. Activate the program.
5. Run it via transaction SE38.

**Package recommendation**: use a local `$` package (e.g. `$ABAPGIT`).

## Installing the developer version

First install the standalone version in English (EN language), then either:

- **Online method** (recommended): requires SSL configuration; clone
  `https://github.com/abapGit/abapGit/` into package `$ABAPGIT`
  ("Create Online Repo", then "Pull").
- **Offline method**: download the ZIP from the GitHub repository, create an
  offline repo in package `$ABAPGIT`, import and pull the ZIP file.

Transaction ZABAPGIT becomes available after completing either method.
