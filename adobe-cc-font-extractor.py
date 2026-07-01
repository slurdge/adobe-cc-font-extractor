import os
import optparse
import platform
import shutil
from pathlib import Path
from xml.etree import ElementTree
from fontTools.ttLib import TTFont

FONT_SPECIFIER_VARIATION_ID = 4
FONT_SPECIFIER_NAME_ID = 1

def _get_otf_data(font):
    name, variation = None, None
    for record in font["name"].names:
        if b'\x00' in record.string:
            data = record.string.decode('utf-16-be')
        else:
            try:
                data = record.string.decode('utf-8')
            except UnicodeDecodeError:
                data = record.string.decode('latin-1')
        if record.nameID == FONT_SPECIFIER_VARIATION_ID and not variation:
            variation = data
        elif record.nameID == FONT_SPECIFIER_NAME_ID and not name: 
            name = data
        if name and variation:
            break
    return name, variation

class AdobeCCFontExtrator:

    def __init__(self, output_path=None):
        self.output_path = Path(output_path) if output_path else Path(".")
        os.makedirs(self.output_path, exist_ok=True)
        self.resolve_font_path()

    def resolve_font_path(self):
        if platform.system() == "Windows":
            self.font_path = Path(os.path.expandvars(r"%APPDATA%\Adobe\CoreSync\plugins\livetype"))
        elif platform.system() == "Darwin":
            self.font_path = Path(os.path.expandvars(r"$HOME/Library/Application Support/Adobe/CoreSync/plugins/livetype"))
        else:
            print(f"Unsupported system: {platform.system()}")
    
    def extract_font_data(self):
        manifest = self.font_path / "c" / "entitlements.xml"
        root = ElementTree.parse(manifest).getroot()
        self.fonts = {}

        for font in root.find("fonts").findall("font"):
            properties = font.find("properties")
            self.fonts[font.find("id").text] = {
                "name": properties.find("familyName").text,
                "variation": properties.find("variationName").text
            }

    def extract(self):
        self.extract_font_data()
        candidates = ("r", "t", "w")
        for font_id, font_data in self.fonts.items():
            source = None
            for candidate in candidates:
                font_folder = self.font_path / candidate
                source = font_folder / font_id
                if not source.exists():
                    source = None
                    continue
            if source is None:
                print(f"Font exists in manifest but not on filesystem: {font_id}")
                continue
            #Check this is a well formed file
            ttfont = TTFont(file=source)
            name, variation = _get_otf_data(ttfont)
            destination = self.output_path / f"{font_data['name']} {font_data['variation']}.otf"
            if not destination.exists():
                print(f"Extracting {font_data['name']} with variation {font_data['variation']}")
                shutil.copy(source, destination)


def main():
    options = optparse.OptionParser(description="Tool to extract Adobe font back in their original format")
    extractor = AdobeCCFontExtrator("output")
    extractor.extract()

if __name__ == "__main__":
    main()