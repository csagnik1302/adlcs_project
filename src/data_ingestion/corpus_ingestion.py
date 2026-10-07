from pathlib import Path
import pymupdf
import pandas as pd

ROOT=Path(__file__).resolve().parent.parent.parent
raw_path=ROOT/'data'/'raw'



def type_detection(file_dir=raw_path):
    extensions={i.suffix for i in file_dir.iterdir() if i.is_file()}
    out=list(extensions)[0]
    return out



def path_list_ext(glob_str, file_dir=raw_path):
    file_path_list=[]

    for i in file_dir.rglob(f"*{glob_str}"):
        file_path_list.append(i)
    
    return file_path_list


def text_extractor(path_list):

    content=[]

    for i in path_list:
        with open(str(i),'r',encoding='utf-8') as f:
            text=f.read()
        content.append(text)

    return content


def pdf_extractor(path_list):

    content=[]

    for i in path_list:
        text=''
        with pymupdf.open(str(i)) as f:
            for page in f:
                page_text=page.get_text()
                text+=page_text.replace('\n',' ').strip()
        content.append(text)

    return content


# def csv_extractor(file_path):
#     output=pd.read_csv(file_path)
#     return output

def main(file_path):
    type=type_detection()
    path_list=path_list_ext(type)

    if type=='.txt':
        output=text_extractor(path_list)
    elif type=='.pdf':
        output=pdf_extractor(path_list)

    return output


if __name__=='__main__':

    from pathlib import Path

    PARENT=Path(__file__).resolve().parent
    SRC=PARENT.parent
    ROOT=SRC.parent

    data_folder=ROOT/'data'/'raw'

    out=main(data_folder)

    print(out)
