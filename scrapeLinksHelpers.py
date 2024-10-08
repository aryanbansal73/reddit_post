import requests
import time
import re
import html
import demoji
from bs4 import BeautifulSoup

MAX_COMMENTS = 8

profanity = {
	"fuck": "frick",
	"damn": "darn",
	"bitch": "dog",
	"shitty": "lousy",
	"whore": "tramp",
    "bastard": "scoundrel",
    "cock": "rod",
	# "ass": "butt",
    
	# "sex":"shenanigans"
}

def replaceProfanity(text):
	replaced_text = text
	for key, value in profanity.items():
		replaced_text = replaced_text.replace(key, value)
	return replaced_text

def remove_emojis(text):
    return demoji.replace(text, '')

def getAskRedditComments(output_file, url):
    # Send a GET request to the URL
    response = requests.get(f"{url}.json?sort=top")
    while response.status_code != 200:
        print(f"Status code of {response.status_code}: Trying again...")
        time.sleep(1)
        response = requests.get(f"{url}.json")
    if response.status_code == 200:
        # Parse the HTML content using Beautiful Soup
        data = response.json()

        i = 0
        # top_comments = []
        for thread in data[1]["data"]["children"]:
            try:
                thread_data = thread["data"]
                if "body" in thread_data:
                    top_thread_body = html.unescape(thread_data["body"])
                    soup = BeautifulSoup(top_thread_body, 'html.parser')
                    top_thread_body = soup.get_text()

                    pattern = re.compile(r'edit:', re.IGNORECASE)
                    match = pattern.search(top_thread_body)
                    if match:
                        top_thread_body = top_thread_body[:match.start()]
                    pattern = re.compile(r'update:', re.IGNORECASE)
                    match = pattern.search(top_thread_body)
                    if match and (match.start() > (len(top_thread_body) / 4)):
                        top_thread_body = top_thread_body[:match.start()]

                    # top_comments.append(remove_emojis(top_thread_body))
                    if (top_thread_body == '[removed]' or top_thread_body == '[deleted]' or 'https' in top_thread_body):
                        continue
                    with open(output_file, 'a', encoding='utf-8') as file:
                        file.write(replaceProfanity(str(remove_emojis(top_thread_body).replace("\n", " ")) + "\n\n"))
            except:
                print("Out of comments, moving on...")
            i += 1
            if (i >= MAX_COMMENTS):
                break
        return True
    else:
        print(f"Failed to fetch the URL. Status code: {response.status_code}")
        return False