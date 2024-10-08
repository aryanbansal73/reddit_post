import random
import os
import random
from datetime import date
import whisper_timestamped as whisper
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips

from support_func import *
model = whisper.load_model("base")

MAX_SHORTS_TIME = 60
MAX_REEL_TIME = 90

INSTAGRAM_REELS_QUEUE = []
TIKTOK_QUEUE = []
YOUTUBE_SHORTS_QUEUE = []


def randomVideoSegment(output_video_filepath, duration, background="subway"):
    total_duration_seconds = 30 * 60
    background_video_path = "static/video/minecraft.mp4"

    if background == "minecraft":
        background_video_path = "static/video/minecraft.mp4"
        video_clip = VideoFileClip(background_video_path)
        duration_sec = video_clip.duration
        minecraft_times = [int(duration_sec * i / 7) for i in range(8)]

        # minecraft_times = [4*60+17, 4*60+58, 9*60+50, 7*60+4, 5*60+59, 6*60+53, 51*60+54]
        rand_background = random.randint(1, 7)
        # total_duration_seconds = minecraft_times[rand_background - 1]
        background_video_path = f"static/video/minecraft/minecraft_{rand_background}.mp4"
        video_clip = VideoFileClip(background_video_path)
        total_duration_seconds = video_clip.duration
    elif background == "subway":
        background_video_path = "static/video/subway.mp4"
        video_clip = VideoFileClip(background_video_path)
        duration_sec = video_clip.duration
        subway_times = [int(duration_sec * i / 6) for i in range(7)]

        # minecraft_times = [4*60+17, 4*60+58, 9*60+50, 7*60+4, 5*60+59, 6*60+53, 51*60+54]
        rand_background = random.randint(1, 6)
        # total_duration_seconds = subway_times[rand_background - 1]
        background_video_path = f"static/video/subway/subway_{rand_background}.mp4"
        video_clip = VideoFileClip(background_video_path)
        total_duration_seconds = video_clip.duration
    elif background == "gta":
        background_video_path = "static/video/gta.mp4"
        video_clip = VideoFileClip(background_video_path)
        duration_sec = video_clip.duration
        gta_times = [int(duration_sec * i / 4) for i in range(5)]

        # minecraft_times = [4*60+17, 4*60+58, 9*60+50, 7*60+4, 5*60+59, 6*60+53, 51*60+54]
        rand_background = random.randint(1, 4)
        # total_duration_seconds = gta_times[rand_background - 1]
        background_video_path = f"static/video/gta/gta_{rand_background}.mp4"
        video_clip = VideoFileClip(background_video_path)
        total_duration_seconds = video_clip.duration
    # dark_theme_subreddits = ["nosleep", "letsnotmeet", "glitch_in_the_matrix", "creepyencounters"]
    # if any(text.lower() in output_video_filepath.lower() for text in dark_theme_subreddits):
    #     background_video_path = "static/video/nighttime_minecraft_parkour.mp4"
    #     total_duration_seconds = 33 * 60 + 33 # nightime minecraft parkour

    random_start_time_seconds = random.uniform(0, total_duration_seconds - duration)
    video_clip = VideoFileClip(background_video_path)
    random_segment = video_clip.subclip(random_start_time_seconds, random_start_time_seconds + duration)
    random_segment.write_videofile(output_video_filepath, codec="libx264", threads=8, preset='ultrafast', logger=None)
    print(f"Snipped {duration} s length video starting at: {random_start_time_seconds} for {output_video_filepath.split('/')[-1]}")

def make_video(wav_file_path, wav_title_file_path, video_path, post_path, postName):
    h
