import sys
import os
import uuid
import json
import shutil
import datetime
import requests
import tkinter as tk
from tkinter import messagebox, filedialog
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet
import importlib.util

# Removed static import of gui to allow dynamic decrypted loading
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
    return str(uuid.getnode())

def derive_key(signature_hex, machine_id):
    """Derives a Fernet-compatible key using PBKDF2."""
    salt = machine_id.encode('utf-8')
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(signature_hex.encode('utf-8')))

def check_time_tampering():
    """Checks if the system clock has been rolled back."""
    time_file = os.path.join(os.getenv('APPDATA', ''), 'HelixCare', 'sys_time.dat')
    os.makedirs(os.path.dirname(time_file), exist_ok=True)
    
    current_time = datetime.datetime.now(datetime.timezone.utc)
    
    if os.path.exists(time_file):
        try:
            with open(time_file, "r") as f:
                last_time_str = f.read().strip()
            last_time = datetime.datetime.fromisoformat(last_time_str)
            if current_time < last_time:
                return False, f"Time tampering detected! System clock was rolled back.\nLast run: {last_time}\nCurrent time: {current_time}"
        except Exception:
            pass # File corrupted or unreadable, ignore for now
            
    # Update the time file
    try:
        with open(time_file, "w") as f:
            f.write(current_time.isoformat())
    except Exception:
        pass
        
    return True, ""


def verify_signature_offline(license_data, signature_hex):
    """Verifies RSA signature of the license data using the hardcoded Public Key."""
    try:
        public_key = load_pem_public_key(PUBLIC_KEY_PEM.encode('utf-8'))
        signature = bytes.fromhex(signature_hex)
        data_bytes = json.dumps(license_data, separators=(',', ':')).encode('utf-8')
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
        if not verify_signature_offline(license_data, signature):
            return False, "License signature is invalid (tampered file)."
        local_machine = get_machine_id()
        if license_data.get("machine_id") != local_machine:
            return False, f"License bound to another machine.\n\nLocal: {local_machine}\nLicense: {license_data.get('machine_id')}"
        expires_at_str = license_data.get("expires_at")
        if expires_at_str:
            expires_at = datetime.datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            if expires_at < now:
                return False, f"License expired on {expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        return True, "License valid (Offline)", derive_key(signature, local_machine)
    except Exception as e:
        return False, f"Error reading license: {str(e)}", None

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
                with open(LICENSE_FILE, "w") as f:
                    json.dump({
                        "license_data": data["license_data"],
                        "signature": data["signature"]
                    }, f, indent=4)
                return True, "License activated successfully!", derive_key(data["signature"], machine_id)
            else:
                return False, data.get("message", "Invalid license key."), None
        return False, f"Server returned error code {response.status_code}", None
    except requests.RequestException as e:
        return False, f"Could not connect to activation server: {str(e)}", None

