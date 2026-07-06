import sys
import os
import uuid
import json
import base64
import datetime
import requests
import tkinter as tk
from tkinter import simpledialog, messagebox
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from carm_multi_viewer.gui import run

# ── HARDCODED RSA PUBLIC KEY ──────────────────────────────────────────────────
# IMPORTANT: Replace the dummy key below with your ACTUAL RSA PUBLIC KEY!
# You can find your real public key by looking at the logs of your backend server,
# or by checking the `settings` table in your MySQL database.
# Ensure you keep the exact PEM format (-----BEGIN PUBLIC KEY----- ... -----END PUBLIC KEY-----)
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyvU4b6Jm0l0v34rZpZtM
8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m
8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m
8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m
8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m
8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m
8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m8m0m
-----END PUBLIC KEY-----"""

LICENSE_FILE = "license.lic"

def get_machine_id():
    # Use MAC address as a unique machine ID
    return str(uuid.getnode())

def verify_signature_offline(license_data, signature_hex):
    """Verifies RSA signature of the license data using the hardcoded Public Key."""
    try:
        public_key = load_pem_public_key(PUBLIC_KEY_PEM.encode('utf-8'))
        signature = bytes.fromhex(signature_hex)
        
        # Serialize exactly as server did (compact JSON string)
        data_bytes = json.dumps(license_data, separators=(',', ':')).encode('utf-8')
        
        # Verify SHA256 RSA PKCS1v15 Signature
        public_key.verify(
            signature,
            data_bytes,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        return True
    except Exception as e:
        print("Signature verification failed:", e)
        return False

def validate_license_offline():
    """Reads license file and checks offline signature, machine ID, and expiry date."""
    if not os.path.exists(LICENSE_FILE):
        return False, "No license file found."
    
    try:
        with open(LICENSE_FILE, "r") as f:
            lic_obj = json.load(f)
        
        license_data = lic_obj.get("license_data")
        signature = lic_obj.get("signature")
        
        if not license_data or not signature:
            return False, "Invalid license file structure."
        
        # 1. Verify Cryptographic Signature
        if not verify_signature_offline(license_data, signature):
            return False, "License signature is invalid (tampered file)."
        
        # 2. Verify Machine ID matches
        local_machine = get_machine_id()
        if license_data.get("machine_id") != local_machine:
            return False, f"License bound to another machine.\n\nLocal: {local_machine}\nLicense: {license_data.get('machine_id')}"
        
        # 3. Verify Expiry Date
        expires_at_str = license_data.get("expires_at")
        if expires_at_str:
            # Parse ISO string
            expires_at = datetime.datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            # Make timezone aware comparison in UTC
            now = datetime.datetime.now(datetime.timezone.utc)
            if expires_at < now:
                return False, f"License expired on {expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        
        return True, "License valid (Offline)"
    except Exception as e:
        return False, f"Error reading license: {str(e)}"

def activate_license_online(key):
    """Hits the online endpoint to bind machine and fetch signed license payload."""
    machine_id = get_machine_id()
    try:
        response = requests.post("https://lic.omvky.com/api/verify", json={
            "key": key,
            "machine_id": machine_id
        }, timeout=8)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("valid") and "license_data" in data and "signature" in data:
                # Save offline license file
                with open(LICENSE_FILE, "w") as f:
                    json.dump({
                        "license_data": data["license_data"],
                        "signature": data["signature"]
                    }, f, indent=4)
                return True, "License activated successfully!"
            else:
                return False, data.get("message", "Invalid license key.")
        return False, f"Server returned error code {response.status_code}"
    except requests.RequestException as e:
        return False, f"Could not connect to activation server: {str(e)}"

def main():
    root = tk.Tk()
    root.withdraw() # Hide empty window

    # 1. Attempt Offline Verification first
    valid, message = validate_license_offline()
    if valid:
        print("Offline verification successful. Starting viewer...")
        root.destroy()
        run()
        sys.exit(0)
    
    # If offline check failed (or file missing), show message and request activation key
    print(f"Offline validation failed: {message}")
    if os.path.exists(LICENSE_FILE):
        messagebox.showwarning("License Verification Failed", f"Offline license invalid: {message}\n\nPlease re-activate.")
    
    # 2. Get key for online activation
    key = simpledialog.askstring("Activation Required", "Please enter your License Activation Key:")
    if not key:
        sys.exit(0)
        
    # Attempt activation
    success, act_msg = activate_license_online(key.strip())
    if success:
        messagebox.showinfo("Activation Successful", "License successfully verified and activated offline!")
        root.destroy()
        run()
    else:
        messagebox.showerror("Activation Failed", f"Activation failed: {act_msg}")
        if os.path.exists(LICENSE_FILE):
            os.remove(LICENSE_FILE)
        sys.exit(1)

if __name__ == "__main__":
    main()
