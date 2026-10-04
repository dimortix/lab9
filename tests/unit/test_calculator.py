import pytest

import pytest

from src.calculator import Calculator

# Все тесты файла относятся к набору unit (см. маркеры в pytest.ini).
pytestmark = pytest.mark.unit


@pytest.fixture
def calc():
    return Calculator()


@pytest.mark.parametrize("a, b, expected", [
    (2, 3, 5),
    (-2, -3, -5),
    (-5, 5, 0),
    (0, 0, 0),
    (2.5, 0.5, 3.0),
    (10**18, 1, 10**18 + 1),
])
def test_add(calc, a, b, expected):
    assert calc.add(a, b) == expected


def test_add_floats_with_rounding_error(calc):
    # 0.1 + 0.2 в двоичной арифметике даёт 0.30000000000000004
    assert calc.add(0.1, 0.2) == pytest.approx(0.3)


@pytest.mark.parametrize("a, b, expected", [
    (10, 4, 6),
    (4, 10, -6),
    (-3, -3, 0),
    (0, 7, -7),
    (5.5, 2.25, 3.25),
])
def test_subtract(calc, a, b, expected):
    assert calc.subtract(a, b) == expected


@pytest.mark.parametrize("a, b, expected", [
    (3, 4, 12),
    (-3, 4, -12),
    (-3, -4, 12),
    (123456, 0, 0),
    (1.5, 2, 3.0),
])
def test_multiply(calc, a, b, expected):
    assert calc.multiply(a, b) == expected


@pytest.mark.parametrize("a, b, expected", [
    (10, 2, 5),
    (7, 2, 3.5),
    (-9, 3, -3),
    (-9, -3, 3),
    (0, 5, 0),
    (1, 3, pytest.approx(0.333333, rel=1e-5)),
])
def test_divide(calc, a, b, expected):
    assert calc.divide(a, b) == expected


@pytest.mark.parametrize("a, zero", [(1, 0), (-5, 0), (0, 0), (3.7, 0.0)])
def test_divide_by_zero_raises(calc, a, zero):
    with pytest.raises(ZeroDivisionError, match="Деление на ноль невозможно"):
        calc.divide(a, zero)


@pytest.mark.parametrize("method", ["add", "subtract", "multiply", "divide"])
@pytest.mark.parametrize("bad", ["2", None, [1], True])
def test_arithmetic_rejects_non_numbers(calc, method, bad):
    with pytest.raises(TypeError, match="Ожидалось число"):
        getattr(calc, method)(bad, 1)


@pytest.mark.parametrize("n", [2, 3, 5, 7, 11, 13, 97, 7919, 2_147_483_647])
def test_is_prime_true(calc, n):
    assert calc.is_prime_number(n) is True


@pytest.mark.parametrize("n", [-7, -1, 0, 1, 4, 9, 15, 25, 100, 561, 7917, 2_147_483_649])
def test_is_prime_false(calc, n):
    assert calc.is_prime_number(n) is False


@pytest.mark.parametrize("bad", [7.0, "7", None, True])
def test_is_prime_rejects_non_integers(calc, bad):
    with pytest.raises(TypeError):
        calc.is_prime_number(bad)
