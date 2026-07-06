import sys
from PIL import Image

input_path = sys.argv[1]
output_path = sys.argv[2]

try:
    img = Image.open(input_path)
    # Ensure it is square (or just save directly as ICO)
    # The ICO format supports multiple sizes, but we'll just use the default save behavior
    img.save(output_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    print(f"Successfully converted {input_path} to {output_path}")
except Exception as e:
    print(f"Failed to convert image: {e}")
