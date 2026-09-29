"""Small, reusable helpers for validating data and calculating statistics."""

from collections import Counter
import math
import re
import statistics


MAX_VALUES = 10_000
MAX_ABSOLUTE_VALUE = 1e100
MAX_INPUT_LENGTH = 200_000

# Accept normal decimals and scientific notation, but not Python-specific
# numbers such as NaN, infinity, underscores, or hexadecimal literals.
NUMBER_PATTERN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)


def parse_dataset(raw_text):
    """Return finite floats from comma-, whitespace-, or newline-separated text."""
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ValueError("Enter at least one number before calculating.")
    if len(raw_text) > MAX_INPUT_LENGTH:
        raise ValueError("Your dataset is too long. Use at most 200,000 characters.")

    tokens = [token for token in re.split(r"[,\s]+", raw_text.strip()) if token]
    if not tokens:
        raise ValueError("Enter at least one number before calculating.")
    if len(tokens) > MAX_VALUES:
        raise ValueError("Use at most 10,000 numbers in one calculation.")

    values = []
    for index, token in enumerate(tokens, start=1):
        if not NUMBER_PATTERN.fullmatch(token):
            # Limit the preview so a long invalid token cannot flood the page.
            preview = token[:35] + ("…" if len(token) > 35 else "")
            raise ValueError(f'Value {index} ("{preview}") is not a valid number.')
        value = float(token)
        if not math.isfinite(value) or abs(value) > MAX_ABSOLUTE_VALUE:
            raise ValueError(f"Value {index} must be finite and between -1e100 and 1e100.")
        values.append(value)
    return values


def calculate_statistics(values):
    """Calculate population statistics; all equally frequent modes are returned.

    A dataset with distinct values has no mode. A singleton has its only value
    as its mode. Variance divides by N (population), so a singleton's variance
    and standard deviation are both zero.
    """
    if not values:
        raise ValueError("Enter at least one number before calculating.")

    ordered = sorted(values)
    frequencies = Counter(values)
    highest_frequency = max(frequencies.values())
    modes = (
        sorted(value for value, frequency in frequencies.items() if frequency == highest_frequency)
        if highest_frequency > 1 or len(values) == 1
        else []
    )
    variance = statistics.pvariance(values)
    return {
        "count": len(values),
        "sum": math.fsum(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "mode": modes,
        "min": ordered[0],
        "max": ordered[-1],
        "range": ordered[-1] - ordered[0],
        "variance": variance,
        # pstdev keeps tiny deviations accurate even when variance underflows.
        "standard_deviation": statistics.pstdev(values),
        "sorted": ordered,
    }


def format_number(value):
    """Format readable results without rounding tiny nonzero values to zero."""
    number = float(value)
    if number == 0:
        return "0"
    if abs(number) >= 1e12 or abs(number) < 1e-6:
        mantissa, exponent = f"{number:.6e}".split("e")
        return f"{mantissa.rstrip('0').rstrip('.')}e{int(exponent):+d}"
    return f"{number:,.6f}".rstrip("0").rstrip(".")