def show_activation_window():
    """
    Shows a professional activation window with:
    - Machine ID display (copy button)
    - Import .lic file button
    - Online activation input
    """
    machine_id = get_machine_id()
    result = {"action": None, "key": None}

    win = tk.Tk()
    win.title("HelixCare — Activation Required")
    win.geometry("520x480")
    win.resizable(False, False)
    win.configure(bg="#0d1117")

    # ── Fonts & Colors ──
    BG = "#0d1117"
    SURFACE = "#161b22"
    BORDER = "#30363d"
    BLUE = "#2563eb"
    TEXT = "#e6edf3"
    MUTED = "#8b949e"
    SUCCESS = "#22c55e"

    # ── Header ──
    header_frame = tk.Frame(win, bg=SURFACE, pady=16)
    header_frame.pack(fill="x")

    tk.Label(header_frame, text="🧬 HelixCare", font=("Segoe UI", 18, "bold"),
             bg=SURFACE, fg=TEXT).pack()
    tk.Label(header_frame, text="by Omvky — License Activation", font=("Segoe UI", 10),
             bg=SURFACE, fg=MUTED).pack()

    # ── Machine ID Section ──
    mid_frame = tk.Frame(win, bg=BG, padx=28, pady=18)
    mid_frame.pack(fill="x")

    tk.Label(mid_frame, text="Your Machine ID", font=("Segoe UI", 9, "bold"),
             bg=BG, fg=MUTED).pack(anchor="w")
    tk.Label(mid_frame,
             text="Share this ID with Omvky support to receive your offline license file.",
             font=("Segoe UI", 8), bg=BG, fg=MUTED, wraplength=460, justify="left").pack(anchor="w", pady=(2,8))

    mid_inner = tk.Frame(mid_frame, bg=SURFACE, padx=12, pady=10,
                         highlightbackground=BORDER, highlightthickness=1)
    mid_inner.pack(fill="x")

    mid_var = tk.StringVar(value=machine_id)
    mid_entry = tk.Entry(mid_inner, textvariable=mid_var, font=("Courier New", 13, "bold"),
                         bg=SURFACE, fg=SUCCESS, bd=0, readonlybackground=SURFACE,
                         state="readonly", width=28)
    mid_entry.pack(side="left", fill="x", expand=True)

    def copy_mid():
        win.clipboard_clear()
        win.clipboard_append(machine_id)
        copy_btn.config(text="✔ Copied!")
        win.after(1800, lambda: copy_btn.config(text="⎘ Copy"))

    copy_btn = tk.Button(mid_inner, text="⎘ Copy", command=copy_mid,
                         font=("Segoe UI", 9, "bold"), bg=BLUE, fg="white",
                         activebackground="#1d4ed8", activeforeground="white",
                         bd=0, padx=12, pady=4, cursor="hand2")
    copy_btn.pack(side="right")

    sep = tk.Frame(win, bg=BORDER, height=1)
    sep.pack(fill="x", padx=28, pady=4)

    # ── Import License File ──
    import_frame = tk.Frame(win, bg=BG, padx=28, pady=10)
    import_frame.pack(fill="x")

    tk.Label(import_frame, text="Already have a license file?",
             font=("Segoe UI", 9, "bold"), bg=BG, fg=TEXT).pack(anchor="w")
    tk.Label(import_frame,
             text="Click below to import the license.lic file sent to you by Omvky.",
             font=("Segoe UI", 8), bg=BG, fg=MUTED).pack(anchor="w", pady=(2,8))

    def import_lic():
        path = filedialog.askopenfilename(
            title="Select your license.lic file",
            filetypes=[("License File", "*.lic"), ("All Files", "*.*")]
        )
        if path:
            shutil.copy(path, LICENSE_FILE)
            result["action"] = "imported"
            win.destroy()

    tk.Button(import_frame, text="📂  Import License File", command=import_lic,
              font=("Segoe UI", 10, "bold"), bg="#1c2333", fg=TEXT,
              activebackground=BORDER, activeforeground=TEXT,
              bd=0, pady=10, cursor="hand2", highlightbackground=BORDER,
              highlightthickness=1).pack(fill="x")

    sep2 = tk.Frame(win, bg=BORDER, height=1)
    sep2.pack(fill="x", padx=28, pady=4)

    # ── Online Activation ──
    online_frame = tk.Frame(win, bg=BG, padx=28, pady=10)
    online_frame.pack(fill="x")

    tk.Label(online_frame, text="Or activate online with a license key:",
             font=("Segoe UI", 9, "bold"), bg=BG, fg=TEXT).pack(anchor="w", pady=(0,6))

    key_inner = tk.Frame(online_frame, bg=SURFACE, padx=10, pady=8,
                         highlightbackground=BORDER, highlightthickness=1)
    key_inner.pack(fill="x")

    key_var = tk.StringVar()
    tk.Entry(key_inner, textvariable=key_var, font=("Courier New", 11),
             bg=SURFACE, fg=TEXT, bd=0, insertbackground=TEXT,
             placeholder_text="LIC-XXXX-XXXX-XXXX").pack(side="left", fill="x", expand=True)

    def activate_online():
        key = key_var.get().strip()
        if not key:
            messagebox.showwarning("Missing Key", "Please enter your license key.", parent=win)
            return
        result["action"] = "online"
        result["key"] = key
        win.destroy()

    tk.Button(key_inner, text="Activate", command=activate_online,
              font=("Segoe UI", 9, "bold"), bg=BLUE, fg="white",
              activebackground="#1d4ed8", activeforeground="white",
              bd=0, padx=14, pady=4, cursor="hand2").pack(side="right")

    win.mainloop()
    return result

