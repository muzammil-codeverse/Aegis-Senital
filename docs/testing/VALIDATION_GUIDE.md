# Validation and testing guide

## Windows native-extension flake policy

Some optional stacks (for example `torch` / `torchreid` / CUDA-backed paths) can intermittently fault on Windows when native code raises access violations. **Always run the full Python suite with faulthandler enabled** so faults surface as Python tracebacks instead of silent process exit:

- `PYTHONFAULTHANDLER=1` (set by `scripts/run_validation_suite.py` and `scripts/run_full_validation.py`)
- `python -X faulthandler -m pytest ...`

## Controlled pytest basetemp

Keep pytest basetemp under `storage/pytest_basetemp` (or `storage/pytest_basetemp_fh` for historical runs) so long paths and artifacts stay out of the repo root and are easy to clean.

## Commands

**Full Python validation (recommended daily):**

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\run_validation_suite.py
```

**Full project gate (compileall + pytest + validate_runtime + frontend build):**

```powershell
python scripts\run_full_validation.py
```

Optional CUDA smoke:

```powershell
python scripts\run_full_validation.py --include-smoke
```

**Focused model governance tests:**

```powershell
python -X faulthandler -m pytest tests/test_model_governance_config.py tests/test_model_registry_completeness.py tests/test_model_governance_service.py tests/test_model_governance_routes.py tests/test_model_drift_service.py tests/test_model_promotion_policy.py tests/test_model_rollback.py tests/test_identity_candidate_emission.py tests/test_liveness_governance.py tests/test_validation_suite_runner.py -vv --basetemp storage\pytest_basetemp
```

## Safe local smoke assets

Do not commit weights or generated benchmark artifacts. For optional smoke checks, place operator-provided assets outside tracked paths referenced by environment variables (for example `AEGIS_OPEN_VOCAB_MODEL_PATH`) or follow `models/registry.json` paths only after you mirror weights locally.
