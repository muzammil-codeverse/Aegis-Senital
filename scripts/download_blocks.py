import urllib.request
import zipfile
import os

url = 'https://github.com/Cosys-Lab/Cosys-AirSim/releases/download/5.5-v3.3/Blocks_packaged_Windows_55_33.zip'
dest = r'C:\AegisExternalTools\drone_sim\runtime\downloads\Blocks.zip'
ext = r'C:\AegisExternalTools\drone_sim\runtime\environments\Blocks'

os.makedirs(os.path.dirname(dest), exist_ok=True)
print('Downloading...')
urllib.request.urlretrieve(url, dest)
print('Downloaded.')

os.makedirs(ext, exist_ok=True)
print('Extracting...')
with zipfile.ZipFile(dest, 'r') as z:
    z.extractall(ext)
print('Extracted.')
