def decode_shift(s: str) -> str:
    return "".join(chr(ord(c) - 1) for c in s)