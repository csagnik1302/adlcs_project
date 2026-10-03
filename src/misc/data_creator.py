import os
from datasets import load_dataset
from dotenv import load_dotenv
import json
from pathlib import Path
from tqdm import tqdm

load_dotenv()
hf_token=os.getenv('HF_TOKEN')

dataset=[]
splits=['train','validation','test']

for i in splits:
    ds = load_dataset("Despina/conll04", token=hf_token, split=i)
    for j in range(len(ds)):
        dataset.append(ds[j])


MISC=Path(__file__).resolve().parent
SRC=MISC.parent
ROOT=SRC.parent

data_path=ROOT/'data'

for i in tqdm(dataset):
    with open(data_path/f'{i['orig_id']}.txt', 'w', encoding='utf-8') as f:
        f.write(i['text'])