def overlayText(wav_file_path, wav_title_file_path, video_path, post_path, postName):
    global INSTAGRAM_REELS_QUEUE
    global YOUTUBE_SHORTS_QUEUE
    global TIKTOK_QUEUE
    text_colors = ['white', 'cyan', 'yellow', 'magenta']
    askreddit_comment_times = []
    if (postName.startswith("askreddit")):
        with open(f"{video_path.split('.')[0]}/comment_times.txt", 'r', encoding='utf-8') as comment_times:
            askreddit_comment_times = [float(value) for value in comment_times.read().split(',')]
    partNum = 0 
    wav_duration = get_wav_length(wav_file_path)

    video_title_path = f"{video_path.split('.')[0]}/videoTitle.txt"
    video_title = "Errors Reading From Title"
    with open(video_title_path, 'r', encoding='utf-8') as file:
        video_title = file.read().strip()
    title_duration = get_wav_length(wav_title_file_path)

     # if more than a 6 parter, create long form content intead
    long_form = False
    if (wav_duration + title_duration) >= 180:
        long_form = True
    insta_reel = False
    if (wav_duration + title_duration) < 90:
        insta_reel = True
    # only create multiple parts if proceeding clips are of valulable length
    multipleParts = title_duration + wav_duration > MAX_SHORTS_TIME
    
    multipleShorts = title_duration + wav_duration > MAX_SHORTS_TIME + 10
    b_clip, title_clip, banner_clip, comment_clip = createTitleClip(video_title + (" (p1)" if multipleShorts and not long_form else ""), 0, title_duration)
    print(wav_file_path)
    audio = whisper.load_audio(wav_file_path)
    print('success')
    result = whisper.transcribe(model, audio, 'en')

    start_time = 0
    currentVidTime = 0
    currentMaxVidTime = 60

    video_segments = [[[], []]]  # To store paths of individual video segments
    video_segments[partNum][1].append(0)
    video_segments[partNum][0].append(b_clip)
    video_segments[partNum][0].append(title_clip)
    video_segments[partNum][0].append(banner_clip)
    video_segments[partNum][0].append(comment_clip)

    reels_video_segments = [[], []]
    reels_video_segments[1].append(0)

    tiktok_video_segments = [[], []]
    tiktok_video_segments[1].append(0)

    video_clip = VideoFileClip(video_path)

    print(f"\nOverlaying Text on {postName}...")
    first_segment = True
    for segment in result['segments']:
        abbreviationFixedText = replace_abbreviations(segment['text'])
        if first_segment:
            first_segment = False

        # split segment into multiple if phrase is longer than 30 characters
        splitSegments = []
        if segment['end'] > start_time + 30:
            continue
        if len(abbreviationFixedText) <= 30:
            splitSegments.append([abbreviationFixedText, segment['end']])
        else:
        # if True:
            currentText = ""
            prevEnd = start_time
            for word in segment['words']:
                if (len(word['text']) + len(currentText) + 1) < 15:
                    currentText += (word['text'] + " ")
                else:
                    splitSegments.append([replace_abbreviations(currentText), prevEnd])
                    currentText = (word['text'] + " ")
                prevEnd = word['end']
            splitSegments.append([replace_abbreviations(currentText), prevEnd])
            if (prevEnd == -1):
                print("Invalid word, too many characters")
                return

        # create text overlay for each segment
        for split in splitSegments:
            text = split[0].strip()
            endTime = split[1]
            # wrappedText = splitTextForWrap(text.strip(), 15)
            wrappedText = text
            if len(wrappedText) == 0:
                continue

            duration = endTime - start_time
            # print(f"{start_time} {start_time + duration} {duration}\n'{wrappedText}'")

            # if length is over 60 seconds, create a new part for the video
            if ((endTime + (title_duration + 1) * (partNum + 1)) > currentMaxVidTime and not long_form):
                video_segments[partNum][1].append(start_time)
                currentMaxVidTime += 60
                partNum += 1
                video_segments.append([[], []])
                video_segments[partNum][1].append(start_time)
                b_clip, title_clip, banner_clip, comment_clip = createTitleClip(video_title + f" (p{partNum + 1})", 0, title_duration)
                video_segments[partNum][0].append(b_clip)
                video_segments[partNum][0].append(title_clip)
                video_segments[partNum][0].append(banner_clip)
                video_segments[partNum][0].append(comment_clip)

                currentVidTime = 0

            color = 'white'
            if postName.startswith("askreddit"):
                colorI = 0
                for time in askreddit_comment_times:
                    if time <= start_time + duration:
                        colorI += 1
                    else:
                        break
                color = text_colors[colorI % 4]
            
            new_textclip, shadow_textclip = createTextClip(wrappedText, currentVidTime, duration, color)
            video_segments[partNum][0].append(shadow_textclip)
            video_segments[partNum][0].append(new_textclip)

            if insta_reel and multipleParts:
                reels_new_textclip, reels_shadow_textclip = createTextClip(wrappedText, start_time, duration, color)
                reels_video_segments[0].append(reels_shadow_textclip)
                reels_video_segments[0].append(reels_new_textclip)

            if not insta_reel and not long_form:
                tiktok_new_textclip, tiktok_shadow_textclip = createTextClip(wrappedText, start_time, duration, color)
                tiktok_video_segments[0].append(tiktok_shadow_textclip)
                tiktok_video_segments[0].append(tiktok_new_textclip)

            # Update start time for the next segment
            start_time = endTime
            currentVidTime += duration

    video_segments[partNum][1].append(start_time)
    reels_video_segments[1].append(start_time)
    tiktok_video_segments[1].append(start_time)

    audio_clip = AudioFileClip(wav_file_path)

    # subclip to remove audio artifact, unusure why AudioFileclip makes, maybe a bug?
    title_audio_clip = AudioFileClip(wav_title_file_path)
    print_title = title_to_print(video_title)
    
    partNum = 1
    for part in video_segments:
        start_time = part[1][0]
        end_time = part[1][1]
        # last clip is too short to make
        if end_time - start_time < 10:
            continue

        snipped_title_video = video_clip.subclip(0, title_duration) if partNum == 1 else video_clip.subclip(start_time, start_time + title_duration)
        snipped_title_audio_clip = title_audio_clip.subclip(0, -0.15)#.audio_fadeout(snipped_title_video.duration - title_last_word_time)
        
        snipped_video = video_clip.subclip(start_time + title_duration, end_time + title_duration)
        snipped_audio = audio_clip.subclip(start_time, end_time)
        
        title_video_with_text = snipped_title_video.set_audio(snipped_title_audio_clip)
        title_video_with_text = CompositeVideoClip([title_video_with_text] + part[0][:4])

        video_with_text = CompositeVideoClip([snipped_video] + part[0][4:])
        video_with_text = video_with_text.set_audio(snipped_audio)

        final_video_clip = concatenate_videoclips([title_video_with_text, video_with_text])
        
        # # add dark theme to some subreddits and if it's not long form content
        # dark_theme_subreddits = ["nosleep", "creepyencounters", "letsnotmeet", "glitch_in_the_matrix"]
        # if any(text.lower() in postName.lower() for text in dark_theme_subreddits) and not long_form:
        #     # add snowfall background music for horror stories
        #     print(f"adding snowfall background music to {postName}")
        #     random_start_time_seconds = random.uniform(0, (15 * 60 + 28) - final_video_clip.duration)
        #     snowfall_audio = AudioFileClip("static/audio/snowfall_volume_boosted.mp3").subclip(random_start_time_seconds, random_start_time_seconds + final_video_clip.duration)
        #     final_audio = CompositeAudioClip([final_video_clip.audio, snowfall_audio])
        #     final_video_clip.audio = final_audio

        if not os.path.exists(f"{post_path}/{postName}"):
            os.makedirs(f"{post_path}/{postName}")
        video_num = f"_p{partNum}" if multipleShorts and not long_form else ""
        output_video_path = f"{post_path}/{postName}/{print_title}{video_num}.mp4"
        print(f"Writing output video: {output_video_path}")
        final_video_clip.write_videofile(output_video_path, codec="libx264", threads=8, preset='ultrafast')
        YOUTUBE_SHORTS_QUEUE.append(output_video_path)
        partNum += 1

    # write seperate if fits within instagram reels
    if insta_reel and multipleParts:
        end_time = reels_video_segments[1][1]
        b_clip, title_clip, banner_clip, comment_clip = createTitleClip(video_title, 0, title_duration)
        snipped_title_video = video_clip.subclip(0, title_duration)
        snipped_title_audio_clip = title_audio_clip.subclip(0, -0.15)
        snipped_video = video_clip.subclip(title_duration, end_time + title_duration)
        snipped_audio = audio_clip.subclip(0, end_time)
        title_video_with_text = snipped_title_video.set_audio(snipped_title_audio_clip)
        title_video_with_text = CompositeVideoClip([title_video_with_text] + [b_clip, title_clip, banner_clip, comment_clip])
        video_with_text = CompositeVideoClip([snipped_video] + reels_video_segments[0])
        video_with_text = video_with_text.set_audio(snipped_audio)
        final_video_clip = concatenate_videoclips([title_video_with_text, video_with_text])
        output_video_path = f"{post_path}/{postName}/{print_title}_reel.mp4"
        final_video_clip.write_videofile(output_video_path, codec="libx264", threads=8, preset='ultrafast')
        INSTAGRAM_REELS_QUEUE.append(output_video_path)
        print(f"Finished writing reel: {output_video_path}")
    elif insta_reel:
        output_video_path = f"{post_path}/{postName}/{print_title}.mp4"
        print(f"Using short {output_video_path} as Instagram Reel")
        INSTAGRAM_REELS_QUEUE.append(output_video_path)

    # write seperate tiktok
    if not insta_reel and not long_form:
        end_time = tiktok_video_segments[1][1]
        b_clip, title_clip, banner_clip, comment_clip = createTitleClip(video_title, 0, title_duration)
        snipped_title_video = video_clip.subclip(0, title_duration)
        snipped_title_audio_clip = title_audio_clip.subclip(0, -0.15)
        snipped_video = video_clip.subclip(title_duration, end_time + title_duration)
        snipped_audio = audio_clip.subclip(0, end_time)
        title_video_with_text = snipped_title_video.set_audio(snipped_title_audio_clip)
        title_video_with_text = CompositeVideoClip([title_video_with_text] + [b_clip, title_clip, banner_clip, comment_clip])
        video_with_text = CompositeVideoClip([snipped_video] + tiktok_video_segments[0])
        video_with_text = video_with_text.set_audio(snipped_audio)
        final_video_clip = concatenate_videoclips([title_video_with_text, video_with_text])
        output_video_path = f"{post_path}/{postName}/{print_title}_tiktok.mp4"
        final_video_clip.write_videofile(output_video_path, codec="libx264", threads=8, preset='ultrafast')
        TIKTOK_QUEUE.append(output_video_path)
        print(f"Finished writing tiktok: {output_video_path}")
    elif insta_reel and multipleParts:
        output_video_path = f"{post_path}/{postName}/{print_title}_reel.mp4"
        print(f"Using reel {output_video_path} as Tiktok")
        TIKTOK_QUEUE.append(output_video_path)
    else:
        output_video_path = f"{post_path}/{postName}/{print_title}.mp4"
        print(f"Using short {output_video_path} as Tiktok")
        TIKTOK_QUEUE.append(output_video_path)

    print("Overlay complete.")

