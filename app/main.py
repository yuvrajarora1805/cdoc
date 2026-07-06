import sys

# Import the Cython-compiled module
try:
    import run_carm_viewer
except ImportError as e:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Initialization Error", f"Failed to load application core.\n{e}")
    sys.exit(1)

if __name__ == '__main__':
    run_carm_viewer.main()
