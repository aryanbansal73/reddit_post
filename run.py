import os
import subprocess
from get_links_reddit import run_1
from scrape import run_2
from testing import run_3
if __name__ == "__main__":
    # Run the Python files
    # get top weekly posts
    run_1()
    run_2()
    run_3()
    # get post content
    # subprocess.run(["python", "./scrape.py"])
    # convert post content to mp3
    # subprocess.run(["python", "./testing.py"])
    # create videos
    # subprocess.run(["python", "./textOverlay.py"])

    # upload videos to YouTube, Tiktok, and Instagram
    # subprocess.run(["python", "./youtube_upload/upload.py"])
    # subprocess.run(["python", "./tiktok_uploader/upload_vid.py"])