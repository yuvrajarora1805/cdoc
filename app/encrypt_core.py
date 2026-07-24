import os
import sys
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet

def derive_key(signature_hex, machine_id):
    """Derives a Fernet-compatible key using PBKDF2."""
    salt = machine_id.encode('utf-8')
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(signature_hex.encode('utf-8')))
    return key

def encrypt_file(input_path, output_path, signature_hex, machine_id):
    key = derive_key(signature_hex, machine_id)
    f = Fernet(key)
    
    with open(input_path, 'rb') as file:
        original_data = file.read()
        
    encrypted_data = f.encrypt(original_data)
    
    with open(output_path, 'wb') as file:
        file.write(encrypted_data)
    
    print(f"Successfully encrypted {input_path} -> {output_path}")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python encrypt_core.py <input_file> <output_file> <license_signature_hex> <machine_id>")
        sys.exit(1)
        
    encrypt_file(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
