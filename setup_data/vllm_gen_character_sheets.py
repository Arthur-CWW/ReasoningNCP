import os
from tqdm import tqdm
import argparse

#####################################################################################
# GENERAL STRUCTURE OF CHIRON GENERATION
#
# 1) Generate basic structure
# 2) Simplify (semi-optional)
# 4) Feed those into classifier (not done in this script)
#
#####################################################################################

parser = argparse.ArgumentParser(description="Run evaluation on a specific quarter of the dataset.")
parser.add_argument("--input_fname", type=str, default="train_long_story_to_3chars+chaps.pkl")
parser.add_argument("--save_name", type=str, default="train_longstorychapters")
args = parser.parse_args()

input_fname = args.input_fname
SAVING_NAME = args.save_name

ORIGINAL_STORIES_INPUT_FNAME = input_fname

##########################################################################
# SAMPLING PARAMS
######################################################
##########################################################################

from chiron_generation_module_utils import get_prompt_data_for_chiron_generation

import jsonlines
from transformers import AutoTokenizer
from chiron_simplification_utils import (
    SIMPLIFICATION_ICL_BASE_QUERY,
    flatten_generation_outputs,
    get_chiron_simplification_format_prompt,
    reformat_sentences_from_simplification,
)

from openai import OpenAI

client = OpenAI(
    base_url=os.getenv("BASE_URL", "http://localhost:8000/v1"),
    api_key=os.getenv("API_KEY", "token-abc123"),
)

import jsonlines
from transformers import AutoTokenizer

import pandas as pd
import pickle

import re

import torch

regexspace = re.compile(r"\ +", re.IGNORECASE)
regexlines = re.compile(r"(\n(\ )?)+", re.IGNORECASE)


##########################################################################
# Generation Module
##########################################################################
# GENERATION_MODULE_MAX_TOKENS = 150
GENERATION_MODULE_MAX_TOKENS = 300
# GENERATION_MODULE_MAX_TOKENS = 500
# GENERATION_MODULE_NUM_BEAMS = 4

# GENERATION_MODULE_MODEL_NAME = "mistral7bv0.3"
# GENERATION_MODULE_CHECKPOINT_NAME = "mistralai/Mistral-7B-Instruct-v0.3"
GENERATION_MODULE_MODEL_NAME = "llama70B"
GENERATION_MODULE_CHECKPOINT_NAME = "meta-llama/Llama-3.3-70B-Instruct"
USING_SYSTEM_ROLE = "llama" in GENERATION_MODULE_CHECKPOINT_NAME.lower()

model = None
TOKENIZER = AutoTokenizer.from_pretrained(GENERATION_MODULE_CHECKPOINT_NAME)
# TOKENIZER.padding_side = "right"
# TOKENIZER.add_special_tokens({"pad_token": "[PAD]"})
print(f"Tokenizer loaded!")


def generation():
    generationmodule_output_name = f"./temp.{SAVING_NAME}.output.generationmodule.vllm.{GENERATION_MODULE_MODEL_NAME}.{GENERATION_MODULE_MAX_TOKENS}maxtok.jsonl"

    if os.path.exists(generationmodule_output_name):
        print(f"Loading generation module outputs from {generationmodule_output_name}...")
        with jsonlines.open(generationmodule_output_name, "r") as reader:
            GENERATION_OUTPUTS = list(reader)
        print(f"Loaded {len(GENERATION_OUTPUTS)} generation module outputs")
        print(f"Getting sentences...")
        FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE = flatten_generation_outputs(
            GENERATION_OUTPUTS
        )

        print(
            f"Found {len(FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE)} sentences, starting simplification..."
        )
        return FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE

    print(f"Loading input stories from {ORIGINAL_STORIES_INPUT_FNAME}...")
    with open(ORIGINAL_STORIES_INPUT_FNAME, "rb") as f:
        STORIES_TO_BASE_CHARACTER_SHEETS_ON = pickle.load(f)

    # will be (story_name, (list_of_3_characters, list_of_chapters))
    STORIES_TO_BASE_CHARACTER_SHEETS_ON = list(STORIES_TO_BASE_CHARACTER_SHEETS_ON.items())

    print(f"Loaded! Found {len(STORIES_TO_BASE_CHARACTER_SHEETS_ON)} stories")

    if QUARTER is not None:
        print("USING QUARTER")
        quarter_point = len(STORIES_TO_BASE_CHARACTER_SHEETS_ON) // 4
        if QUARTER == 1:
            STORIES_TO_BASE_CHARACTER_SHEETS_ON = STORIES_TO_BASE_CHARACTER_SHEETS_ON[
                :quarter_point
            ]
        elif QUARTER == 2:
            STORIES_TO_BASE_CHARACTER_SHEETS_ON = STORIES_TO_BASE_CHARACTER_SHEETS_ON[
                quarter_point : quarter_point * 2
            ]
        elif QUARTER == 3:
            STORIES_TO_BASE_CHARACTER_SHEETS_ON = STORIES_TO_BASE_CHARACTER_SHEETS_ON[
                quarter_point * 2 : quarter_point * 3
            ]
        elif QUARTER == 4:
            STORIES_TO_BASE_CHARACTER_SHEETS_ON = STORIES_TO_BASE_CHARACTER_SHEETS_ON[
                quarter_point * 3 :
            ]

        print(f"New length post quarter: {len(STORIES_TO_BASE_CHARACTER_SHEETS_ON)}")

    all_generation_module_data_pre_generation = []
    generation_module_prompts = []
    # for every story
    for story_name, (list_of_3_characters, list_of_chapters) in STORIES_TO_BASE_CHARACTER_SHEETS_ON:
        for character in list_of_3_characters:
            all_snippets = list_of_chapters
            all_snippets = [header + text for header, text in all_snippets]

            # for every snippet in the story, get the prompt and data
            for snippet in all_snippets:
                # some have role, some don't
                snippet_role = None

                all_prompt_data = get_prompt_data_for_chiron_generation(
                    TOKENIZER,
                    snippet,
                    character,
                    snippet_role=snippet_role,
                    using_system_role=USING_SYSTEM_ROLE,
                )
                for prompt_data in all_prompt_data:
                    prompt_data["story_id"] = story_name
                    prompt_data["character"] = character

                    generation_module_prompts.append(prompt_data["prompt"])
                    all_generation_module_data_pre_generation.append(prompt_data)

    print(f"Running generation on {len(generation_module_prompts)} prompts")

    # outputs = model.generate(generation_module_prompts, GENERATION_MODULE_SAMPLING_PARAMS)

    generate_method = (
        lambda prompt: client.chat.completions.create(
            model=GENERATION_MODULE_CHECKPOINT_NAME,
            messages=prompt,
            stream=False,
            max_tokens=GENERATION_MODULE_MAX_TOKENS,
            temperature=0.6,
            top_p=0.9,
            # top_k=50,
            stop=["\n"],
        )
        .choices[0]
        .message.content
    )
    outputs = []
    for prompt in tqdm(generation_module_prompts):
        outputs.append(generate_method(prompt))

        print(f"response: {outputs[-1]}")

    print(f"Finished generation!")

    all_generation_module_data = []
    for output, prompt_data in zip(outputs, all_generation_module_data_pre_generation):
        # generated_text = output.outputs[0].text
        generated_text = output.strip()

        new_prompt_data = prompt_data.copy()
        new_prompt_data["response"] = generated_text

        all_generation_module_data.append(new_prompt_data)

    print(
        f"Writing {len(all_generation_module_data)} examples to {generationmodule_output_name}..."
    )

    with jsonlines.open(generationmodule_output_name, "w") as writer:
        writer.write_all(all_generation_module_data)

    # with jsonlines.open("/mnt/disk/" + generationmodule_output_name, "w") as writer:
    #     writer.write_all(all_generation_module_data)

    print(f"FINISHED: saved to {generationmodule_output_name}")

    del all_generation_module_data_pre_generation
    del generation_module_prompts

    GENERATION_OUTPUTS = all_generation_module_data

    print(f"Loaded! Found {len(GENERATION_OUTPUTS)} results")

    print(f"Getting sentences...")
    FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE = flatten_generation_outputs(
        GENERATION_OUTPUTS
    )

    print(
        f"Found {len(FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE)} sentences, starting simplification..."
    )
    return FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE

FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE = generation()


#########################################################
# Simplification
#########################################################
def simplification(
    FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE, TOKENIZER
):
    print("Getting prompt data")
    # we will save the flattened version of the data, with the entailment information added on top
    all_output_simplified_data = FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE.copy()
    # get prompts for each sentence and this question
    all_prompts_for_this_question = []
    # save sentences so we can get their lengths for generation
    all_sentences = []
    # iterate over per-sentence data
    for sentence_index, query_data in enumerate(
        FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE
    ):
        sentence_of_interest = query_data["sentence_of_interest"]
        all_sentences.append(sentence_of_interest)

        statsandsimps = SIMPLIFICATION_ICL_BASE_QUERY.split("\n\n")[1:]
        statsandsimps = [comb.split("\n") for comb in statsandsimps][:-1]

        # note this is tokenized but both should return same result

        # cur_prompt = get_chiron_simplification_format_prompt(
        #     TOKENIZER, statsandsimps, sentence_of_interest, tokenize=True
        # )
        cur_prompt = get_chiron_simplification_format_prompt(
            TOKENIZER, statsandsimps, sentence_of_interest, tokenize=False
        )

        all_prompts_for_this_question.append(cur_prompt)

        # update the data with the prompt+question information
        all_output_simplified_data[sentence_index][
            "sentence_from_response_to_split"
        ] = sentence_of_interest

    print(
        f"Running simplification task over model: {len(all_prompts_for_this_question)}"
    )


    generate_method = (
        lambda messages: client.chat.completions.create(
            model=GENERATION_MODULE_CHECKPOINT_NAME,
            messages=messages,
            stream=False,
            max_tokens=50, # should tune
            temperature=0.6,
            top_p=0.9,
            # top_k=50,
            stop=["\n"],
        )
        .choices[0]
        .message.content
    )

    output_simplification_texts = []
    for prompt in tqdm(all_prompts_for_this_question):
        output_simplification_texts.append(generate_method(prompt))
        print(f"simplified: {output_simplification_texts[-1]}")

    print(
        "Finished running over model, now reformatting our data and filtering bad simplifications..."
    )

    reformat_sentences_from_simplification(
        all_output_simplified_data, output_simplification_texts
    )

    print("Reformatting complete")

    simplification_output_name = f"./temp.{SAVING_NAME}.output.simplified.vllm.{GENERATION_MODULE_MODEL_NAME}.40maxtok.jsonl"

    print(
        f"Writing {len(all_output_simplified_data)} examples to {simplification_output_name}..."
    )

    with jsonlines.open(simplification_output_name, "w") as writer:
        writer.write_all(all_output_simplified_data)

    print(f"FINISHED: saved to {simplification_output_name}")

    del all_prompts_for_this_question
    del all_sentences
    return all_output_simplified_data


all_output_simplified_data = simplification(
    FLATTENED_GENERATION_OUTPUTS_PER_SENTENCE,
    TOKENIZER,
)