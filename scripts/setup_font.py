#!/usr/bin/env python3
"""Script to automatically download DejaVu Sans font for PDF Cyrillic support."""

import os
import sys
import urllib.request
import zipfile
import tempfile
from pathlib import Path

# DejaVu Sans font download URLs
# GitHub releases - zip archive with all fonts
DEJAVU_ZIP_URL = "https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip"

FONTS_DIR = Path(__file__).parent.parent / "fonts"
FONT_FILE = FONTS_DIR / "DejaVuSans.ttf"


def download_font() -> bool:
    """Download DejaVu Sans font if it doesn't exist."""
    if FONT_FILE.exists():
        print(f"✓ Font already exists: {FONT_FILE}")
        return True

    print(f"Downloading DejaVu Sans font...")
    print(f"URL: {DEJAVU_ZIP_URL}")
    
    FONTS_DIR.mkdir(exist_ok=True, parents=True)
    
    try:
        # Download zip archive
        req = urllib.request.Request(DEJAVU_ZIP_URL)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
            tmp_path = tmp_file.name
            
            print("Downloading zip archive...")
            with urllib.request.urlopen(req, timeout=60) as response:
                if response.status != 200:
                    print(f"✗ HTTP {response.status}")
                    return False
                
                # Download in chunks
                chunk_size = 8192
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    tmp_file.write(chunk)
        
        print("Extracting font from archive...")
        # Extract DejaVuSans.ttf from zip
        with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
            # Find DejaVuSans.ttf in the archive
            font_found = False
            for file_info in zip_ref.namelist():
                if file_info.endswith('DejaVuSans.ttf'):
                    print(f"Found font: {file_info}")
                    with zip_ref.open(file_info) as source:
                        with open(FONT_FILE, 'wb') as target:
                            target.write(source.read())
                    font_found = True
                    break
            
            if not font_found:
                print("✗ DejaVuSans.ttf not found in archive")
                # List all files for debugging
                print("Files in archive:")
                for f in zip_ref.namelist()[:10]:
                    print(f"  - {f}")
                os.unlink(tmp_path)
                return False
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        if FONT_FILE.exists() and FONT_FILE.stat().st_size > 1000:
            file_size = FONT_FILE.stat().st_size
            print(f"✓ Font downloaded successfully: {FONT_FILE} ({file_size:,} bytes)")
            return True
        else:
            print(f"✗ Font file is invalid or too small")
            if FONT_FILE.exists():
                FONT_FILE.unlink()
            return False
            
    except urllib.error.HTTPError as e:
        print(f"✗ HTTP Error {e.code}: {e.reason}")
        return False
    except zipfile.BadZipFile as e:
        print(f"✗ Invalid zip file: {e}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def update_env_file(font_path: str) -> bool:
    """Update .env file with font path if it exists."""
    env_file = FONTS_DIR.parent / ".env"
    env_example = FONTS_DIR.parent / ".env.example"
    
    # Try to update .env if it exists
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if PDF_FONT_PATH already exists
            if 'PDF_FONT_PATH=' in content:
                # Update existing line
                lines = content.split('\n')
                updated = False
                for i, line in enumerate(lines):
                    if line.startswith('PDF_FONT_PATH='):
                        lines[i] = f'PDF_FONT_PATH={font_path}'
                        updated = True
                        break
                
                if updated:
                    with open(env_file, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lines))
                    print(f"✓ Updated .env file with font path")
                    return True
            else:
                # Append if not found
                with open(env_file, 'a', encoding='utf-8') as f:
                    f.write(f'\nPDF_FONT_PATH={font_path}\n')
                print(f"✓ Added PDF_FONT_PATH to .env file")
                return True
        except Exception as e:
            print(f"⚠ Could not update .env file: {e}")
            return False
    
    # Update .env.example if .env doesn't exist
    if env_example.exists():
        try:
            with open(env_example, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if 'PDF_FONT_PATH=' in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith('PDF_FONT_PATH='):
                        lines[i] = f'PDF_FONT_PATH={font_path}'
                        break
                
                with open(env_example, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
                print(f"✓ Updated .env.example with font path")
        except Exception as e:
            print(f"⚠ Could not update .env.example: {e}")
    
    return False


def main():
    """Main entry point."""
    success = download_font()
    
    if success:
        font_path = str(FONT_FILE.absolute())
        print(f"\n✓ Setup complete!")
        
        # Try to update .env file automatically
        updated = update_env_file(font_path)
        
        if not updated:
            print(f"\nAdd this to your .env file:")
            print(f"PDF_FONT_PATH={font_path}")
        return 0
    else:
        print(f"\n✗ Setup failed. Please download the font manually.")
        print(f"Visit: https://dejavu-fonts.github.io/")
        return 1


if __name__ == "__main__":
    sys.exit(main())

