
import os
from moviepy.editor import VideoFileClip

def split_video_into_parts(video_path, output_dir, base_name):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    video_clip = VideoFileClip(video_path)
    duration_sec = video_clip.duration
    part_durations = [duration_sec * i / 3 for i in range(4)]
    
    for i in range(3):
        start_time = part_durations[i]
        end_time = part_durations[i + 1]
        segment = video_clip.subclip(start_time, end_time)
        output_path = os.path.join(output_dir, f"{base_name}_{i+1}.mp4")
        segment.write_videofile(output_path, codec="libx264", threads=8, preset='ultrafast')
        print(f"Saved segment {i+1} from {start_time} to {end_time} seconds as {output_path}")

if __name__ == "__main__":
    input_directory = "static/video"
    
    for video_filename in os.listdir(input_directory):
        video_path = os.path.join(input_directory, video_filename)
        
        if video_filename.endswith(".mp4"):
            base_name, _ = os.path.splitext(video_filename)
            output_directory = os.path.join(input_directory, base_name)
            split_video_into_parts(video_path, output_directory, base_name)

    print("All videos have been split into 4 parts.")
