"""Fixture for testing decorated classes and edge cases."""

from dataclasses import dataclass


@dataclass
class Config:
    """A decorated class."""

    host: str = "localhost"
    port: int = 8080


@dataclass
class ChildConfig(Config):
    """Inheriting decorated class."""

    debug: bool = False


class Outer:
    """Outer class for deep nesting tests."""

    class Middle:
        """Middle level."""

        class Inner:
            """Deeply nested class."""

            def deep_method(self):
                return "deep"


def valid_path():
    """For testing dotted path where middle segment exists."""

    def level_one():
        def level_two():
            return "found"

        return level_two

    return level_one


def has_kwonly_args(*, key: str, value: int = 0) -> dict:
    """Function with keyword-only args."""
    return {key: value}
