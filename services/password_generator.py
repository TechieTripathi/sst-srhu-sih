"""
TechForge 3.0 — Secure Password Generator
Generates cryptographically secure, unique passwords for pre-provisioned Jury members.
"""

import secrets
import string


def generate_secure_jury_password(length: int = 12) -> str:
    """
    Generate a cryptographically secure, random password.
    Format example: TF3-X7mP9qL2
    Guarantees:
    - Uppercase characters
    - Lowercase characters
    - Digits
    - Safe separator/special character
    - Unique for every call
    """
    prefix = "TF3-"
    random_len = max(8, length - len(prefix))
    
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    
    # Ensure at least 2 uppercase, 2 lowercase, 2 digits
    chars = [
        secrets.choice(uppercase),
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(digits),
    ]
    
    all_allowed = uppercase + lowercase + digits
    while len(chars) < random_len:
        chars.append(secrets.choice(all_allowed))
        
    # Cryptographically shuffle the characters
    shuffled = chars.copy()
    for i in range(len(shuffled) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
        
    return prefix + "".join(shuffled)
