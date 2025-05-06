# Setup Story Data

To use the following scripts, you will need to have organized your story data in these formats:

1) STORY_TO_CHAPTERS_AND_CHARACTERS: {story_name: (list_of_characters, list_of_chapters)} - technically optional if you choose to not use character sheets
2) SUBCHAPTER_SUMMARIES: {story_name_upto_n: combined_str_of_summaries_up_to_that_chapter (not including n)} - these could be the raw chapters but we use gold summaries of the chapters for computational efficiency and to avoid poor quality summaries
3) BOOK_TO_CHAPTER_SUMMARIES: {story_name: list_of_chapter_summaries}

These formats allow us to run the summarization steps independently and compile the dataset later.

## Start VLLM Server

We use VLLM for the generation steps, and recommend using the server mode for efficiency (you are able to run multiple scripts in parallel).

```bash
vllm serve meta-llama/Llama-3.3-70B-Instruct --tensor-parallel-size $GPU_COUNT --max-model-len 25000 --gpu-memory-utilization 0.95
```

Where `$GPU_COUNT` is the number of GPUs you want to use. You can change the other parameters but these are what we used in the paper.

## Summarize Chapter Summaries

Run

```bash
python vllm_summarize_chapter_summaries.py --model_name <model_name> --input_chapters_fname <input_chapters_fname> --output_name <output_name>
```

## Character Sheets

### Generate Character Sheets

Run

```bash
python vllm_summarize_character_sheets.py --model_name <model_name> --input_chapters_fname <input_chapters_fname> --output_name <output_name>
```

### Retrofit Character Sheets

This step is convenient for making the file-sizes smaller and avoiding storing unnecessary information.

Run

```bash
python retrofit_character_sheets.py --model_name <model_name> --retrofit_fname <retrofit_fname> --output_fname <output_fname>
```

### Filter Character Sheets

Run

```bash
python filter_csheets.py --model_name <model_name> --retrofit_fname <retrofit_fname> --output_fname <output_fname> --story-data-fname <story_data_fname>
```

### Summarize Character Sheets

Your data needs to have the following structure:

```
{
    "story_name_upto_n": character_sheets_upto_n
}
```

## Compile Dataset

Modify the `compile_dataset.py` script to point to the correct datasets and directory. This script will compile the dataset into a single file that can be used for training.

```bash
python compile_dataset.py
```