if __name__ == "__main__":
    # today = date.today().strftime("%Y-%m-%d")
    today = "2024-06-18"
    # today = "Custom"
    # today = "Test"
    folder_path = f"RedditPosts/{today}/Texts"
    # for subreddit in os.listdir(folder_path):
    #     # print('i')
    #     post_path = f"{folder_path}/{subreddit}"
    #     for post in os.listdir(post_path):
    #         if post.endswith(".wav") and not post.endswith("title.wav"):
    #             wav_file_path = f"{post_path}/{post}"
    #             wav_title_file_path = f"{post_path}/{post.split('.')[0]}_title.wav"
    #             output_video_path = f"{post_path}/{post.split('.')[0]}.mp4"
    #             duration = get_wav_length(wav_file_path)
    #             title_duration = get_wav_length(wav_title_file_path)
    #             print(wav_file_path)
    #             print(wav_title_file_path)
    #             print(output_video_path)
                
    #             background = 'minecraft'
    #             randomVideoSegment(output_video_path, duration + title_duration, background)
    print("hi")
    for subreddit in os.listdir(folder_path):
        post_path = f"{folder_path}/{subreddit}"
        for post in os.listdir(post_path):
            if post.endswith(".mp4"):# and post.startswith("askreddit"):
                wav_file_path = f"{post_path}/{post.split('.')[0]}.wav"
                wav_title_file_path = f"{post_path}/{post.split('.')[0]}_title.wav"
                mp4_file_path = f"{post_path}/{post}"
                # if post != "AITAH2.mp4":
                #     continue
                overlayText(wav_file_path, wav_title_file_path, mp4_file_path, post_path, f"{post.split('.')[0]}")
    
    upload_queue_folder_path = f"RedditPosts/{today}/uploadQueue"
    if not os.path.exists(upload_queue_folder_path):
        os.makedirs(upload_queue_folder_path)

    with open(f"{upload_queue_folder_path}/tiktok_queue.txt", 'w', encoding='utf-8') as tiktok_upload_queue:
        tiktok_upload_queue.write('\n'.join(TIKTOK_QUEUE))
    with open(f"{upload_queue_folder_path}/instagram_queue.txt", 'w', encoding='utf-8') as insta_upload_queue:
        insta_upload_queue.write('\n'.join(INSTAGRAM_REELS_QUEUE))
    with open(f"{upload_queue_folder_path}/youtube_queue.txt", 'w', encoding='utf-8') as youtube_upload_queue:
        youtube_upload_queue.write('\n'.join(YOUTUBE_SHORTS_QUEUE))

    print("Video Maker Completed")