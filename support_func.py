import os
import math
# import shutil
import numpy as np
import pydub
import wave
from pydub import AudioSegment
from moviepy.editor import AudioFileClip, VideoFileClip, ImageClip, TextClip, CompositeVideoClip
from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": r"C:\\Program Files\\ImageMagick-7.1.1-Q16-HDRI\\magick.exe"})
# Construct the relative path to ffmpeg.exe
script_dir = os.path.dirname(os.path.abspath(__file__))
ffmpeg_exe_path = os.path.join(script_dir, "ffmpeg.exe")
pydub.AudioSegment.ffmpeg = ffmpeg_exe_path
# pydub.AudioSegment.converter = ffmpeg_exe_path
# pydub.utils.get_prober_name = lambda: ffmpeg_exe_path
import re

def replace_abbreviations(sentence):
    pattern_aita1 = r'\bada\b'
    pattern_aita2 = r'\bida\b'
    pattern_aita3 = r'\baida\b'
    pattern_aita4 = r'\bada\b'
    pattern_tifu1 = r'\btyphoo\b'
    pattern_tifu2 = r'\bTIF(?:\s*,*\s*)you\b'
    
    modified_sentence = re.sub(pattern_aita1, 'AITA', sentence, flags=re.IGNORECASE)
    modified_sentence = re.sub(pattern_aita2, 'AITA', modified_sentence, flags=re.IGNORECASE)
    modified_sentence = re.sub(pattern_aita3, 'AITA', modified_sentence, flags=re.IGNORECASE)
    modified_sentence = re.sub(pattern_aita4, 'AITA', modified_sentence, flags=re.IGNORECASE)
    modified_sentence = re.sub(pattern_tifu1, 'TIFU', modified_sentence, flags=re.IGNORECASE)
    modified_sentence = re.sub(pattern_tifu2, 'TIFU', modified_sentence, flags=re.IGNORECASE)

    return modified_sentence

def title_to_print(video_title):
    first_5_words = video_title[:-1].split()[:5]
    words_until_10_chars = ""
    for word in first_5_words:
        if len(words_until_10_chars) > 15:
              break
        else:
            words_until_10_chars += word + "_"
    return words_until_10_chars[:-1].replace(':', '').replace('&', '').replace('"', '').replace('/', '')

def splitTextForWrap(input_str: str, line_length: int):
    words = input_str.split(" ")
    line_count = 0
    split_input = ""
    line = ""
    i = 0
    for word in words:
        # long word case
        if (line_count == 0 and len(word) >= line_length):
            split_input += (word + ("\n" if i < (len(words) - 1) else ""))
        elif (line_count + len(word) + 1) > line_length:
            paddingNeeded = line_length - line_count
            alternatePadding = True
            while (paddingNeeded > 0):
                if alternatePadding:
                    line = "\u00A0" + line
                else:
                    line = line + "\u00A0"
                alternatePadding = not alternatePadding
                paddingNeeded -= 1
            line += "\n"

            split_input += line
            line = word
            line_count = len(word)
        else:
            line += ("\u00A0" + word) 
            line_count += len(word) + 1
        i += 1
    
    paddingNeeded = line_length - line_count
    alternatePadding = True
    while (line_count != 0 and paddingNeeded > 0):
        if alternatePadding:
            line = "\u00A0" + line
        else:
            line = line + "\u00A0"
        alternatePadding = not alternatePadding
        paddingNeeded -= 1
    split_input += line
    return split_input
def get_wav_length(wav_file_path):
    try:
        with wave.open(wav_file_path, 'rb') as wav_file:
            # Get the duration in seconds
            duration_seconds = wav_file.getnframes() / float(wav_file.getframerate())
            return duration_seconds
    except Exception as e:
        print(f"Error: {e}")
        return 0

def get_mp3_length(mp3_file_path):
    try:
        audio_clip = AudioFileClip(mp3_file_path)
        duration_seconds = audio_clip.duration
        audio_clip.close()
        return duration_seconds
    except Exception as e:
        print(f"Error: {e}")
        return None
    
def add_mp3_padding(file_path, padding_duration_seconds):
    audio = AudioSegment.from_file(file_path, format="mp3")
    padding_duration_ms = int(padding_duration_seconds * 1000)
    padding = AudioSegment.silent(duration=padding_duration_ms)
    extended_audio = audio + padding
    extended_audio.export(file_path, format="mp3")

def calculate_db(input_file):
    print(input_file)
    audio_segment = AudioSegment.from_file(input_file)
    rms = audio_segment.rms
    if rms == 0:
        return float('-inf')  # Avoid log(0)
    return 20 * math.log10(rms)

def make_mp3_audio_louder(input_audio_path, output_audio_path, volume_factor):
    audio_clip = AudioSegment.from_file(input_audio_path)
    loud_audio = audio_clip + volume_factor
    loud_audio.export(output_audio_path, format="mp3")

