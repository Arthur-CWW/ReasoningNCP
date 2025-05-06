import jsonlines
from tqdm import tqdm
import argparse
from openai import OpenAI
import pickle
import os
from transformers import AutoTokenizer
import argparse

parser = argparse.ArgumentParser(description="Summarize the chapter summaries")
parser.add_argument('--model_name', type=str, help="Model name", default="meta-llama/Llama-3.3-70B-Instruct")
parser.add_argument('--nice_model_name', type=str, help="Nice model name", default="llama70B")
parser.add_argument('--using_role', type=bool, help="Using system role", default=True)
parser.add_argument('--input_chapters_fname', type=str, help="Input chapters file name", default="train_long_storyuptochapsum_to_storysummaries.pkl")
parser.add_argument('--output_name', type=str, help="Output file name", default="train_long_story_chapter_to_plot_summaryllama70B_0.5max.pkl")
args = parser.parse_args()

MODEL_NAME = args.model_name

client = OpenAI(
    base_url=os.getenv("BASE_URL", "http://localhost:8000/v1"),
    api_key=os.getenv("API_KEY", "token-abc123"),
)

def get_vllm_response(
    messages,
    max_tokens=1024,
    temperature=0.9,
    top_p=0.9,
    num_return_sequences=1,
):
    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        n=num_return_sequences,
    )
    response_strs = [c.message.content for c in completion.choices]

    return response_strs

MODEL_NAME = args.model_name
nice_model_name = args.nice_model_name
USING_ROLE = args.using_role
# DATA_FNAME = "long_story_to_chapters.pkl"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

min_len = 50
max_len = 500

def make_messages_for_plot_summary(chapter, USING_ROLE=True):
    # use word ratio for tokens from booookscore
    plot_instruction = """write a detailed plot point-by-plot point summary for the excerpt provided, make sure to include vital information related to key events, backgrounds, settings, characters, their objectives, and motivations. You must briefly introduce characters, places, and other major elements if they are being mentioned for the first time in the summary. The story may feature non-linear narratives, flashbacks, switches between alternate worlds or viewpoints, etc. Therefore, you should organize the summary so it presents a consistent and chronological narrative. Note: the story sections provided may not necessarily be the entire story, so do not make claims as to the completeness of the story. Instead, focus on summarizing information that would be useful for continuing the story. Do not make any claims about the story being complete, or make overly broad claims about the story. The summary must be shorter than the provided summaries, and can include multiple paragraphs. Make sure to include all the important plot points and characters. Please mark when important plot points happen, using the chapter numbers as reference (e.g. '(Chapter 1)')."""

    role_text = "You are an expert author and writing assistant."
    query_text = """Below is a series of chapter summaries from a story. Please write a detailed summary of the story up to this point, don't miss out on any important plot points, characters, or chapters. Please mark when important plot points happen, using the chapter numbers as reference.
---
{chapter}
---
{plot_instruction}""".format(chapter=chapter, plot_instruction=plot_instruction)

    if USING_ROLE:
        messages = [
            {"role": "system", "content": role_text},
            {"role": "user", "content": query_text},
        ]
    else:
        messages = [
            {"role": "user", "content": role_text + "\n\n" + query_text},
        ]

    return messages

def get_estimated_token_length(next_chapter):
    return len(tokenizer(next_chapter)['input_ids'])

DATA_FNAME = args.input_chapters_fname

with open(DATA_FNAME, "rb") as f:
    STORY_TO_CHAPTERS = pickle.load(f)

output_name = args.output_name

chapter_to_plot_summary = {}

# structure is story_name -> list of chapters
dataset = list(STORY_TO_CHAPTERS.items())

print("len dataset", len(dataset))

print("loaded model and tokenizer")

i = 0
for story_name_upto_n, chapter_summaries in tqdm(dataset):
    if story_name_upto_n in chapter_to_plot_summary:
        print(f"skipping {story_name_upto_n} because we already have it")
        continue

    gen_next_chapter_summary_messages = make_messages_for_plot_summary(chapter_summaries, USING_ROLE=USING_ROLE)

    estimated_token_length = get_estimated_token_length(chapter_summaries)

    # the summary should be at most half the length of the story (which is already summarized)
    # if estimated_token_length < 4096:
    if estimated_token_length < 200:
        # very short summary, just use it as is
        summarized_chapters = chapter_summaries
    else:
        max_length = min(int(estimated_token_length * 0.8), 4096)
        # the summary should be at least 5% the length of the story
        # min_length = int(estimated_token_length * 0.05)
        decoded_messages = get_vllm_response(
            gen_next_chapter_summary_messages,
            max_tokens=max_length,
            temperature=0.6,
            top_p=0.9,
            num_return_sequences=1,
        )

        summarized_chapters = decoded_messages[0]

    summarized_chapters = summarized_chapters.strip()

    print(f"summarized story id: {story_name_upto_n}")

    print(f"ratio of words: {len(summarized_chapters.split()) / len(chapter_summaries.split())}")

    chapter_to_plot_summary[story_name_upto_n] = summarized_chapters

    with open(output_name, "wb") as f:
        pickle.dump(chapter_to_plot_summary, f)
