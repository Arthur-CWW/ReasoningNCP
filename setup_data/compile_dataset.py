import jsonlines
import pickle
import json
from .prompt_utils import generate_reasoning_from_story_messages

# Explanations:
## STORY_TO_CHAPTERS_AND_CHARACTERS - {story id: [[character list], [chapter list]]}
## BOOK_TO_CHAPTER_SUMMARIES - {story id: [per-chapter summary list]}
## SUBCHAPTER_SUMMARIES_TO_TEXT - {storyid_uptoX: combined_str_of_summaries_up_to_that_chapter (not including)}
## STORY_CHAR_CHAP_TO_CSHEET - {storyid_charactername_X: character sheet for charactername up to that chapter}
## STORY_CHAR_SUMCSHEET - {storyid_charactername_X: summarized character sheet for charactername up to that chapter}
## SUMMARY_UPTOCHAP - { summaries up to chapter (from SUBCHAPTER_SUMMARIES_TO_TEXT) to summarized version}

def shorten_text_to_max_len(text, max_len=-1):
    if max_len < 0:
        return text
    new_text = []
    cur_len = 0
    split = text.split("\n")
    split = split[::-1]
    for i, s in enumerate(split):
        # remember to account for "\n" joining paragraphs
        num_words = len(s.split(" ")) + 1

        if cur_len + num_words > max_len:
            break
        cur_len += num_words
        new_text.append(s)
    new_text = new_text[::-1]
    return "\n".join(new_text)


def get_num_message_words(messages):
    combined = " ".join([m['content'] for m in messages])
    return len(combined.split(" "))

def get_datapoints(stories, last_n,
                   STORY_TO_CHAPTERS_AND_CHARACTERS, SUMMARY_UPTOCHAP,
                   BOOK_TO_CHAPTER_SUMMARIES,
                   STORY_CHAR_SUMCSHEET):
    datapoints = []
    for story in stories:
        characters, chapters = STORY_TO_CHAPTERS_AND_CHARACTERS[story]
        for chapter_index in range(MINIMUM_CHAPTER_INDEX, len(chapters) - MAXIMUM_CHAPTER_OFFSET):
            header, chapter = chapters[chapter_index]
            chapter = header + chapter
            next_chapter_words = len(chapter.split(" "))
            if next_chapter_words <= LOW_CHAPTER_WORD_LIMIT:
                print("too low")
                print(story, chapter_index, next_chapter_words)
                continue
            if next_chapter_words >= HIGH_CHAPTER_WORD_LIMIT:
                print("too high")
                print(story, chapter_index, next_chapter_words)
                continue

            prior_chapters = chapters[chapter_index - last_n:chapter_index]
            prior_chapters = "\n".join([h + c for h, c in prior_chapters])
            prior_chapters = shorten_text_to_max_len(prior_chapters, max_len=MAX_STORY_WORDS)
            if len(prior_chapters.split(" ")) >= HIGH_CHAPTER_WORD_LIMIT:
                continue
            prior_story_summary = SUMMARY_UPTOCHAP[f"{story}_upto{chapter_index}"]
            total_story_summary = SUMMARY_UPTOCHAP[f"{story}_upto{len(chapters)}"]
            synopsis = BOOK_TO_CHAPTER_SUMMARIES[story][chapter_index]

            all_csheets = {}
            for char in characters:
                csheet_id = f"{story}_{char}_{chapter_index}"
                csheet = STORY_CHAR_SUMCSHEET.get(csheet_id, None)
                if csheet is None:
                    print(csheet_id)
                if type(csheet) is dict:
                    csheet = csheet['final_summary']
                all_csheets[char] = csheet



            skip = any(v is None for v in all_csheets.values())
            if skip:
                print("AHH")
            if not skip:
                datapoint = {
                    'story_text':prior_chapters,
                    'next_chapter_header':header,
                    'prior_plot_summary':prior_story_summary,
                    'high_level_plot_summary':total_story_summary,
                    'character_sheets': all_csheets,
                    'next_chapter_synopsis':synopsis,
                    'last_n_chapters':last_n,
                    'next_chapter': chapter,
                    'chapter_index': chapter_index,
                    'story_id': story
                }
                messages = generate_reasoning_from_story_messages(datapoint, [], USE_SYSTEM_ROLE=True)
                num_message_words = get_num_message_words(messages)
                if num_message_words >= MESSAGE_WORD_LIMIT:
                    print(f"Skipping chapter {chapter_index} because it has {num_message_words} words")
                    continue
                datapoints.append(datapoint)
            else:
                print("FJDSKLFJDKSLJJKL")
    return datapoints

LOW_CHAPTER_WORD_LIMIT = 200
# HIGH_CHAPTER_WORD_LIMIT = 4000
HIGH_CHAPTER_WORD_LIMIT = 5000
MINIMUM_CHAPTER_INDEX = 2
MAXIMUM_CHAPTER_OFFSET = 2
MESSAGE_WORD_LIMIT = 10000
last_n = 1
MAX_STORY_WORDS = -1
split = "train"

with open(f"training_data/{split}_long_story_to_3chars+chaps.pkl", 'rb') as f:
    STORY_TO_CHAPTERS_AND_CHARACTERS = pickle.load(f)
print(f"len(STORY_TO_CHAPTERS_AND_CHARACTERS) = {len(STORY_TO_CHAPTERS_AND_CHARACTERS)}")

with open(f"training_data/{split}_long_story_character_sheet_summaryllama70B_0.5max.pkl", 'rb') as f:
    STORY_CHAR_SUMCSHEET = pickle.load(f)
print(f"len(STORY_CHAR_SUMCSHEET) = {len(STORY_CHAR_SUMCSHEET)}")

with open(f"training_data/{split}_long_story_chapter_to_plot_summaryllama70B_0.5max.pkl", 'rb') as f:
    SUMMARY_UPTOCHAP = pickle.load(f)
print(f"len(SUMMARY_UPTOCHAP) = {len(SUMMARY_UPTOCHAP)}")

with open(f"training_data/{split}_long_storyuptochapsum_to_storysummaries.pkl", "rb") as f:
    SUBCHAPTER_SUMMARIES_TO_TEXT = pickle.load(f)

with open(f"training_data/{split}_long_story_to_chapter_summaries.pkl", "rb") as f:
    BOOK_TO_CHAPTER_SUMMARIES = pickle.load(f)

stories = list(STORY_TO_CHAPTERS_AND_CHARACTERS.keys())
print(f"len(stories) = {len(stories)}")

datapoints = get_datapoints(stories, last_n,
                            STORY_TO_CHAPTERS_AND_CHARACTERS,
                            SUMMARY_UPTOCHAP, SUBCHAPTER_SUMMARIES_TO_TEXT,
                            BOOK_TO_CHAPTER_SUMMARIES,
                            STORY_CHAR_SUMCSHEET,
                           MAX_STORY_WORDS=MAX_STORY_WORDS)

print(f"writing {len(datapoints)} datapoints")
with jsonlines.open(f"{split}_long_story_noprompt_dataset.jsonl", 'w') as writer:
    writer.write_all(datapoints)
