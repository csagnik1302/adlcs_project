import os
from misc import view_graphml
from corpus_ingestion import main
from atlas_rag.kg_construction.triple_extraction import KnowledgeGraphExtractor
from atlas_rag.kg_construction.triple_config import ProcessingConfig
from atlas_rag.llm_generator import LLMGenerator
from transformers import pipeline
from dotenv import load_dotenv
import tomllib
from pathlib import Path
import json
import shutil

ROOT=Path(__file__).resolve().parent.parent.parent

load_dotenv()
hf_token=os.getenv('HF_TOKEN')

with open('config.toml', 'rb') as f:
    config=tomllib.load(f)

model_name=config['data_ingestion']['llm_model']

client=pipeline("text-generation", model=model_name, device_map="auto", token=hf_token)

raw_directory=ROOT/'data'/'raw'
input_directory=ROOT/'data'/'kg_input'
output_directory=ROOT/'data'/'kg_output'
KEYWORD='kg_input_docs'


def json_parse(raw_dir=raw_directory):

    doc_list=main(raw_dir)

    documents = []
    for idx, doc in enumerate(sorted(doc_list)):
        text = doc
        if text:
            documents.append({"id": f"doc_{idx}", "text": text})
    return documents




def save_json(documents, json_dir=input_directory, keyword=KEYWORD):
    if not documents:
        raise FileNotFoundError("No non-empty .txt files found to convert")

    # Wipe everything inside json_dir, then recreate it
    if json_dir.exists():
        shutil.rmtree(json_dir)
    json_dir.mkdir(parents=True, exist_ok=True)

    out_file = json_dir / f"{keyword}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(documents)} documents to {out_file}")





def kg_extractor(client=client, model_name=model_name, input_dir=input_directory, output_dir=output_directory, keyword=KEYWORD):
    triple_generator=LLMGenerator(client, model_name=model_name)
    kg_extraction_config=ProcessingConfig(model_path=model_name,
                                        data_directory=str(input_dir),
                                        filename_pattern=keyword,
                                        batch_size_triple=3,
                                        batch_size_concept=16,
                                        output_directory=str(output_dir))
    kg_extractor=KnowledgeGraphExtractor(model=triple_generator, config=kg_extraction_config)

    kg_extractor.run_extraction()
    kg_extractor.convert_json_to_csv()
    kg_extractor.generate_concept_csv_temp(batch_size=64)
    kg_extractor.create_concept_csv()
    kg_extractor.convert_to_graphml()


def kg_extractor_pipeline():
    save_json(json_parse())
    kg_extractor()


if __name__=='__main__':

    # kg_extractor_pipeline()
    view_graphml(r'D:\adlcs_project\data\kg_output\kg_graphml\kg_input_docs_graph.graphml')
