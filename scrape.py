from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.edge import service
# from openai import OpenAI
# from accountCredentials.openai_key import OPENAI_API_KEY
from scrapeLinksHelpers import getAskRedditComments, remove_emojis , replaceProfanity
from datetime import date
import time
import os
import re
from selenium.webdriver.common.keys import Keys

from webdriver_manager.chrome import ChromeDriverManager

from dotenv import load_dotenv
load_dotenv()
reddit_username = os.environ.get('REDDIT_USERNAME')
reddit_password = os.environ.get('REDDIT_PASSWORD')

options = webdriver.ChromeOptions()
options.add_argument('headless')
options.add_argument('user-agent="MQQBrowser/26 Mozilla/5.0 (Linux; U; Android 2.3.7; zh-cn; MB200 Build/GRJ22; CyanogenMod-7) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1"')

options.add_argument('window-size=1920x1080')
# options.add_argument('disable-gpu')

driver = webdriver.Chrome(options= options)
entire_post = ""

subreddits = {
    "relationships": 3, 
    "relationship_advice": 3, 
    "confessions": 3, 
    "TrueOffMyChest": 5, 
    "offmychest": 5,
    "tifu": 4, 
    "legaladvice": 1, 
    "AmItheAsshole": 8, 
    "AITAH": 8,  
    "askreddit": 3
}   

def check_id(id_name):
    try:
        driver.find_element(By.ID, id_name)
    except NoSuchElementException:
        return False
    return True

def check_class(class_name):
    try:
        driver.find_element(By.CLASS_NAME, class_name)
    except NoSuchElementException:
        return False
    return True


def check_selector(selector):
    try:
        driver.find_element(By.CSS_SELECTOR, selector)
    except NoSuchElementException:
        return False
    return True

from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

def slow_typing(element, text): 
   for character in text: 
      element.send_keys(character)
      time.sleep(0.05)

def login():
    driver.get("https://www.reddit.com/login/")
    print(reddit_username)
    username_field = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "login-username"))
    )
    password_field =  WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "login-password"))
    )
    slow_typing(username_field, reddit_username)
    slow_typing(password_field, reddit_password)

    
    time.sleep(2)
    

    password_field.send_keys(Keys.ENTER)


    time.sleep(4)

def getContentLoggedIn(url, download_path, subreddit, number, custom):
    global subreddits
    if not custom and subreddits[subreddit] <= 0 or "removed_by_reddit" in url:
        return False

    if not os.path.exists(download_path):
        os.makedirs(download_path)

    # create the file
    filename = subreddit + str(number) + ".txt"
    output_file = os.path.join(download_path, filename)
    try:
        driver.get(url)
        #using this to ensure that it is loaded
        driver.execute_script("return document.readyState")
        time.sleep(1)

        div_post = ""
        contentClass = "_3xX726aBn29LDbsDtzr_6E"
        # div_post = driver.find_element(By.CLASS_NAME, contentClass)
        div_post = driver.find_element(By.XPATH, "//div[starts-with(@id, 't3')]")

        # title_element = driver.find_element(By.TAG_NAME, "title")
        title_element = driver.find_element(By.XPATH, "//h1[starts-with(@id, 'post-title-t3')]")

        # title = title_element.get_attribute("text").split(':')[0].strip()
        title = title_element.text.rsplit(':', 1)[0].strip()
        if not title.endswith(('.', '!', '?', ';', ':')):
            title += '.'

        if title == 'Reddit - Dive into anything.':
            title_element = driver.find_element(By.XPATH, '//*[@id="t3_198rdnr"]/div/div[3]/div[1]/div/h1')
            title = title_element.get_attribute("text").rsplit(':', 1)[0].strip()
            if not title.endswith(('.', '!', '?', ';', ':')):
                title += '.'
            print(f"Found the default title , now replacing it with {title}")

        if "update" in title.lower():
            print(f"Skipping post at url {url}: Update instead of new content")
            return False

        entire_post = title + "\n"

        if subreddit == "askreddit":
             # create a file and write the title to it
            with open(output_file, 'w', encoding='utf-8') as file:
                cleaned_post = replaceProfanity(entire_post)
                file.write(cleaned_post)
            if getAskRedditComments(output_file, url):
                subreddits[subreddit] -= 1
                return True
            return False

        # get all text into a variable
        p_elements = div_post.find_elements(By.TAG_NAME, "p")
        for p_element in p_elements:
            # Tokenize the input text into sentences
            entire_post += p_element.text + '\n'

        pattern = re.compile(r'edit:', re.IGNORECASE)
        match = pattern.search(entire_post)
        if match:
            entire_post = entire_post[:match.start()]
        pattern = re.compile(r'update:', re.IGNORECASE)
        match = pattern.search(entire_post)
        if match and (match.start() > (len(entire_post) / 4)):
            entire_post = entire_post[:match.start()]
        pattern = re.compile(r'update post:', re.IGNORECASE)
        match = pattern.search(entire_post)
        if match and (match.start() > (len(entire_post) / 4)):
            entire_post = entire_post[:match.start()]
        pattern = re.compile(r'edited to:', re.IGNORECASE)
        match = pattern.search(entire_post)
        if match and (match.start() > (len(entire_post) / 4)):
            entire_post = entire_post[:match.start()]

        entire_post = entire_post
        # entire_post = title + '.\n' + completion.choices[0].message.content
        entire_post = remove_emojis(entire_post)

        if len(entire_post) < 900 or len(entire_post) > 2300:
            print(f"Post at {url} is too short or long with {len(entire_post)} characters, skipping...")
            return False

        with open(output_file, 'w', encoding='utf-8') as file:
            cleaned_post = replaceProfanity(entire_post)
            # title = cleaned_post[0]
            title = cleaned_post.split('\n')[0]
            # print(title)
            file.write(cleaned_post)
        
        subreddits[subreddit] -= 1
        return True
    
    except Exception as e:
        print("An error occurred:", str(e))
        return False
def run_2():
    # Define the URL of the Reddit page you want to scrape
    today = date.today().strftime("%Y-%m-%d")
    # today = "2024-01-18"
    # today = "Custom"

    login()
    custom = True if today == "Custom" else False
    filePath = f"RedditPosts/{today}/links.txt"
    download_path = f"RedditPosts/{today}/Texts"
    file = open(filePath, 'r')
    links = file.readlines()
    subreddit = "TIFU"
    count = 1
    for link in links:
        if link.strip():
            tryLink = "https://" + link
            path = download_path + '/' + subreddit
            if "reddit.com" in tryLink:
                if getContentLoggedIn(tryLink, path, subreddit, count, custom):
                    count += 1
            else:
                subreddit = link.strip()
                count = 1

    # Close the browser
    driver.quit()
if __name__ == "__main__":
    # Define the URL of the Reddit page you want to scrape
    today = date.today().strftime("%Y-%m-%d")
    # today = "2024-01-18"
    # today = "Custom"

    login()
    custom = True if today == "Custom" else False
    filePath = f"RedditPosts/{today}/links.txt"
    download_path = f"RedditPosts/{today}/Texts"
    file = open(filePath, 'r')
    links = file.readlines()
    subreddit = "TIFU"
    count = 1
    for link in links:
        if link.strip():
            tryLink = "https://" + link
            path = download_path + '/' + subreddit
            if "reddit.com" in tryLink:
                if getContentLoggedIn(tryLink, path, subreddit, count, custom):
                    count += 1
            else:
                subreddit = link.strip()
                count = 1

    # Close the browser
    driver.quit()