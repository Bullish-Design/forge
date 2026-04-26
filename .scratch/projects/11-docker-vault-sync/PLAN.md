# PLAN

## Mandatory Rule
NO SUBAGENTS. All work done directly.

## Goal
Run Forge with vault data inside a Docker named volume and provide UV Python scripts for host import/export.

## Steps
1. Update compose vault mounts to named volume.
2. Add `import_vault.py` and `export_vault.py` UV scripts in `docker/`.
3. Update env/docs to explain sync workflow.
4. Validate compose and script help output.

## Mandatory Rule
NO SUBAGENTS.
