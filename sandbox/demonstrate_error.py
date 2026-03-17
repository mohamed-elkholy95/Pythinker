import sys


def demonstrate_improved_error_message():
    try:
        # Intentionally create a TypeError with a common typo
        "hello".split(max_split=1)
    except TypeError as e:
        print(f"Caught TypeError: {e}")
        print("\n--- Expected improved error message for max_split vs maxsplit ---\n")


if __name__ == "__main__":
    print(f"Running Python version: {sys.version.split()[0]}")
    demonstrate_improved_error_message()
