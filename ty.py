import os
from PIL import Image

# Get the absolute path
file_path = os.path.abspath("back.png")

# Debugging - Print the file path to check if it's correct
print("Looking for file at:", file_path)

# Open the image
bg_image = Image.open(file_path)
