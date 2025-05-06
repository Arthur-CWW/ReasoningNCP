import jsonlines
from tqdm import tqdm
import argparse
from openai import OpenAI
import pickle
import os
from transformers import AutoTokenizer

# Add argument parsing
parser = argparse.ArgumentParser(description="Summarize character sheets")
# parser.add_argument('--model_name', type=str, help="Model name", default="meta-llama/Llama-3.3-70B-Instruct")
parser.add_argument('--model_name', type=str, help="Model name", default=os.getenv("MODEL_NAME", "deepseek/deepseek-chat-v3-0324:free"))
parser.add_argument('--nice_model_name', type=str, help="Nice model name", default="llama70B")
parser.add_argument('--using_role', type=bool, help="Whether to use system role", default=True)
parser.add_argument('--character_sheets_fname', type=str, help="Filename of the character sheets", default="train_long_story_to_3chars+chaps.vllm.jsonl")
parser.add_argument('--output_fname', type=str, help="Filename of the output", default="train_long_story_to_3chars+chaps.vllm.jsonl")
args = parser.parse_args()

fname = args.output_fname

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
    from rich.live import Live
    from rich.console import Console
    from rich.text import Text

    console = Console()
    response_strs = []

    with Live(console=console) as live:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            n=num_return_sequences,
            stream=True
        )

        for chunk in completion:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                live.update(Text(content))
                response_strs.append(content)

    return [''.join(response_strs)]

MODEL_NAME = args.model_name
nice_model_name = args.nice_model_name
USING_ROLE = args.using_role

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")

min_len = 50
max_len = 500

def make_messages_for_plot_summary(chapter, USING_ROLE=True):
    # use word ratio for tokens from booookscore
    plot_instruction = """Write a condensed version of the character sheet provided. Please summarize the sections within the character sheet provided above to create a more condensed character sheet, make sure to include vital information related to key events, backgrounds, settings, characters, their objectives, and motivations. Do not include any statements that do not add to our understanding of the character (e.g. "there are no physical descriptions of X"). You must briefly introduce characters, places, and other major elements if they are being mentioned for the first time in the summary. The story may feature non-linear narratives, flashbacks, switches between alternate worlds or viewpoints, etc. Therefore, you should organize the summary so it presents a consistent and chronological narrative. Please mark and describe how the character changes over time, using the snippet ids as reference."""

    role_text = "You are an expert author and writing assistant."

    query_text = """Below is a character sheet up to a point in a story (i.e. the character sheet does not represent the final state of the character). Please summarize the sections within the character sheet provided above to create a more condensed character sheet, make sure to include vital information related to key events, backgrounds, settings, characters, their objectives, and motivations. Do not include any statements that do not add to our understanding of the character (e.g. "there are no physical descriptions of X"). You must briefly introduce characters, places, and other major elements if they are being mentioned for the first time in the summary. The story may feature non-linear narratives, flashbacks, switches between alternate worlds or viewpoints, etc. Therefore, you should organize the summary so it presents a consistent and chronological narrative. Please mark and describe how the character changes over time, using the snippet ids as reference.
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

DATA_FNAME = args.character_sheets_fname

with open(DATA_FNAME, "rb") as f:
    STORYCHARCHAP_TO_CHARACTER_SHEETS = pickle.load(f)

if os.path.exists(fname):
    print(f"file {fname} already exists, loading what we have")
    with open(fname, "rb") as f:
        story_char_chap_to_character_sheet_summary = pickle.load(f)
    print(f"loaded {len(story_char_chap_to_character_sheet_summary)} chapters")
else:
    story_char_chap_to_character_sheet_summary = {}

# structure is story_name -> list of chapters

dataset = list(STORYCHARCHAP_TO_CHARACTER_SHEETS.items())

print("len dataset", len(dataset))

print("loaded model and tokenizer")

i = 0
for story_char_chap, character_sheet in tqdm(dataset):

    gen_next_chapter_summary_messages = make_messages_for_plot_summary(character_sheet, USING_ROLE=USING_ROLE)

    estimated_token_length = get_estimated_token_length(character_sheet)

    # restrict the length of the summary to 80% of the story or 2048 tokens, whichever is smaller
    max_length = min(int(estimated_token_length * 0.8), 2048)

    decoded_messages = get_vllm_response(
        gen_next_chapter_summary_messages,
        max_tokens=max_length,
        temperature=0.6,
        top_p=0.9,
        num_return_sequences=1,
    )

    next_chapter_summary = decoded_messages[0]

    next_chapter_summary = next_chapter_summary.strip()

    print(f"next chapter summary: {next_chapter_summary}")
    print(f"ratio of words: {len(next_chapter_summary.split()) / len(character_sheet.split())}")

    story_char_chap_to_character_sheet_summary[story_char_chap] = next_chapter_summary


with open(fname, "wb") as f:
    pickle.dump(story_char_chap_to_character_sheet_summary, f)
