from openai import OpenAI
from tqdm import tqdm
import torch
import pandas as pd
from transformers import AutoTokenizer
import jsonlines
import pickle
import argparse
import os
from .thought_chain_utils import (
    format_prompt,
    get_final_entailment_question,
)

parser = argparse.ArgumentParser(description="Filter character sheets")
parser.add_argument('--model_name', type=str, help="Model name", default="meta-llama/Llama-3.3-70B-Instruct", description="Model name for entailment classifier")
parser.add_argument('--retrofit_fname', type=str, help="File name from retrofitting the simplified csheet data", default="temp.longstorychapters.output.simplified.vllm.llama70B.40maxtok.retrofit.jsonl", description="File name from retrofitting the simplified csheet data")
parser.add_argument('--output_fname', type=str, help="File name to write the filtered csheets to", default="verified_longstorychapters.jsonl", description="File name to write the filtered csheets to")
parser.add_argument('--story-data-fname', type=str, help="File name to read the story data from", default="long_story_to_3chars+chaps.pkl", description="File name to read the story data from - used for getting the story snippet")
args = parser.parse_args()

client = OpenAI(
    base_url=os.getenv("BASE_URL", "http://localhost:8000/v1"),
    api_key=os.getenv("API_KEY", "token-abc123"),
)

MODEL_NAME = args.model_name
TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)

def get_pred(text):
    completion = client.completions.create(
        model=MODEL_NAME,
        prompt=text,
        max_tokens=1,
        temperature=0.0,
    )

    decoded_answer = completion.choices[0].text
    decoded_answer = decoded_answer.strip()
    # print(decoded_answer)
    if decoded_answer.endswith("."):
        decoded_answer = decoded_answer[:-1]
    try:
        pred = int(decoded_answer[-1])
    except:
        # error, just return 1
        pred = 1
    return pred

DATA_FNAME = argparse.retrofit_fname

with jsonlines.open(DATA_FNAME) as reader:
    simplified_data = list(reader)

ORIGINAL_STORIES_INPUT_FNAME = args.story_data_fname

with open(ORIGINAL_STORIES_INPUT_FNAME, "rb") as f:
    STORIES_TO_BASE_CHARACTER_SHEETS_ON = pickle.load(f)
# will be (story_name -> (list_of_3_characters, list_of_chapters))

verified_datapoints = []
for datapoint in tqdm(simplified_data):
    # datapoint['snippet] is the index of the chapter in the story
    header, chapter = STORIES_TO_BASE_CHARACTER_SHEETS_ON[datapoint['story_id']][1][datapoint['snippet']]
    snippet = header + chapter
    character = datapoint['character']
    sentence_of_interest = datapoint['sentence_to_verify']
    question = get_final_entailment_question()
    prior_questions_and_answers = []

    cur_prompt = format_prompt(
        MODEL_NAME,
        TOKENIZER,
        character,
        snippet,
        sentence_of_interest,
        question,
        prior_questions_and_answers,
    )

    pred = get_pred(cur_prompt)
    if pred == 5:
        verified_datapoints.append(datapoint)

print(f"Verified {len(verified_datapoints)} datapoints out of {len(simplified_data)}")

with jsonlines.open(argparse.output_fname, "w") as writer:
    writer.write_all(verified_datapoints)