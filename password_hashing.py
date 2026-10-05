import bcrypt
from werkzeug.security import check_password_hash


def password_matches(hashed: str, password: str) -> bool:
    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        # bcrypt hashes at most 72 bytes; reject longer strings without truncation.
        encoded = password.encode()
        if len(encoded) > 72:
            return False
        try:
            return bcrypt.checkpw(encoded, hashed.encode())
        except ValueError:
            return False
    return check_password_hash(hashed, password)
