-- Migration 0002 (user_version 1 -> 2)
--
-- What it does: additive schema migration that removes the deprecated columns
--   analysis_code_path / analysis_sha256 from the objects table (always NULL in the single-page model).
-- How it works: two ALTER TABLE ... DROP COLUMN statements; the runner db.apply_migrations wraps the
--   file in BEGIN/COMMIT and bumps user_version, so this file must NOT open transactions or touch user_version.
-- Connections: executed by core/src/tools/db.py (apply_migrations) on a DB at user_version 1;
--   numbered in core/src/db/migrations/ and aligned to db.SCHEMA_VERSION. Tests: test_migrations.py.
--
-- Removes the deprecated columns analysis_code_path / analysis_sha256 from the
-- objects table. Single-page model (§2): the L1 code analysis and L2 functional
-- analysis live INLINE in the object page, never in a separate document; these
-- columns were always NULL and constituted pure architectural noise.
--
-- They are not referenced by any index, trigger, or view, so DROP COLUMN is safe.
-- Requires SQLite >= 3.35 (ALTER TABLE ... DROP COLUMN); guaranteed by Python >= 3.11.
-- The runner (db.apply_migrations) wraps this file in BEGIN/COMMIT + user_version bump:
-- this file must NOT open transactions or set user_version.
ALTER TABLE objects DROP COLUMN analysis_code_path;
ALTER TABLE objects DROP COLUMN analysis_sha256;
