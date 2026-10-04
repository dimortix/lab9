"""Класс Calculator с бизнес-логикой — объект модульного тестирования ЛР6."""
import math
from numbers import Real


class Calculator:
    @staticmethod
    def _check_numbers(*values):
        # bool формально подкласс int, но True + True как арифметика здесь не нужна
        for value in values:
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"Ожидалось число, получено {type(value).__name__}")

    def add(self, a, b):
        self._check_numbers(a, b)
        return a + b

    def subtract(self, a, b):
        self._check_numbers(a, b)
        return a - b

    def multiply(self, a, b):
        self._check_numbers(a, b)
        return a * b

    def divide(self, a, b):
        self._check_numbers(a, b)
        if b == 0:
            raise ZeroDivisionError("Деление на ноль невозможно")
        return a / b

    def is_prime_number(self, n):
        if isinstance(n, bool) or not isinstance(n, int):
            raise TypeError("Простота определяется только для целых чисел")
        if n < 2:
            return False
        if n % 2 == 0:
            return n == 2
        return all(n % d for d in range(3, math.isqrt(n) + 1, 2))
