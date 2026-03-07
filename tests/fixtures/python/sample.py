"""A sample Python module for testing extraction."""

# Module-level constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT: int = 30

LOOKUP_TABLE = {
    "a": 1,
    "b": 2,
    "c": 3,
}


def simple_function():
    """A simple top-level function."""
    return 42


def function_with_args(x: int, y: str = "hello") -> bool:
    """Function with typed arguments."""
    return len(y) > x


async def async_handler(request: dict) -> dict:
    """An async function."""
    return {"status": "ok"}


def outer_function():
    """Function containing a nested function."""

    def inner_function():
        """The nested function."""
        return "inner"

    return inner_function()


#@@start config-section
MAX_POOL_SIZE = 10
MIN_POOL_SIZE = 1
#@@end config-section


@property
def my_property(self):
    return self._value


class SimpleClass:
    """A simple class."""

    class_var = "hello"

    def __init__(self, value: int):
        self.value = value

    def get_value(self) -> int:
        """Get the value."""
        return self.value

    @staticmethod
    def static_method():
        """A static method."""
        return True

    @classmethod
    def from_string(cls, s: str) -> "SimpleClass":
        """Create from string."""
        return cls(int(s))

    class InnerClass:
        """A nested class."""

        def inner_method(self):
            return "inner"


class AsyncProcessor:
    """Class with async methods."""

    async def process(self, data: list) -> dict:
        """Process data asynchronously."""
        #@@start processing-logic
        result = {}
        for item in data:
            result[item] = True
        #@@end processing-logic
        return result

    async def cleanup(self):
        pass


def function_with_complex_sig(
    items: list[str],
    *args: int,
    callback: callable = None,
    **kwargs: str,
) -> list[dict]:
    """Function with a complex signature."""
    return []
