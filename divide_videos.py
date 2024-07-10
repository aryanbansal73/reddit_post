
import os
from moviepy.editor import VideoFileClip

def split_video_into_parts(video_path, output_dir, base_name):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    video_clip = VideoFileClip(video_path)
    video_clip = video_clip.without_audio()
    duration_sec = video_clip.duration
    part_durations = [duration_sec * i / 5 for i in range(6)]
    
    for i in range(5):
        start_time = part_durations[i]
        end_time = part_durations[i + 1]
        segment = video_clip.subclip(start_time, end_time)
        output_path = os.path.join(output_dir, f"{base_name}_{i+1}.mp4")
        segment.write_videofile(output_path, codec="libx264", threads=8, preset='ultrafast')
        print(f"Saved segment {i+1} from {start_time} to {end_time} seconds as {output_path}")
def resize_video(input_path, output_path):
    # Load the video
    video = VideoFileClip(input_path)
    
    # Resize the video
    resized_video = video.resize(newsize=(1080, 1920))
    
    # Write the resized video to a file
    resized_video.write_videofile(output_path, codec='libx264', fps=video.fps)
if __name__ == "__main__":

    input_directory = "static/video"
    
    for video_filename in os.listdir(input_directory):
        video_path = os.path.join(input_directory, video_filename)
        
        if video_filename.endswith(".mp4"):
            base_name, _ = os.path.splitext(video_filename)
            output_directory = os.path.join(input_directory, base_name)
            split_video_into_parts(video_path, output_directory, base_name)

    print("All videos have been split into 4 parts.")
