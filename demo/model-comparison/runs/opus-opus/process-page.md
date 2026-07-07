---
type: process-doc
slice: abapgit-standalone-demo
title: abapGit standalone - offline installation and usage of the ABAP git client
owner: gixsy95github@gmail.com
doc_level: L2
l2_gate_run: l2-abapgit-standalone-demo-2026-07-03
updated: '2026-07-03'
tags:
- sap
- process
- l2
- abapgit-standalone-demo
status: draft
---
# Process - abapGit standalone - offline installation and usage of the ABAP git client

## Process summary

The slice documents the offline installation and usage of abapGit standalone, the ABAP Git client:
from installing the single-file report to synchronising ABAP objects with a Git repository either
online (over HTTP) or offline (via ZIP)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-purpose-abapgit.md:16-24]
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-run-se38.md:17-19]. In this
landscape the whole process is exercised only as a non-productive benchmark fixture: it is never
actually run here
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:16].

## End-to-end flow

1) Install: create a report named ZABAPGIT_STANDALONE via SE38/SE80/ADT, upload the downloaded
source and activate
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-run-se38.md:24-26]. 2) Launch
via transaction SE38
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-standalone-run-se38.md:34-36]. 3) The
report dispatches on sy-batch - foreground = interactive HTML GUI on screen 1001, background =
zcl_abapgit_background=>run
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-runtime-trigger-dbt.md:21-24]. 4a)
Online: clone a remote repository, then add/commit(push) and pull to synchronise the SAP system with
the remote
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-workflow.md:18-27]. 4b) Offline:
import/export repository contents as ZIP files for air-gapped landscapes
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-offline-airgapped.md:17-28]. In THIS
system none of these steps is actually executed
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:20].

## Object chain

Flow order of the slice's custom objects (consistent with membership.md): (1)
[[program-ZABAPGIT_STANDALONE]] - the SE38 entry point and abapmerge monolith that drives the whole
flow; during PERFORM run it consults its optional user-exit includes - (2)
[[program-ZABAPGIT_AUTHORIZATIONS_EXIT]] (authorization hook), (3) [[program-ZABAPGIT_USER_EXIT]]
(general user exit), (4) [[program-ZABAPGIT_BACKGROUND_USER_EXIT]] (background-mode hook), (5)
[[program-ZABAPGIT_GUI_PAGES_USEREXIT]] (GUI-pages hook); and (6) [[table-ZABAPGIT]] - abapGit's own
persistence table for settings/repository configuration. The ordering of the user-exit hooks and the
persistence step is derived from the L1 include architecture and the slice membership, not from a
citable functional source. [INFERRED]

## Standard SAP touchpoints

The process touches the standard SAP repository/transport/DDIC layer: it serialises and deserialises
objects reading/writing TADIR, E070/E071, REPOSRC and DD02L (plus TVDIR/TDDAT for table-maintenance
deserialization)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-workflow.md:30-33]. Online it
talks to a remote Git host over HTTP(S)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-workflow.md:18-27]; offline it
exchanges ZIP files
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-offline-airgapped.md:17-28]. The report
shell additionally borrows standard dynpro/selection-screen services (RPY_DYNPRO_READ/INSERT,
RS_SET_SELSCREEN_STATUS, RSDBRUNT) to host the HTML GUI on the report screen [INFERRED].

## Variants and exceptions

Two orthogonal variants. Connectivity: online (remote Git over HTTP(S): clone -> add/commit -> pull)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-online-workflow.md:18-27] versus
offline/air-gapped (ZIP import/export)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-offline-airgapped.md:17-28]. Execution:
interactive HTML GUI (sy-batch = false) versus unattended background sync (sy-batch = true ->
zcl_abapgit_background=>run)
[VERIFIED: slices/abapgit-standalone-demo/research/2026-07-03-runtime-trigger-dbt.md:21-24]. In this
system the background variant is an unused capability
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:20].

## Open points (process)

Whether any background sync is actually scheduled could not be confirmed against TBTCO/TBTCP because
the abap-fs MCP server is unavailable in this benchmark; it rests on owner input
[VERIFIED: slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md:20].
The concrete launching transaction / authorization wiring in this landscape is [UNVERIFIABLE]
without MCP. The chain is documented as a capability of the tool, not as a live business process
running in this demo system.

## Process sources

Auto-research evidence under slices/abapgit-standalone-demo/research/ (2026-07-03-purpose-abapgit.md,
2026-07-03-standalone-run-se38.md, 2026-07-03-runtime-trigger-dbt.md,
2026-07-03-persistence-credentials.md, 2026-07-03-online-workflow.md,
2026-07-03-offline-airgapped.md) and the owner expert answer
slices/abapgit-standalone-demo/inputs/expert-answers/2026-07-03-owner-demo-context.md. Object chain
from slices/abapgit-standalone-demo/membership.md; technical anchoring from the L1 page
wiki/ZABAPGIT/program-ZABAPGIT_STANDALONE.md (used to avoid contradiction, not cited as VERIFIED).

## User notes

<!-- Manual notes: never overwritten by the agent. -->

<!-- user-notes-end -->

<!-- ingest-history -->
- 2026-07-03 | L2 | process doc + gate ACCEPT (slice abapgit-standalone-demo)
