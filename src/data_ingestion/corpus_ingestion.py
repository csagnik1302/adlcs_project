from pathlib import Path
import pymupdf
from pdf2image import convert_from_path
from pytesseract import image_to_string
import pandas as pd

def type_detection(file_dir):
    extensions={i.suffix for i in file_dir.iterdir() if i.is_file()}
    return list(extensions)[0]


def text_extractor(file_dir, glob_str):
    loaded_files={}
    for i in file_dir.glob(f"*{glob_str}"):
        loaded_files[i.name]=i.read_text(encoding='utf-8')
    return loaded_files


def pdf_extractor(file_path):
    doc=pymupdf.open(filename=file_path)
    doc_image=convert_from_path(pdf_path=file_path)

    output_text=''

    for i in range(len(doc)):
        page=doc[i]
        text=page.get_text()

        if len(text)>0:
            output_text+=text
        else:
            output_text+=image_to_string(image=doc_image[i])

    return output_text

def csv_extractor(file_path):
    output=pd.read_csv(file_path)
    return output

def main(file_path):
    type=type_detection(file_path=file_path)

    if type=='.txt':
        output=text_extractor(file_path=file_path)
    elif type=='.pdf':
        output=pdf_extractor(file_path=file_path)
    elif type=='.csv':
        output=csv_extractor(file_path=file_path)

    return output


if __name__=='__main__':

    from pathlib import Path

    PARENT=Path(__file__).resolve().parent
    SRC=PARENT.parent
    ROOT=SRC.parent

    data_folder=ROOT/'data'/'raw'

    print(type_detection(data_folder))