def load_and_run_core(decryption_key=None):
    """Dynamically decrypts and loads the core GUI module, or runs the unencrypted one if in dev mode."""
    # Check time tampering
    time_ok, time_msg = check_time_tampering()
    if not time_ok:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Security Error", time_msg)
        sys.exit(1)

    enc_path = os.path.join(os.path.dirname(__file__), "carm_multi_viewer", "gui_encrypted.enc")
    dev_path = os.path.join(os.path.dirname(__file__), "carm_multi_viewer", "gui.py")

    if os.path.exists(enc_path) and decryption_key:
        try:
            f = Fernet(decryption_key)
            with open(enc_path, "rb") as file:
                encrypted_data = file.read()
            decrypted_code = f.decrypt(encrypted_data)
            
            # Dynamically load the decrypted code as a module
            spec = importlib.util.spec_from_loader('carm_multi_viewer.gui', loader=None)
            gui_module = importlib.util.module_from_spec(spec)
            sys.modules['carm_multi_viewer.gui'] = gui_module
            exec(decrypted_code, gui_module.__dict__)
            
            print("Successfully decrypted and loaded core application logic.")
            gui_module.run()
        except Exception as e:
            root = tk.Tk(); root.withdraw()
            messagebox.showerror("Security Error", f"Failed to decrypt core application. License key is invalid or tampered.\n{e}")
            sys.exit(1)
    elif os.path.exists(dev_path):
        print("Running unencrypted core (Dev Mode).")
        from carm_multi_viewer.gui import run
        run()
    else:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Error", "Core application files are missing.")
        sys.exit(1)


def main():
    # 1. Attempt offline verification first
    valid, message, derived_key = validate_license_offline()
    if valid:
        print("Offline verification successful. Starting viewer...")
        load_and_run_core(derived_key)
        sys.exit(0)

    # 2. If a license file exists but is invalid, warn the user
    if os.path.exists(LICENSE_FILE):
        root = tk.Tk(); root.withdraw()
        messagebox.showwarning(
            "License Invalid",
            f"Your existing license is invalid:\n\n{message}\n\nPlease import a new license file or re-activate.",
            parent=root
        )
        root.destroy()
        if os.path.exists(LICENSE_FILE):
            os.remove(LICENSE_FILE)

    # 3. Show the full activation window
    while True:
        result = show_activation_window()

        if result["action"] == "imported":
            # Re-validate the imported file
            valid, msg, derived_key = validate_license_offline()
            if valid:
                root = tk.Tk(); root.withdraw()
                messagebox.showinfo("Activated!", "License imported and verified successfully! Starting HelixCare...")
                root.destroy()
                load_and_run_core(derived_key)
                sys.exit(0)
            else:
                root = tk.Tk(); root.withdraw()
                messagebox.showerror("Invalid License File", f"The imported file is not valid:\n\n{msg}", parent=root)
                root.destroy()
                if os.path.exists(LICENSE_FILE):
                    os.remove(LICENSE_FILE)
                continue

        elif result["action"] == "online":
            success, act_msg, derived_key = activate_license_online(result["key"])
            if success:
                root = tk.Tk(); root.withdraw()
                messagebox.showinfo("Activated!", "License activated successfully! Starting HelixCare...")
                root.destroy()
                load_and_run_core(derived_key)
                sys.exit(0)
            else:
                root = tk.Tk(); root.withdraw()
                messagebox.showerror("Activation Failed", f"Activation failed:\n\n{act_msg}", parent=root)
                root.destroy()
                continue

        else:
            # User closed the window without activating
            sys.exit(0)

if __name__ == "__main__":
    main()
