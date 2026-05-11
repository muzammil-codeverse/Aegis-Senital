from __future__ import annotations

import numpy as np

from inference.model_pool import ModelPool, _InferenceRequest


class _FakeInnerModel:
    def __init__(self) -> None:
        self.float_called = False

    def float(self) -> None:
        self.float_called = True


class _FlakyHalfModel:
    def __init__(self) -> None:
        self.model = _FakeInnerModel()
        self.calls: list[bool] = []

    def __call__(self, frame, *, verbose: bool, device: str, half: bool):  # noqa: ANN001
        del frame, verbose, device
        self.calls.append(half)
        if half:
            raise RuntimeError(
                "expected mat1 and mat2 to have the same dtype, but got: struct c10::Half != float"
            )
        return ["ok"]


def test_model_pool_fp16_retry_falls_back_to_fp32() -> None:
    pool = ModelPool()
    original_use_half = pool._use_half
    original_device = pool._device
    try:
        pool._use_half = True
        pool._device = "cuda"
        model = _FlakyHalfModel()
        request = _InferenceRequest(
            model_type="weapon",
            frame=np.zeros((8, 8, 3), dtype=np.uint8),
        )

        result = pool._run_request(model, request)

        assert result == ["ok"]
        assert model.calls == [True, False]
        assert pool.use_half is False
        assert model.model.float_called is True
    finally:
        pool._use_half = original_use_half
        pool._device = original_device
