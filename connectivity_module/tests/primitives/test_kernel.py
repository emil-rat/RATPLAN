"""Tests for ArdKernel's product-of-exponentials covariance (kernel.py)."""

import numpy as np
import pytest

from ratplan_connectivity.primitives.features import GridFeatures
from ratplan_connectivity.primitives.kernel import ArdKernel


def _features(rows: list[list[float]]) -> GridFeatures:
    return GridFeatures(values=np.array(rows, dtype=np.float64))


def test_self_variance_equals_alpha():
    kernel = ArdKernel(alpha=25.0)
    assert kernel.self_variance() == 25.0


def test_kernel_value_at_zero_distance_equals_alpha():
    kernel = ArdKernel(alpha=10.0)
    z = [1.0, 2.0, 3.0, 5.0, 0.5, 0.5, 1.0]
    matrix = kernel.matrix(_features([z]))
    assert matrix[0, 0] == pytest.approx(10.0)


def test_kernel_decreases_with_distance():
    kernel = ArdKernel()
    origin = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    near = [10.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    far = [1000.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    matrix = kernel.matrix(_features([origin, near, far]))
    assert matrix[0, 1] > matrix[0, 2]


def test_kernel_decreases_with_distance_feature_alone():
    kernel = ArdKernel()
    origin = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    near = [0.0, 0.0, 0.0, 10.0, 0.0, 1.0, 0.0]
    far = [0.0, 0.0, 0.0, 1000.0, 0.0, 1.0, 0.0]
    matrix = kernel.matrix(_features([origin, near, far]))
    assert matrix[0, 1] > matrix[0, 2]


def test_matrix_is_symmetric():
    kernel = ArdKernel()
    rng = np.random.default_rng(0)
    matrix = kernel.matrix(_features(rng.normal(size=(5, 7)).tolist()))
    assert np.allclose(matrix, matrix.T)


def test_matrix_is_positive_semidefinite():
    kernel = ArdKernel()
    rng = np.random.default_rng(1)
    matrix = kernel.matrix(_features(rng.normal(size=(20, 7)).tolist()))
    eigenvalues = np.linalg.eigvalsh(matrix)
    assert eigenvalues.min() > -1e-8


def test_cross_matches_matrix_row():
    kernel = ArdKernel()
    rng = np.random.default_rng(2)
    values = rng.normal(size=(6, 7))
    features = _features(values.tolist())
    matrix = kernel.matrix(features)
    cross = kernel.cross(values[2], features)
    assert np.allclose(cross, matrix[2])
