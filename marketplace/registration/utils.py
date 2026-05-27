import random


def generate_code():
    return "".join([random.randint(1, 9) for _ in range(6)])
