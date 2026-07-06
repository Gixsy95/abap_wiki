---
source_url: https://docs.abapgit.org/user-guide/projects/online/first-project.html
fetched: 2026-07-02
project: abapGit (https://abapgit.org)
license: MIT (abapGit documentation and source)
note: condensed extract of the official page (navigation chrome removed)
purpose: citable raw-docs evidence for the L2 auto-research of the benchmark
---

# First online repository project

## Repository setup

1. "Create the repository on GitHub, and make sure it contains something like a
   README file."
2. Launch the `ZABAPGIT` transaction.
3. "Clone the repository into abapGit."

## Adding objects

1. Navigate to the repository and select the "Add" link.
2. The system prompts to choose which object to add.
3. "The object will be committed to the repository."

## Modifying objects

When an already-committed object is updated, "a 'commit' link will show up in
abapGit." Clicking it pushes the changes to the remote repository.

## Pull operations

If the remote repository receives updates, "a 'pull' link will show up in
abapGit"; "the changes must be pulled before new objects can be changed or
added." The pull operation synchronizes the local SAP system with the latest
remote repository state.

## License handling

Open-source projects on GitHub typically include a LICENSE file. abapGit does
not import this file into SAP systems, so license information should be kept in
source code comments or SPDX identifiers.
