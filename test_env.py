import sys
import os
print(f"Python: {sys.executable}")
print(f"CWD: {os.getcwd()}")
try:
    import google.genai
    print("Success: google.genai imported")
except ImportError as e:
    print(f"Error: {e}")
try:
    import PIL
    print("Success: PIL imported")
except ImportError as e:
    print(f"Error: PIL: {e}")
