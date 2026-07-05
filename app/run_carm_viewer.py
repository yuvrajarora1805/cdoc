import sys
import os
import uuid
import requests
import tkinter as tk
from tkinter import simpledialog, messagebox
from carm_multi_viewer.gui import run

def get_machine_id():
    # Use MAC address as a simple unique machine identifier
    return str(uuid.getnode())

def verify_license(key):
    machine_id = get_machine_id()
    try:
        # Pointing to the Node.js API server
        response = requests.post("http://localhost:3003/api/verify", json={
            "key": key,
            "machine_id": machine_id
        }, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("valid", False)
        return False
    except requests.RequestException:
        messagebox.showerror("Connection Error", "Could not connect to the licensing server. Please check your internet connection.")
        return False

def main():
    root = tk.Tk()
    root.withdraw() # Hide the main window

    license_file = "license.key"
    key = None

    if os.path.exists(license_file):
        with open(license_file, "r") as f:
            key = f.read().strip()

    if not key:
        key = simpledialog.askstring("License Required", "Please enter your License Key:")
        if not key:
            sys.exit(0)
    
    # Verify the key
    if verify_license(key):
        # Save valid key so user doesn't have to enter it again
        with open(license_file, "w") as f:
            f.write(key)
        
        root.destroy()
        # Launch the actual application
        run()
    else:
        messagebox.showerror("Invalid License", "The license key is invalid or expired.")
        # Remove invalid key if it exists
        if os.path.exists(license_file):
            os.remove(license_file)
        sys.exit(1)

if __name__ == "__main__":
    main()
