import sys
import os
import datetime

with open("debug_log.txt", "w") as f:
    f.write(f"Started at {datetime.datetime.now()}\n")
    f.write(f"Python: {sys.executable}\n")
    f.write(f"CWD: {os.getcwd()}\n")
    
    print(f"Python: {sys.executable}")
    print(f"CWD: {os.getcwd()}")
    
    try:
        import google.genai
        f.write("Success: google.genai imported\n")
        print("Success: google.genai imported")
    except ImportError as e:
        f.write(f"Error: {e}\n")
        print(f"Error: {e}")
        
    try:
        import PIL
        f.write("Success: PIL imported\n")
        print("Success: PIL imported")
    except ImportError as e:
        f.write(f"Error: PIL: {e}\n")
        print(f"Error: PIL: {e}")