def convert_video_to_audio(input_video_path, output_audio_path):
    # Load the video clip
    video_clip = VideoFileClip(input_video_path)
    audio_clip = video_clip.audio
    audio_clip.write_audiofile(output_audio_path, codec='mp3')
    video_clip.close()
    audio_clip.close()

def adjust_mp4_volume(file_path, target_dB):
    video_clip = VideoFileClip(file_path)
    mean_volume_dB = 20 * np.log10(np.sqrt(np.mean(video_clip.audio.to_soundarray()**2)))
    volume_factor = 10**((target_dB - mean_volume_dB) / 20)
    print(f"{volume_factor} {mean_volume_dB}")
    # new_video_clip = video_clip.volumex(volume_factor)
    new_video_clip = video_clip.multiply_volume(volume_factor).set_audio(video_clip.audio)

    print(f"Adjusting {file_path} to -14dB")
    temp_file_path = f"{file_path.split('.')[0]}_temp.mp4"
    # new_video_clip.write_videofile(temp_file_path, codec='libx264', audio_codec='aac', logger=None)
    new_video_clip.write_videofile(temp_file_path, codec='libx264', audio_codec='aac', logger=None, temp_audiofile="temp-audio.m4a", remove_temp=True)
    # shutil.move(temp_file_path, file_path)
    video_clip.close()
    new_video_clip.close()
def createTitleClip(wrappedText, start, duration):
    width_x = 720
    height_y = 1280
    textbox_size_x = 640
    textbox_size_y = 400

    font = "ARLRDBD.TTF"
    new_textclip = TextClip(
        wrappedText, 
        fontsize=50, 
        color='black', 
        bg_color='transparent',
        method='caption',
        font=f"static/fonts/{font}",
        size=(600, None),
        align='West',
    ).set_start(start).set_duration(duration).resize(width=600).set_position(('center', 'center'))
    text_width, text_height = new_textclip.size

    background_image_path = 'static/images/medalled_banner_resized.png'
    background_clip = ImageClip(background_image_path, duration=duration).resize((640, text_height + 20)).set_position(('center', 'center'))

    banner_path = 'static/images/medalled_banner_resized.png'
    banner_clip = ImageClip(banner_path, duration=duration).resize(width=640).set_position(('center', 1280))

    comment_path = 'static/images/comments.png'
    comment_clip = ImageClip(comment_path, duration=duration).resize(width=640).set_position(('center', 1280))

    return background_clip, new_textclip, banner_clip, comment_clip

def createTextClip(wrappedText, start, duration, color='white'):
    width_x = 720
    height_y = 1280
    textbox_size_x = 640
    textbox_size_y = 400
    center_x = width_x / 2 - textbox_size_x / 2
    center_y = height_y / 2 - textbox_size_y / 2

    font = 'GILBI___.TTF'
    new_textclip = TextClip(
        wrappedText, 
        fontsize=105, 
        color=color, 
        bg_color='transparent',
        method='caption',
        # method='label',
        font=f'static/fonts/{font}',
        size=(textbox_size_x, None)#, textbox_size_y)
    ).set_start(start).set_duration(duration).resize(lambda t : min(1, 0.8  + 15 * t)).set_position(('center', 'center'))
    
    shadow_textclip = TextClip(
        wrappedText, 
        fontsize=105, 
        color='black', 
        bg_color='transparent', 
        stroke_width=20,
        stroke_color="black",
        method='caption',
        # method='label',
        font=f'static/fonts/{font}',
        size=(textbox_size_x + 20, None)#, textbox_size_y)
    ).set_start(start).set_duration(duration).resize(lambda t : min(1, 0.6  + 20 * t)).set_position(('center', 'center'))

    return new_textclip, shadow_textclip


if __name__ == "__main__":
    calculate_db("RedditPosts/2024-01-05/Texts/creepyencounters/creepyencounters1/part1.mp4")
    # date = "Test"    
    # directory_path = f'RedditPosts/{date}/Texts'  # Replace with the path to your directory
    # all_files = []
    # for subreddit in os.listdir(directory_path):
    #     subredditFolder = f"{directory_path}/{subreddit}"
    #     for post in os.listdir(subredditFolder):
    #         if post.endswith(".mp3"):
    #             postPath = f"{subredditFolder}/{post}"
    #             print(calculate_db(postPath))

    # input_video_path = 'audio/snowfall_volume_boosted.mp4'
    # output_audio_path = 'audio/snowfall_volume_boosted.mp3'

    # convert_video_to_audio(input_video_path, output_audio_path)

    # make_mp3_audio_louder("audio/snowfall.mp3", "audio/snowfall2x.mp3", 2.0)