import secrets


def generate_code():
    return "".join(str(secrets.randbelow(10)) for _ in range(6))
